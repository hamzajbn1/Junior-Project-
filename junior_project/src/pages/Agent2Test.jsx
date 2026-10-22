import { useEffect, useRef, useState } from 'react';

async function researchApi(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api/${path}`, options);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Cannot reach the backend. Start it with Junior Test’s Python environment.');
  }
  let body;
  try { body = await response.json(); }
  catch { throw new Error('The backend returned an unreadable answer.'); }
  if (!response.ok) throw new Error(body.error || 'The request failed.');
  return body;
}

const initialForm = { first_concept: 'machine learning', connection: 'usesMethod', second_concept: 'random forest', start_year: '', end_year: '' };

export default function Agent2Test() {
  const [form, setForm] = useState(initialForm);
  const [connections, setConnections] = useState([]);
  const [taskId, setTaskId] = useState('');
  const [snapshot, setSnapshot] = useState(null);
  const [selections, setSelections] = useState({});
  const [busy, setBusy] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [error, setError] = useState('');
  const submitting = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    researchApi('connections', { signal: controller.signal }).then(body => setConnections(body.connections))
      .catch(error => { if (error.name !== 'AbortError') setError(error.message); });
    return () => { controller.abort(); submitting.current?.abort(); };
  }, []);

  useEffect(() => {
    if (!taskId || !busy) return;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try {
        const body = await researchApi(`agent2/tasks/${taskId}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setSnapshot(body);
        if (body.status === 'running') timer = setTimeout(poll, 1000);
        else setBusy(false);
      } catch (error) {
        if (error.name !== 'AbortError') {
          setError(error.message);
          setBusy(false);
        }
      }
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [taskId, busy]);

  function edit(name, value) {
    setForm(previous => ({ ...previous, [name]: value }));
    setSnapshot(null);
    setSelections({});
    setTaskId('');
    setError('');
  }

  async function submit(event) {
    event.preventDefault();
    setError('');
    setSnapshot(null);
    setSelections({});
    setTaskId('');
    setBusy(true);
    const controller = new AbortController();
    submitting.current = controller;
    const payload = { ...form,
      start_year: form.start_year === '' ? null : Number(form.start_year),
      end_year: form.end_year === '' ? null : Number(form.end_year) };
    try {
      const body = await researchApi('agent2/tasks', { method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (!controller.signal.aborted) setTaskId(body.task_id);
    } catch (error) {
      if (error.name !== 'AbortError') { setError(error.message); setBusy(false); }
    }
  }

  async function resume() {
    setResuming(true);
    setError('');
    const controller = new AbortController();
    submitting.current = controller;
    try {
      await researchApi(`agent2/tasks/${taskId}/resume`, { method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ selections }) });
      if (!controller.signal.aborted) setBusy(true);
    } catch (error) {
      if (error.name !== 'AbortError') { setError(error.message); setBusy(false); }
    } finally {
      if (!controller.signal.aborted) setResuming(false);
    }
  }

  const result = snapshot?.result;
  const ambiguous = Object.entries(result?.resolution || {}).filter(([, value]) => !value.selected && value.candidates.length);
  const canResume = ambiguous.every(([side]) => selections[side]);

  return (
    <section style={{ padding: 16, overflowWrap: 'anywhere' }} aria-labelledby="agent2-title">
      <h1 id="agent2-title">Agent 2 Test</h1>
      <p>Live CS-KG → OpenAlex → counts → validation. LangGraph workflow; no LLM.</p>
      <form onSubmit={submit} style={{ maxWidth: 640 }}>
        <fieldset disabled={busy || resuming}>
          <legend>Research request</legend>
          <p><label htmlFor="a2-first">First concept</label>
            <input id="a2-first" required minLength={2} maxLength={200} value={form.first_concept}
              onChange={event => edit('first_concept', event.target.value)} /></p>
          <p><label htmlFor="a2-connection">Connection</label>
            <select id="a2-connection" value={form.connection} onChange={event => edit('connection', event.target.value)}>
              {connections.map(item => <option key={item.id} value={item.id}>{item.label} ({item.id})</option>)}
            </select></p>
          <p><label htmlFor="a2-second">Second concept</label>
            <input id="a2-second" required minLength={2} maxLength={200} value={form.second_concept}
              onChange={event => edit('second_concept', event.target.value)} /></p>
          <p><label htmlFor="a2-start">Start year (optional)</label>
            <input id="a2-start" type="number" min="1000" max={new Date().getFullYear()} step="1" value={form.start_year}
              onChange={event => edit('start_year', event.target.value)} /></p>
          <p><label htmlFor="a2-end">End year (optional)</label>
            <input id="a2-end" type="number" min={form.start_year || '1000'} max={new Date().getFullYear()} step="1" value={form.end_year}
              onChange={event => edit('end_year', event.target.value)} /></p>
          <p>Leave years blank to use all available publication years, as in Overview.</p>
          <button type="submit" disabled={!connections.length}>{busy ? 'Running…' : 'Run research'}</button>
        </fieldset>
      </form>
      <p role="status" aria-live="polite">{busy ? 'Research is running. Progress appears below.' : snapshot ? `Status: ${snapshot.status}` : 'Ready. No research request has run yet.'}</p>
      {error && <p role="alert">{error}</p>}

      {snapshot?.events.length > 0 && <details open><summary>Step progress and attempts</summary>
        <ol>{snapshot.events.map((event, index) => <li key={index}>
          {event.step}: {event.status} — {event.message}
          {event.attempt ? ` (attempt ${event.attempt}/${event.max_attempts})` : ''}
        </li>)}</ol>
      </details>}

      {result && <section aria-labelledby="a2-result">
        <h2 id="a2-result">Research result</h2>
        {result.message && <p>{result.message}</p>}
        {result.error && <p role="alert">{result.error.message}</p>}
        {Object.entries(result.resolution || {}).map(([side, value]) => value.selected && <p key={side}>
          {side === 'first' ? 'First' : 'Second'} concept: {value.selected.label} — <code>{value.selected.id}</code>
        </p>)}
        {result.relationship?.predicate && <p>Directed connection: {result.relationship.subject} → {result.relationship.predicate} → {result.relationship.object}</p>}
        {snapshot.status === 'needs_clarification' && <fieldset disabled={busy || resuming}>
          <legend>Select the intended concepts</legend>
          {ambiguous.map(([side, value]) => <p key={side}>
            <label htmlFor={`a2-choice-${side}`}>{side === 'first' ? 'First' : 'Second'} concept</label>
            <select id={`a2-choice-${side}`} value={selections[side] || ''}
              onChange={event => setSelections(previous => ({ ...previous, [side]: event.target.value }))}>
              <option value="">Choose a returned candidate</option>
              {value.candidates.map(candidate => <option key={candidate.id} value={candidate.id}>{candidate.label} ({candidate.name})</option>)}
            </select>
          </p>)}
          <button type="button" disabled={!canResume} onClick={resume}>Continue with choices</button>
        </fieldset>}
        <p>Validation: {result.validation?.passed ? 'Passed' : result.validation?.performed === false ? 'Not performed — research did not reach T6.' : 'Not passed'}</p>
        {result.counted_papers != null && <p>Counted papers in range: {result.counted_papers}. Mapped supporting papers before year filtering: {result.total_supporting_papers}.</p>}
        {result.yearly_counts?.length > 0 && <table style={{ width: '100%', maxWidth: 480, textAlign: 'left' }}>
          <caption>Distinct supporting papers per publication year</caption>
          <thead><tr><th scope="col">Year</th><th scope="col">Papers</th></tr></thead>
          <tbody>{result.yearly_counts.map(row => <tr key={row.year}><td>{row.year}</td><td>{row.papers ?? 'Unknown — incomplete coverage'}</td></tr>)}</tbody>
        </table>}
        {result.validation?.passed && !result.yearly_counts?.length && <p>No dated papers are available in this range. Check coverage below.</p>}
        {result.warnings?.length > 0 && <ul>{result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
        {result.coverage && <details open><summary>Coverage</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(result.coverage, null, 2)}</pre></details>}
        {result.counted_paper_ids?.length > 0 && <details><summary>Counted paper IDs (selected years)</summary>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{result.counted_paper_ids.join(', ')}</pre>
        </details>}
        {result.supporting_paper_ids?.length > 0 && <details><summary>Supporting paper IDs (before year filtering)</summary>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{result.supporting_paper_ids.join(', ')}</pre>
        </details>}
        {result.source && <p>Sources: CS-KG ({result.source.graph}), OpenAlex. Retrieved: {result.retrieved_at}. Elapsed: {result.elapsed_seconds}s.</p>}
        <details><summary>Full result JSON, including supporting IDs</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(result, null, 2)}</pre></details>
      </section>}
    </section>
  );
}
