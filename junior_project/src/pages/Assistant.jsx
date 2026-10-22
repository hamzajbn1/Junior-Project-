import { useEffect, useRef, useState } from 'react';
import '../design/assistant.css';

const examples = ['Hello, how are you?', 'Introduce yourself briefly.', 'What can you help me with?'];

async function connectionRequest(path, controller, message) {
  const timer = setTimeout(() => controller.abort(), 35000);
  try {
    const response = await fetch(`/api/assistant/connection/${path}`, {
      signal: controller.signal,
      ...(message !== undefined ? {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      } : path === 'test' ? { method: 'POST' } : {}),
    });
    let body;
    try { body = await response.json(); }
    catch { throw new Error('The assistant service returned an unreadable response.'); }
    if (!response.ok) throw new Error(body.error || 'The assistant service is unavailable.');
    if (path !== 'status' && (body.status !== 'ok' || typeof body.text !== 'string' || !body.text.trim())) {
      throw new Error('Gemini returned no usable reply. Please try again.');
    }
    return body;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Waiting for Gemini stopped. Please try again.');
    if (error instanceof TypeError) throw new Error('Cannot reach the assistant service. Make sure the backend is running.');
    throw error;
  } finally { clearTimeout(timer); }
}

export default function Assistant() {
  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState([]);
  const [connection, setConnection] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const input = useRef(null);
  const scroll = useRef(null);
  const active = useRef(null);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = 'AI Assistant · Research Trend Explorer';
    const controller = new AbortController();
    connectionRequest('status', controller)
      .then(body => { if (!controller.signal.aborted) setConnection(body); })
      .catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => {
      document.title = previousTitle;
      controller.abort();
      active.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [turns, busy, error]);

  function newConversation() {
    active.current?.abort();
    active.current = null;
    setTurns([]); setDraft(''); setError(''); setBusy('');
    input.current?.focus();
  }

  async function run(path) {
    if (active.current) return;
    const text = draft.trim();
    if (path === 'message' && !text) return;
    const controller = new AbortController();
    active.current = controller;
    setBusy(path); setError('');
    if (path === 'message') {
      setTurns(current => [...current, { message: text, reply: '', failed: false }]);
      setDraft('');
    }
    try {
      const body = await connectionRequest(path, controller, path === 'message' ? text : undefined);
      if (active.current !== controller) return;
      setConnection({ configured: true, connection_verified: true, model: body.model });
      if (path === 'message') {
        setTurns(current => current.map((turn, index) => index === current.length - 1 ? { ...turn, reply: body.text } : turn));
      }
    } catch (err) {
      if (active.current !== controller) return;
      setError(err.message);
      if (path === 'message') {
        setTurns(current => current.map((turn, index) => index === current.length - 1 ? { ...turn, failed: true } : turn));
        setDraft(current => current || text);
      }
    } finally {
      if (active.current === controller) { active.current = null; setBusy(''); }
    }
  }

  const connectionLabel = connection?.connection_verified ? 'Connected'
    : connection?.configured ? 'Ready to send'
    : connection ? 'Setup required' : 'Connection not checked';

  return (
    <div className="assistant-layout">
      <aside className="assistant-sidebar">
        <span className="eyebrow">RESEARCH ASSISTANT</span>
        <h1>Explore your research.</h1>
        <p>Start with a message to your AI assistant.</p>
        <button className="assistant-new" type="button" onClick={newConversation}><span aria-hidden="true">＋</span> New conversation</button>
        <div className="assistant-stage"><span className="eyebrow">ASSISTANT STATUS</span><h2>{connectionLabel}</h2>
          <p>Send a message to receive a reply from Gemini.</p>
        </div>
        <div className="assistant-model" aria-live="polite"><span className={`assistant-model-dot ${connection?.connection_verified ? 'online' : ''}`} aria-hidden="true" />
          <div><strong>AI Assistant</strong><p>{connection?.model || 'Gemini'} · {connectionLabel}</p>
            <button disabled={Boolean(busy)} className="text-button" type="button" onClick={() => run('test')}>{busy === 'test' ? 'Checking…' : 'Check connection'}</button>
          </div>
        </div>
      </aside>
      <section className="assistant-chat" aria-label="AI Assistant conversation">
        <header className="assistant-chat-header"><span>AI Assistant</span><span className="assistant-milestone">{connectionLabel}</span></header>
        <div className="assistant-scroll" ref={scroll}>
          {!turns.length ? <div className="assistant-welcome">
            <div className="assistant-symbol" aria-hidden="true">↗</div>
            <span className="eyebrow">AI ASSISTANT</span>
            <h2>Start a conversation.</h2>
            <p>Try “Hello, how are you?” to get a reply from Gemini.</p>
            <div className="assistant-examples">{examples.map(example => <button type="button" key={example} onClick={() => { setDraft(example); input.current?.focus(); }}>{example}<span aria-hidden="true">↗</span></button>)}</div>
          </div> : <div className="assistant-messages">
            {turns.map((turn, index) => <div className="assistant-turn" key={index}>
              <div className="assistant-user">{turn.message}</div>
              {turn.reply && <div className="assistant-answer"><span className="assistant-answer-label">AI ASSISTANT</span><p className="assistant-reply">{turn.reply}</p></div>}
              {turn.failed && <p className="assistant-failed">No reply received. Your message is available below to try again.</p>}
            </div>)}
          </div>}
          {busy && <div className="assistant-wait" role="status"><span className="spinner" aria-hidden="true" />{busy === 'test' ? 'Checking the Gemini connection…' : 'Waiting for Gemini…'}</div>}
        </div>
        <div className="assistant-compose-area">
          {error && <p className="assistant-error" role="alert">{error}</p>}
          <form onSubmit={event => { event.preventDefault(); run('message'); }} className="assistant-composer">
            <label className="sr-only" htmlFor="research-question">Message</label>
            <textarea id="research-question" ref={input} value={draft} maxLength={2000} rows={2}
              placeholder="Type a message…" onChange={event => setDraft(event.target.value)} aria-describedby="assistant-input-note" />
            <button type="submit" disabled={Boolean(busy) || !draft.trim()} aria-label="Send message">↑</button>
          </form>
          <p id="assistant-input-note" className="assistant-input-note">Each message is sent independently. This conversation is not saved.</p>
        </div>
      </section>
    </div>
  );
}
