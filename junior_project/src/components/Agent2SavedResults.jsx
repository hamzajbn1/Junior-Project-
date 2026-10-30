import { useEffect, useState } from 'react';
import Agent3Result from './Agent3Result';

async function loadSavedResults(signal) {
  const response = await fetch('/api/agent2/saved-results', { signal });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Could not read SQLite results.');
  return body;
}

export default function Agent2SavedResults({ savedAt }) {
  const [database, setDatabase] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    loadSavedResults(controller.signal)
      .then(body => {
        if (!controller.signal.aborted) { setDatabase(body); setError(''); setLoading(false); }
      })
      .catch(error => {
        if (!controller.signal.aborted) {
          setError(error.message || 'Cannot reach the backend to read SQLite.'); setLoading(false);
        }
      });
    return () => controller.abort();
  }, [savedAt, refresh]);

  return (
    <section aria-labelledby="a2-sqlite" style={{ marginTop: 32, borderTop: '1px solid #ccc', paddingTop: 16 }}>
      <h2 id="a2-sqlite">Results read back from SQLite</h2>
      <p>Run research above. Every finished run is saved automatically. This section loads all saved runs from the database file, including after a backend restart.</p>
      <button type="button" disabled={loading} onClick={() => { setLoading(true); setRefresh(value => value + 1); }}>
        {loading ? 'Reading SQLite…' : 'Reload all saved results'}
      </button>
      {error && <p role="alert">{error}</p>}
      {database && <>
        <p>SQLite file: <code>{database.database_path}</code></p>
        <p role="status">Saved runs: {database.count}. All records below were read from SQLite.</p>
        {!database.count && <p>No saved results yet. Run a research search to create the first record.</p>}
        {database.results.map(({ saved_at: savedTime, snapshot }) => {
          const result = snapshot.result;
          return <details key={snapshot.task_id} style={{ marginBottom: 16 }}>
            <summary>{snapshot.request.first_concept} → {snapshot.request.connection} → {snapshot.request.second_concept} — {snapshot.status} — saved {savedTime}</summary>
            <p>Task ID: <code>{snapshot.task_id}</code></p>
            <p>Result ID: <code>{result.result_id || 'Not generated because research failed early'}</code></p>
            <p>Requested years: {snapshot.request.start_year ?? 'Unbounded'} to {snapshot.request.end_year ?? 'Unbounded'}. Validation: {result.validation?.passed ? 'Passed' : 'Not passed / not performed'}.</p>
            {result.error && <p>Research error: {result.error.message}</p>}
            {result.message && <p>{result.message}</p>}
            {result.yearly_counts?.length > 0 && <table style={{ maxWidth: 480, width: '100%', textAlign: 'left' }}>
              <caption>Yearly counts loaded from SQLite</caption>
              <thead><tr><th scope="col">Year</th><th scope="col">Papers</th></tr></thead>
              <tbody>{result.yearly_counts.map(row => <tr key={row.year}><td>{row.year}</td><td>{row.papers ?? 'Unknown — incomplete coverage'}</td></tr>)}</tbody>
            </table>}
            {result.warnings?.length > 0 && <ul>{result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
            <Agent3Result taskId={snapshot.task_id} result={result} saved />
            <details><summary>All saved fields: request, result, supporting IDs, coverage, sources and progress</summary>
              <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(snapshot, null, 2)}</pre>
            </details>
          </details>;
        })}
      </>}
    </section>
  );
}
