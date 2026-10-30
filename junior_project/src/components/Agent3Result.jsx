import { useEffect, useId, useRef, useState } from 'react';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

function ResultChart({ spec }) {
  const canvas = useRef(null);
  useEffect(() => {
    const chart = new Chart(canvas.current, {
      type: spec.type,
      data: {
        labels: spec.labels,
        datasets: [{
          label: 'Distinct supporting papers', data: spec.values,
          borderColor: '#365e50', backgroundColor: '#365e50',
          borderWidth: 2, tension: 0, spanGaps: false,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: spec.x_label } },
          y: { beginAtZero: true, title: { display: true, text: spec.y_label }, ticks: { precision: 0 } },
        },
      },
    });
    return () => chart.destroy();
  }, [spec]);
  return <>
    <p>{spec.type === 'bar' ? 'Bar chart' : 'Line chart'} · {spec.span_years} years in the received scope.</p>
    <div style={{ height: 300, maxWidth: 900 }}>
      <canvas ref={canvas} role="img" aria-label="Agent 3 chart of observed supporting papers by year. Exact values are listed below." />
    </div>
    <details><summary>View exact chart values</summary>
      <table style={{ width: '100%', maxWidth: 480, textAlign: 'left' }}>
        <caption>Original annual counts received from Agent 2</caption>
        <thead><tr><th scope="col">Publication year</th><th scope="col">Supporting papers</th></tr></thead>
        <tbody>{spec.labels.map((year, index) => <tr key={year}>
          <td>{year}</td><td>{spec.values[index] ?? 'Unknown — incomplete coverage'}</td>
        </tr>)}</tbody>
      </table>
    </details>
  </>;
}


export default function Agent3Result({ taskId, result, saved = false }) {
  const heading = useId();
  const [response, setResponse] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = useRef(null);
  useEffect(() => () => active.current?.abort(), []);

  const eligible = ['complete', 'partial'].includes(result.status)
    && result.validation?.passed && result.yearly_counts?.some(row => row.papers != null);

  async function explain() {
    if (active.current || !eligible) return;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true); setError(''); setResponse(null);
    const timer = setTimeout(() => controller.abort(), 245000);
    try {
      const reply = await fetch('/api/agent3/explain', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId }), signal: controller.signal,
      });
      let body;
      try { body = await reply.json(); }
      catch { throw new Error('Agent 3 returned an unreadable response.'); }
      if (active.current !== controller) return;
      if (body.task_id && body.task_id !== taskId) throw new Error('The explanation belongs to a different research run.');
      if (body.chart?.result_id && body.chart.result_id !== result.result_id) {
        throw new Error('The chart belongs to a different research result.');
      }
      if (!reply.ok && body.status !== 'explanation_failed') {
        throw new Error(typeof body.error === 'string' ? body.error : body.error?.message || 'Agent 3 could not explain this run.');
      }
      setResponse(body);
      if (!reply.ok) setError(body.error?.message || 'The explanation failed.');
    } catch (failure) {
      if (active.current === controller) {
        setError(failure.name === 'AbortError' ? 'Waiting for the explanation stopped. You can retry.'
          : failure instanceof TypeError ? 'Cannot reach Agent 3. Make sure the backend is running.' : failure.message);
      }
    } finally {
      clearTimeout(timer);
      if (active.current === controller) { active.current = null; setBusy(false); }
    }
  }

  return <section aria-labelledby={heading} style={{ marginTop: 24, padding: 16, border: '1px solid #ccc' }}>
    <h2 id={heading}>Agent 3: explanation and chart</h2>
    <p>{result.request?.first_concept} → {result.relationship?.predicate || result.request?.connection} → {result.request?.second_concept}</p>
    <p>{saved ? 'Explain this result saved in SQLite.' : 'Explain the result from this Agent 2 run.'} General graph description only.</p>
    <button type="button" disabled={busy || !eligible} onClick={explain}>
      {busy ? 'Preparing the explanation…' : response || error ? 'Retry Agent 3 explanation' : 'Explain with Agent 3'}
    </button>
    {!eligible && <p>Agent 3 needs a validated complete or partial result with at least one known yearly count.</p>}
    {busy && <p role="status">Preparing graph facts and asking Gemini for a short explanation…</p>}
    {error && <p role="alert">{error}</p>}
    {response && <>
      {response.explanation && <>
        <p role="status">Explanation complete · {response.model}.</p>
        <div style={{ whiteSpace: 'pre-wrap' }}>{response.explanation}</div>
      </>}
      {response.status === 'explanation_failed' && <p>The validated chart is shown below. No AI explanation was accepted; retry when Gemini is available.</p>}
      {response.message && <p>{response.message}</p>}
      {response.chart && <ResultChart spec={response.chart} />}
      {response.warnings?.length > 0 && <ul aria-label="Coverage warnings">{response.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
      {response.retrieved_at && <p>Research sources: CS-KG and OpenAlex. Retrieved: {response.retrieved_at}.</p>}
      <details><summary>Agent 3 execution and returned data</summary>
        <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(response, null, 2)}</pre>
      </details>
    </>}
  </section>;
}
