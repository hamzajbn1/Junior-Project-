import { useEffect, useRef, useState } from 'react';
import '../design/assistant.css';

const examples = [
'Find papers where machine learning uses random forest from 2018 to 2020.',
  'Show a yearly chart where machine learning includes random forest.',
  'Find papers where machine learning customizes random forest.',
];

const outputLabels = {
    papers: 'Supporting papers',
    yearly_trend: 'Papers per year and chart', 
    relationship: 'Relationship check',
    explanation: 'Evidence-based explanation'
};

async function assistantApi(path, options = {}){
    let response;
    try {
        response = await fetch(`/api/assistant/${path}`, options);
    } catch (error) {
        if (error.name === 'AbortError') throw error;
        throw new Error('Cannot reach the planner service. Start the backend, then try again.');
    }
    let body;
    try {body = await response.json();}
    catch { throw new Error('The planner service sent an unreadable response. Check that the backend is running.'); }
    if (!response.ok) throw new Error(body.error || 'The planner is unavailable. Please try again.');
    return body;
}

function PlanCard({ result }){
    const plan = result.plan;
    const ready = plan.status === 'ready';
    const years = plan.year_from === null && plan.year_to === null ? 'No year limits requested'
        : `${plan.year_from ?? 'Available start'} – ${plan.year_to ?? 'Available end'}`;
    
    return (
        <article className="plan-card" aria-label="Proposed research plan">
      <div className="plan-card-top">
        <span className={`plan-state ${ready ? '' : 'plan-state-question'}`}>
          {ready ? 'Plan ready for review' : plan.status === 'unsupported' ? 'Unsupported request' : 'Clarification needed'}
        </span>
        <span className="plan-duration">{result.elapsed_seconds}s</span>
      </div>
      <p className="plan-message">{plan.message}</p>
      <dl className="plan-intent">
        <div><dt>First concept</dt><dd>{plan.first_concept || 'Please specify'}</dd></div>
        <div><dt>Connection</dt><dd>{plan.relationship_label || 'Needs a supported meaning'}</dd></div>
        <div><dt>Second concept</dt><dd>{plan.second_concept || 'Please specify'}</dd></div>
        <div><dt>Publication years</dt><dd>{years}</dd></div>
        <div><dt>Requested output</dt><dd>{outputLabels[plan.requested_output]}</dd></div>
      </dl>
      {ready && <>
        <h3>Proposed tool sequence</h3>
        <ol className="plan-steps">
          {plan.steps.map(step => <li key={step.id}>
            <span className="plan-step-id">{step.id}</span>
            <div><strong>{step.name}</strong><p>{step.output}</p>
              <small>{step.requires.length ? `Depends on ${step.requires.join(', ')}` : 'Starts with the researcher’s wording'}</small>
            </div>
          </li>)}
        </ol>
        <details className="plan-details"><summary>Conditional next actions</summary>
          <ul>{plan.conditions.map(condition => <li key={condition}>{condition}</li>)}</ul>
        </details>
      </>}
      <p className="plan-disclaimer">Proposed plan only. Concepts and evidence have not been checked in CS-KG. Research tools are not executed in this milestone.</p>
      <details className="plan-details"><summary>Structured planner output</summary>
        <pre>{JSON.stringify(plan, null, 2)}</pre>
      </details>
    </article>
    );
}

