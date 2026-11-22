import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ResultChart } from '../components/Agent3Result';
import '../design/assistant.css';

const ACTIVE = new Set(['running', 'needs_clarification']);

async function request(path, body, signal, method = body === undefined ? 'GET' : 'POST') {
  const response = await fetch(`/api/assistant/${path}`, {
    method,
    ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }), signal,
  });
  let data;
  try { data = await response.json(); } catch { throw new Error('The assistant returned an unreadable response.'); }
  if (!response.ok) throw new Error(data.error || 'The assistant service is unavailable.');
  return data;
}

function Choices({ turn, onResume, disabled }) {
  const [selections, setSelections] = useState({});
  const unresolved = Object.entries(turn.choices || {}).filter(([, value]) => !value.selected);
  return <form className="assistant-choices" onSubmit={event => { event.preventDefault(); onResume(turn, selections); }}>
    {unresolved.map(([side, value]) => <label key={side}>{side === 'first' ? 'First concept' : 'Second concept'}
      <select value={selections[side] || ''} required onChange={e => setSelections({ ...selections, [side]: e.target.value })}>
        <option value="">Choose the intended meaning</option>
        {value.candidates.map(candidate => <option key={candidate.id} value={candidate.id}>{candidate.label || candidate.name || candidate.id}</option>)}
      </select>
    </label>)}
    <button disabled={disabled} type="submit">Continue research</button>
  </form>;
}

