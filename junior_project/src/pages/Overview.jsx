import {useEffect, useRef, useState} from 'react';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

async function api (path, signal) {
  let response;
  try {
    response = await fetch(`/api/${path}`, { signal });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Cannot reach the research service. Make sure it is running, then try again.');
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error('The research service sent an unreadable answer. Please try again.');
  }
  if (!response.ok) throw new Error(body.error || 'The research service is unavailable.');
  return body;
}

const emptyConcept = () => ({ text: '', selected: null, candidates: [], status: 'idle', message: ''});

/* Searching costs several seconds, so it runs when the researcher asks for it
- Enter or the Search button never on every keystroke. */
function ConceptInput({ id, label, placeholder, value, onEdit, onSearch, onSelect}) {
  return (
    <div className="concept-field">
      <label htmlFor={id}>{label}</label>
      <div className="concept-row">
        <input 
          id={id}
          value={value.text}
          placeholder={placeholder}
          autoComplete="off"
          aria-describedby={`${id}-status`}
          onChange={event => onEdit(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter') { event.preventDefault(); onSearch(); }
          }}
        />
        <button 
          type="button"
          className="find-button"
          onClick={onSearch}
          disabled={value.text.trim().length < 2 || value.status === 'loading'}
        >
          {value.status === 'loading' ? "...": "Search"}
        </button>
      </div>
      
      <div
        id={`${id}-status`}
        className={`field-status ${value.status === 'error' ? 'error-text' : ''}`}
        aria-live="polite"  
      >
        {value.selected 
          ? <span className="resolved">✓ {value.selected.label}<small>{value.selected.name}</small></span>
          : value.status === 'loading' ? 'Searching the knowledge graph...'
          : value.message || 'Type a concept, then press Enter'}
      </div>

      {!value.selected && value.candidates.length > 0 && (
        <ul className="candidates" aria-label={`${label} matches`}>
          {value.candidates.map(candidate => (
            <li key={candidate.id}>
              <button type="button" onClick={() => onSelect(candidate)}>
                <span>{candidate.label}</span>
                <small>{candidate.name} · {candidate.match === 'exact' ? 'Exact match' : 'Suggested match'}</small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TrendChart({result}){
  const canvas = useRef(null);

  useEffect(() => {
    const chart = new Chart(canvas.current, {
      type: 'line',
      data: {
        labels: result.data.map(row => row.label),
        datasets: [{
          label: 'Supporting papers',
          data: result.data.map(row => row.papers),
          borderColor: '#365e50',
          backgroundColor: '#365e50',
          borderWidth: 2.5,
          pointRadius: 4,
          pointHoverRadius: 7,
          tension: 0,
          fill: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            title: { display: true, text: result.bucket_size > 1 ? 'Publication period' : 'Publication year' },
            grid: { display: false },
          },
          y: {
            beginAtZero: true,
            title: { display: true, text: 'Number of supporting papers' },
            ticks: { precision: 0 },
            grid: { color: '#edf0ec' },
          },
        },
      },
    });
    return () => chart.destroy();
  }, [result]);

  return (
    <>
      <div className="chart-wrap">
        <canvas ref={canvas} role="img" aria-label="Supporting papers by publication period. Exact values are in the table below." />
      </div>
      <details className="chart-table">
        <summary>View the numbers</summary>
        <table>
          <thead>
            <tr><th>{result.bucket_size > 1 ? 'Period' : 'Year'}</th><th>Supporting papers</th></tr>
          </thead>
          <tbody>
            {result.data.map(row => (
              <tr key={row.label}><td>{row.label}</td><td>{row.papers}</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </>
  );
}

export default function Overview() {
  const [concepts, setConcepts] = useState([emptyConcept(), emptyConcept()]);
  const [connections, setConnections] = useState([]);
  const [connection, setConnection] = useState('');
  const [configError, setConfigError] = useState('');
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState('');

  const searches = useRef([null, null]);
  const trendSearch = useRef(null);
  const runId = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    api('connections', controller.signal)
      .then(body => setConnections(body.connections))
      .catch(err => { if(err.name !== 'AbortError') setConfigError(err.message); });

      const active = searches.current;
      return () => {
        controller.abort();
        trendSearch.current?.abort();
        active.forEach(item => item?.abort());
      };
  }, []);

  function patch(index, changes) {
    setConcepts(current => current.map((item, i) => (i === index ? { ...item, ...changes} : item)));
  }


  // Any edit invalidates the chart it belong to the previos concepts.
  function clearResult(){
    runId.current += 1;
    trendSearch.current?.abort();
    setResult(null);
    setError('');
    setStatus('idle');
  }

  function editConcept(index, text){
    clearResult();
    searches.current[index]?.abort();
    patch(index, {  ...emptyConcept(), text});
  }

  async function searchConcept(index){
    const text = concepts[index].text.trim();
    if (text.length < 2) return;

    clearResult();
    searches.current[index]?.abort();
    const controller = new AbortController();
    searches.current[index] = controller;  
    patch(index, { status: 'loading', candidates: [], selected: null, message: '' });

    try{
      const body = await api(`entities?q=${encodeURIComponent(text)}`, controller.signal);
      if (searches.current[index] !== controller) return;
      patch(index, {
        status: 'ready',
        candidates: body.candidates,
        selected: body.selected, 
        message: body.candidates.length
          ? 'Choose the concept you mean.'
          : 'No concept in CS-KG matches those words. Try a different spelling or a fuller name.',
      });
    } catch (err){
      if (err.name === 'AbortError' || searches.current[index] !== controller) return;
      patch(index, { status: 'error', message: err.message});
    }
  }

  function selectConcept(index, selected){
    clearResult();
    searches.current[index]?.abort();
    patch(index, { selected, candidates: [], status: 'ready', message: '' });
  }
  
  async function showTrend(event){
    event?.preventDefault();
    if (!concepts.every(item => item.selected) || !connection) return;

    clearResult();
    const id = runId.current;
    const controller = new AbortController();
    trendSearch.current = controller;
    setStatus('loading');

    try {
      const params = new URLSearchParams({
        s: concepts[0].selected.id,
        p: connection,
        o: concepts[1].selected.id,
      });
      const body = await api(`relationship?${params}`, controller.signal);
      if (id !== runId.current) return;
      setResult(body);
      setStatus('ready');
    } catch (err) {
      if (err.name === 'AbortError' || id !== runId.current) return;
      setError(err.message);
      setStatus('error');
    }
  }

  const ready = concepts.every(item => item.selected) && connection;
  const friendly = connections.find(item => item.id === connection)?.label;
  const title = ready
    ? `${concepts[0].selected.label} → ${friendly} → ${concepts[1].selected.label}`
    : 'Explore a connection';

    return(
      <div className="overview-layout">
        <aside className="search-panel" aria-label="Relationship search">
          <div className="panel-intro">
            <span className="eyebrow">Your Research</span>
            <h1>Connect two concepts</h1>
            <p>Explore how a research relationship develops over time.</p>
          </div>

          <form onSubmit={showTrend}>
            <ConceptInput
              id="first-concept" label="First concept" placeholder="e.g. machine learning"
              value={concepts[0]}
              onEdit={text => editConcept(0, text)}
              onSearch={() => searchConcept(0)}
              onSelect={item => selectConcept(0, item)}
            />

            <div className="connection-field">
              <label htmlFor="connection">Connection</label>
              <select
                id="connection"
                value={connection}
                onChange={event => { clearResult(); setConnection(event.target.value); }}
                disabled={!connections.length}
              >
                <option value="">Select a connection</option>
                {connections.map(item => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
              {configError && (
                <p className="error-text" role="alert">
                  {configError}{' '}
                  <button className="text-button" type="button" onClick={() => window.location.reload()}>Retry</button>
                </p>
              )}
            </div>

            <ConceptInput
              id="second-concept" label="Second concept" placeholder="e.g. random forest"
              value={concepts[1]}
              onEdit={text => editConcept(1, text)}
              onSearch={() => searchConcept(1)}
              onSelect={item => selectConcept(1, item)}
            />

            <button className="primary-button" type="submit" disabled={!ready || status === 'loading'}>
              {status === 'loading' ? 'finding evidence...' : 'Show trend'}
              <span aria-hidden="true">→</span>
            </button>
          </form>
          
          <div className="sidebar-note">
            <span className="small-dot" aria-hidden="true" />
            <p>Start with two concepts.<br />Follow the evidence between them.</p>
          </div>
        </aside>

        <section className='results-panel' aria-label='Relationship trend'>
          <div className="results-heading">
            <div>
              <span className="eyebrow">OVERVIEW</span>
              <h2>Research connections</h2>
              <p>Discover the papers behind a direct relationship.</p>
            </div> 
            <span className="source-tag">CS-KG · OpenAlex</span>
          </div>

          <section className="trend-card" aria-labelledby="trend-title" aria-busy={status === 'loading'}>
            <div className="chart-heading">
              <div>
                <span className="eyebrow">PUBLICATIONS OVER TIME</span>
                <h3 id="trend-title">{title}</h3>
              </div>
              {result?.total_papers > 0 && (
                <span className="paper-count">
                  {result.total_papers.toLocaleString()}<small>supporting papers</small>
                </span>
              )}
            </div>

            {status === 'idle' && (
              <div className="empty-state">
                <div className="empty-icon" aria-hidden="true">
                  <svg viewBox="0 0 100 64">
                    <path d="M8 8v48h84M20 42l18-14 17 6 24-23" />
                    <circle cx="20" cy="42" r="3" /><circle cx="38" cy="28" r="3" />
                    <circle cx="55" cy="34" r="3" /><circle cx="79" cy="11" r="3" />
                  </svg>
                </div>
                <h4>Your next insight starts here</h4>
                <p>Choose two concepts and a connection,<br />then show their research trend.</p>
                <span className="empty-caption">Each point represents the papers published in that period.</span>
              </div>
            )}

            {status === 'loading' && (
              <div className="empty-state" role="status">
                <span className='spinner' />
                <h4>Following the evidence</h4>
                <p>Finding the relationship in CS-KG, then its papers in OpenAlex.<br />This usually takes a few seconds.</p>
              </div>
            )}

            {status === 'error' &&(
              <div className="empty-state" role="alert">
                <h4>We couldn't load this trend</h4>
                <p>{error}</p>
                <button className="secondary-button" type="button" onClick={showTrend}>Try again</button>
              </div>
            )}

            {status === 'ready' && result?.status === 'no_relationship' && (
              <div className="empty-state" role="status">
                <h4>No papers record this connection</h4>
              <p>
                CS-KG holds no statement linking these two concepts in this way.<br />
                Try one of the other connections.
              </p>
              </div>
            )}

            {status === 'ready' && result?.status === 'no_years' && (
              <div className="empty-state" role="status">
                <h4>Publication years are unavailable</h4>
                <p>The connection has supporting papers, but none of their publication years could be retrieved.</p>
              </div>
            )}

            {status === 'ready' && result?.status === 'ok' && <TrendChart result={result} />}

            {status === 'ready' && result?.notes?.length > 0 && (
              <div className="result-notice" role="status">
                {result.notes.map(note => <p key={note}>{note}</p>)}
              </div>
            )}

            <div className="chart-footer">
              <span><span className="legend-dot" />Distinct supporting papers</span>
              <span>Direct connection · First → Second</span>
            </div>
          </section>

          <p className="results-note">
          A connection is supported by papers that record that exact relationship between both concepts.
          CS-KG covers computer-science literature published roughly between 2010 and 2022, so later years will not appear.
        </p>
      </section>
    </div>
  );
}
        