export default function Assistant() {
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [connection, setConnection] = useState({ connected: false, message: 'Checking local model…' });
  const controller = useRef(null);
  const bottom = useRef(null);
  const input = useRef(null);

  useEffect (() => { 
    const previousTitle = document.title; 
    document.title = 'AI Assistant · Research Trend Explorer';
    const statusController = new AbortController();
    assistantApi('status', { signal: statusController.signal }).then(setConnection).catch(err => {
      if (err.name !== 'AbortError') setConnection({ connected: false, message: err.message });
    });
    return () => {document.title = previousTitle; statusController.abort(); controller.current?.abort(); };
  }, []);

  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end'});}, [messages, loading]);

  async function checkConnection() {
    setConnection({ connected: false, message: 'Checking local model…' });
    try { setConnection(await assistantApi('status')); }
    catch (err) { setConnection({ connected: false, message: err.message }); }
  }

  async function submit(event) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || loading) return;
    const history = messages.flatMap(message => message.result ? [
      {role: 'user', content: message.question},
      {role: 'assistant', content: JSON.stringify({ ...message.result.plan, steps: undefined, conditions: undefined })},  
    ] : []).slice(-2);
    const abort = new AbortController();
    controller.current = abort;
    setLoading(true);
    setError('');
    setMessages(previous => [...previous, { question, pending: true }]);
    setDraft('');
    try {
      const result = await assistantApi('plan', { method: 'POST', signal: abort.signal,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, history }) });
      setMessages(previous => previous.map((message, i) => i === previous.length - 1 ? { question, result } : message));
      setConnection({ connected: true, model: result.model, message: 'Local model available' });
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError(err.message);
        setDraft(question);
        setMessages(previous => previous.map((message, i) => i === previous.length - 1 ? { question, failed: true } : message));
      }
    } finally {
      if (controller.current === abort) { setLoading(false); controller.current = null; }
    }
  }
  
  function newConversation() {
    if (loading) return;
    setMessages([]); setDraft(''); setError(''); input.current?.focus();
  }

  return (
    <div className="assistant-layout">
      <aside className="assistant-sidebar">
        <span className="eyebrow">RESEARCH ASSISTANT</span>
        <h1>Plan your search.</h1>
        <p>Describe two concepts and the connection you want to investigate.</p>
        <button className="assistant-new" onClick={newConversation} disabled={loading}><span aria-hidden="true">＋</span> New conversation</button>
        <div className="assistant-stage"><span className="eyebrow">CURRENT MILESTONE</span><h2>Orchestrator / Planner</h2>
          <p>Interprets your request and proposes the tools and steps. Evidence retrieval comes in a later milestone.</p>
        </div>
        <div className="assistant-model" aria-live="polite"><span className={`assistant-model-dot ${connection.connected ? 'online' : ''}`} aria-hidden="true" />
          <div><strong>{connection.model || 'Local Qwen model'}</strong><p>{connection.message}</p>
            <button onClick={checkConnection} className="text-button" type="button">Check connection</button>
          </div>
        </div>
      </aside>
      <section className="assistant-chat" aria-label="AI Assistant conversation">
        <header className="assistant-chat-header"><span>AI Assistant</span><span className="assistant-milestone">Planning milestone</span></header>
        <div className="assistant-scroll">
          {messages.length === 0 ? <div className="assistant-welcome">
            <div className="assistant-symbol" aria-hidden="true">↗</div>
            <span className="eyebrow">FROM A QUESTION TO A PLAN</span>
            <h2>What would you like to research?</h2>
            <p>Write the connection in your own words. I’ll identify the concepts, interpret the relationship, and prepare a proposed research plan.</p>
            <div className="assistant-examples">{examples.map(example => <button key={example} onClick={() => { setDraft(example); input.current?.focus(); }}>{example}<span aria-hidden="true">↗</span></button>)}</div>
          </div> : <div className="assistant-messages">
            {messages.map((message, index) => <div className="assistant-turn" key={index}>
              <div className="assistant-user"><span className="sr-only">Researcher: </span>{message.question}</div>
              {message.result && <div className="assistant-answer"><span className="assistant-answer-label">RESEARCH ASSISTANT</span><PlanCard result={message.result} /></div>}
              {message.failed && <p className="assistant-failed">No plan was produced. Edit or resend your request below.</p>}
            </div>)}
            {loading && <div className="assistant-wait" role="status"><span className="spinner" aria-hidden="true" /><span>Qwen is preparing your plan…<small>The first response may take longer while the model loads.</small></span></div>}
          </div>}
          <div ref={bottom} />
        </div>
        <div className="assistant-compose-area">
          {error && <p className="assistant-error" role="alert">{error}</p>}
          <form onSubmit={submit} className="assistant-composer">
            <label className="sr-only" htmlFor="research-question">Research question</label>
            <textarea id="research-question" ref={input} value={draft} maxLength={2000} rows={2}
              placeholder="Find papers where machine learning uses random forest…"
              onChange={event => setDraft(event.target.value)}
              onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form.requestSubmit(); } }}
              aria-describedby="assistant-input-note" />
            <button type="submit" disabled={loading || !draft.trim()} aria-label="Create research plan">{loading ? '…' : '↑'}</button>
          </form>
          <p id="assistant-input-note" className="assistant-input-note">Enter to send · Shift + Enter for a new line. Conversation stays in this page session; it is not saved.</p>
        </div>
      </section>
    </div>
  );
}

