function Output({ output }) {
  return <div className="assistant-result">
    {output.explanation && <p className="assistant-reply">{output.explanation}</p>}
    {output.model && <small>{output.model}</small>}
    {output.message && <p>{output.message}</p>}
    {output.error && <p role="alert">{output.error.message}</p>}
    {output.chart && <ResultChart spec={output.chart} />}
    {output.warnings?.length > 0 && <ul className="assistant-warnings">{output.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
    {output.retrieved_at && <small>Sources: CS-KG and OpenAlex · Retrieved {output.retrieved_at} · {output.research_status}</small>}
  </div>;
}

export default function Assistant() {
  const [searchParams, setSearchParams] = useSearchParams();
  const chatId = Number(searchParams.get('chat')) || null;
  const [chats, setChats] = useState([]);
  const [loadedChatId, setLoadedChatId] = useState(null);
  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState('');
  const [provider, setProvider] = useState('auto');
  const [error, setError] = useState('');
  const [connection, setConnection] = useState(null);
  const [sending, setSending] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [ready, setReady] = useState(false);
  const [reload, setReload] = useState(0);
  const activeRequest = useRef(null);
  const scroll = useRef(null);
  const input = useRef(null);
  const loading = !ready || chatId !== loadedChatId;
  const pending = !loading && turns.find(t => ACTIVE.has(t.status));
  const pendingId = pending?.turn_id;
  const pendingStatus = pending?.status;
  const chatControlsBusy = sending || deleting;
  const busy = chatControlsBusy || loading || Boolean(pending);
  const selectedConfigured = provider === 'auto' ? connection?.configured : connection?.providers?.[provider]?.configured;

  useEffect(() => {
    const previousTitle = document.title;
    document.title = 'AI Assistant · Research Trend Explorer';
    const controller = new AbortController();
    request('connection/status', undefined, controller.signal).then(setConnection).catch(() => {});
    request('chats', undefined, controller.signal).then(data => {
      setChats(data.chats);
      setReady(true);
      if (!new URLSearchParams(window.location.search).has('chat') && data.chats.length) {
        setSearchParams({ chat: String(data.chats[0].chat_id) }, { replace: true });
      }
    }).catch(failure => { if (!controller.signal.aborted) setError(failure.message); });
    return () => { document.title = previousTitle; controller.abort(); activeRequest.current?.abort(); };
  }, [setSearchParams]);

  useEffect(() => {
    if (!chatId) return;
    const controller = new AbortController();
    request(`chats/${chatId}`, undefined, controller.signal).then(data => {
      if (controller.signal.aborted) return;
      setTurns(data.turns);
      setLoadedChatId(chatId);
      setDraft('');
      setError('');
    }).catch(failure => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [chatId, reload]);

  useEffect(() => {
    if (!pendingId || pendingStatus !== 'running') return;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try {
        const data = await request(`chats/${chatId}/turns/${pendingId}`, undefined, controller.signal);
        if (controller.signal.aborted) return;
        setTurns(current => current.map(t => t.turn_id === pendingId ? data : t));
        if (data.status === 'running') timer = setTimeout(poll, 900);
      } catch (failure) {
        if (!controller.signal.aborted) setError(`${failure.message} Use Reconnect to check this chat again.`);
      }
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [chatId, pendingId, pendingStatus]);

  useEffect(() => { if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight; }, [turns]);

  useLayoutEffect(() => {
    const textarea = input.current;
    let width = textarea.clientWidth;
    function resize() {
      textarea.style.height = 'auto';
      const maxHeight = parseFloat(getComputedStyle(textarea).maxHeight);
      textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
      textarea.style.overflowY = textarea.scrollHeight > textarea.clientHeight ? 'auto' : 'hidden';
    }
    resize();
    const observer = new ResizeObserver(() => {
      if (textarea.clientWidth !== width) {
        width = textarea.clientWidth;
        resize();
      }
    });
    observer.observe(textarea);
    return () => observer.disconnect();
  }, [draft]);

  async function send(event) {
    event.preventDefault();
    if (busy || !draft.trim() || activeRequest.current) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setSending(true);
    setError('');
    const message = draft.trim();
    const selectedProvider = provider;
    const turnId = crypto.randomUUID();
    let targetChat = chatId;
    try {
      if (!targetChat) {
        const chat = await request('chats', {}, controller.signal);
        targetChat = chat.chat_id;
      }
      const data = await request('turns', { chat_id: targetChat, turn_id: turnId, message, provider: selectedProvider }, controller.signal);
      setDraft('');
      if (targetChat === chatId) setTurns(current => [...current, data]);
      else setSearchParams({ chat: String(targetChat) });
      const list = await request('chats', undefined, controller.signal);
      setChats(list.chats);
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(failure.message);
        if (targetChat) {
          try {
            const data = await request(`chats/${targetChat}/turns/${turnId}`, undefined, controller.signal);
            setDraft('');
            if (targetChat === chatId) setTurns(current => [...current.filter(t => t.turn_id !== turnId), data]);
            else setSearchParams({ chat: String(targetChat) });
          } catch { /* Reconnect reloads the durable conversation when the service returns. */ }
        }
      }
    } finally { activeRequest.current = null; setSending(false); }
  }

  async function resume(turn, selections) {
    if (chatControlsBusy) return;
    setSending(true); setError('');
    try {
      await request(`chats/${chatId}/turns/${turn.turn_id}/resume`, { selections });
      setTurns(current => current.map(t => t.turn_id === turn.turn_id ? { ...t, status: 'running', choices: {} } : t));
    } catch (failure) { setError(failure.message); }
    finally { setSending(false); }
  }

  async function newConversation() {
    if (chatControlsBusy) return;
    setSending(true); setError('');
    try {
      const chat = await request('chats', {});
      setChats(current => [chat, ...current]);
      setSearchParams({ chat: String(chat.chat_id) });
    } catch (failure) { setError(failure.message); }
    finally { setSending(false); }
  }

  async function deleteConversation(targetChatId) {
    if (targetChatId === chatId || chatControlsBusy) return;
    setDeleting(true);
    setError('');
    try {
      await request('chats/' + targetChatId, undefined, undefined, 'DELETE');
      setChats(current => current.filter(chat => chat.chat_id !== targetChatId));
    } catch (failure) { setError(failure.message); }
    finally { setDeleting(false); }
  }

  async function reconnect() {
    try {
      const data = await request('chats');
      setChats(data.chats);
      setReady(true);
      setReload(value => value + 1);
      setError('');
    } catch (failure) { setError(failure.message); }
  }

  return <div className="assistant-layout">
    <aside className="assistant-sidebar">
      <span className="eyebrow">RESEARCH ASSISTANT</span><h1>Explore your research.</h1>
      <p>Research a relationship, ask about its graph, or focus on specific years.</p>
      <button className="assistant-new" disabled={chatControlsBusy} onClick={newConversation}>＋ New conversation</button>
      <nav className="assistant-chat-list" aria-label="Saved conversations">
        {chats.map(chat => {
          const isCurrent = chat.chat_id === chatId;
          return <div key={chat.chat_id} className="assistant-chat-row">
            <button className="assistant-open-chat" type="button" disabled={chatControlsBusy}
              aria-current={isCurrent ? 'page' : undefined}
              onClick={() => setSearchParams({ chat: String(chat.chat_id) })}>
              <small>Chat {chat.chat_id}</small><span>{chat.title}</span>
            </button>
            <button className="assistant-delete-chat" type="button"
              aria-label={'Delete chat ' + chat.chat_id}
              title={isCurrent ? 'Switch chats before deleting this conversation' : 'Delete conversation'}
              disabled={isCurrent || chatControlsBusy}
              onClick={() => deleteConversation(chat.chat_id)}>&times;</button>
          </div>;
        })}
      </nav>
      <div className="assistant-model"><span className="assistant-model-dot" /><div><strong>AI Assistant</strong>
        <p>{{ auto: 'Auto', gemini: 'Gemini', groq: 'Groq / Qwen' }[provider]} · {selectedConfigured ? 'Configured' : 'Check backend configuration'}</p></div></div>
    </aside>
    <section className="assistant-chat" aria-label="AI Assistant conversation">
      <div className="assistant-scroll" ref={scroll}>
        {loading && <p role="status">Opening your saved conversation…</p>}
        {!loading && !turns.length && <div className="assistant-welcome"><div className="assistant-symbol">↗</div><h2>What would you like to explore?</h2>
          <p>Ask about two concepts and their relationship. Then ask follow-up questions or narrow the years.</p>
          <div className="assistant-examples">{['Research machine learning using random forest.', 'What can you help me research?'].map(example =>
            <button key={example} onClick={() => setDraft(example)}>{example} ↗</button>)}</div></div>}
        {!loading && <div className="assistant-messages">{turns.map(turn => <div className="assistant-turn" key={turn.id}>
          <div className="assistant-user">{turn.message}</div><div className="assistant-answer">
            {turn.text && <p className="assistant-reply">{turn.text}</p>}
            {turn.text && turn.model_calls?.at(-1)?.model && <small>{turn.model_calls.at(-1).model}</small>}
            {turn.outputs.map((output, i) => <Output key={`${turn.id}-${i}`} output={output} />)}
            {turn.status === 'needs_clarification' && <Choices turn={turn} onResume={resume} disabled={chatControlsBusy} />}
            {turn.status === 'running' && <p className="assistant-wait" role="status">{turn.events?.at(-1)?.message || 'Understanding your request…'}</p>}
            {turn.events?.length > 0 && <details className="plan-details"><summary>View progress</summary><ol>{turn.events.map((e, i) => <li key={i}>{e.step}: {e.message}</li>)}</ol></details>}
          </div></div>)}</div>}
        {sending && <p className="assistant-wait" role="status">Saving your request…</p>}
      </div>
      <div className="assistant-compose-area">
        {error && <p className="assistant-error" role="alert">{error} <button onClick={reconnect}>Reconnect</button></p>}
        <form className="assistant-composer" onSubmit={send}>
          <label className="sr-only" htmlFor="research-question">Message</label>
          <textarea ref={input} id="research-question" value={draft} onChange={e => setDraft(e.target.value)} maxLength={2000} rows={1} placeholder="Ask about a relationship or your current results." />
          <div className="assistant-composer-actions">
            <label className="assistant-provider" htmlFor="assistant-provider">
              <span className="sr-only">Model</span>
              <select id="assistant-provider" value={provider} onChange={event => setProvider(event.target.value)}>
                <option value="auto">Auto</option>
                <option value="gemini">Gemini</option>
                <option value="groq">Groq / Qwen</option>
              </select>
            </label>
            <button disabled={busy || !draft.trim()} type="submit" aria-label="Send message">&#8593;</button>
          </div>
        </form>
        <p className="assistant-input-note">Your chats and graphs are saved · Each conversation has its own context</p>
      </div>
    </section>
  </div>;
}
