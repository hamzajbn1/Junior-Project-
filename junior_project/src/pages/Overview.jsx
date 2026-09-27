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

function countryLabel(code){ 
  try {
    return new Intl.DisplayNames(['en'], {type: 'region'}).of(code) || code;
  } catch {
    return code;
  }
}

function tooltipLines(text){
  return text.match(/.{1,48}(?:\s|$)|\S{1,48}/g)?.map(line => line.trim()) || [text];
}

function InsightChart({id, title, rows, metric, description, coverage, cited = false}) {
  const canvas = useRef(null);

  useEffect(() => {
    if(!rows.length) return;
    const chart = new Chart(canvas.current, {
      type: 'bar',
      data:{
        labels: rows.map(row => row.label),
        datasets: [{
          label: metric,
          data: rows.map(row => row.value),
          backgroundColor: rows.map(row => row.is_other ? '#98aa9e' : '#365e50'),
          borderRadius: 4,
          maxBarThickness: 25,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: {
            title: items => tooltipLines(rows[items[0].dataIndex].label),
            afterLabel: context => cited
              ? `Publication year: ${rows[context.dataIndex].publication_year ?? 'Unavailable'}` : '',
          } },
        },
        scales: {
          x: {
            beginAtZero: true,
            suggestedMax: 1,
            title: { display: true, text: metric },
            ticks: { precision: 0 },
            grid: { color: '#edf0ec' },
          },
          y: {
            grid: { display: false },
            ticks: {
              autoSkip: false,
              callback: function(value) {
                const label = this.getLabelForValue(value);
                const limit = this.chart.width < 450 ? 19 : 38;
                return label.length > limit ? `${label.slice(0, limit - 1)}…` : label;
              },
            },
          },
        },
      },
    });
    return () => chart.destroy();
    }, [rows, metric, cited]);

    return (
      <section className={`trend-card insight-card ${cited ? 'cited-card' : ''}`} aria-labelledby={id}>
        <div className="chart-heading"><h3 id={id}>{title}</h3></div>
        {rows.length > 0 ? (
          <div className="chart-wrap insight-chart-wrap">
            <canvas ref={canvas} role="img" aria-label={`${title}, measured in ${metric.toLowerCase()}. Full labels and exact values are in the table below.`} />
          </div>
        ) : (
          <p className="insight-empty" role="status">This metadata is unavailable for the supporting papers retrieved.</p>
        )}
        <p className="insight-description">{description}</p>
        {coverage && <p className="insight-coverage">{coverage}</p>}
        {rows.length > 0 && (
          <details className="chart-table">
            <summary>View full {cited ? 'titles' : 'names'} and numbers</summary>
            <table>
              <caption className="sr-only">{title}</caption>
              <thead>
                <tr><th scope="col">{cited ? 'Paper' : 'Name'}</th>
                {cited && <th scope="col">Year</th>}
                <th scope="col">{metric}</th></tr>
              </thead>
              <tbody>
              {rows.map(row => (
                <tr key={row.id}>
                  <th scope="row">
                    {cited && /^https:\/\/openalex\.org\/W\d+$/.test(row.url || '')
                      ? <a href={row.url} target="_blank" rel="noopener noreferrer">{row.label}</a>
                      : row.label}
                  </th>
                  {cited && <td>{row.publication_year ?? 'Unavailable'}</td>}
                  <td>{row.value.toLocaleString()}</td>
                </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
    </section>
    );
}

function SupportingInsights({result}){
  const coverage = result.coverage || {};
  const missing = (count, field) => count > 0
    ? `${count} supporting paper${count === 1 ? ' lacks' : 's lack'} available ${field} metadata and ${count === 1 ? 'is' : 'are'} excluded here.` : '';
  const countryCoverage = [
    missing(coverage.missing_country_papers, 'affiliation-country'),
    coverage.partial_country_papers > 0
     ? `${coverage.partial_country_papers} papers have some authors without country information; counts may be incomplete.` : '',
    coverage.possibly_truncated_authorship_papers > 0
      ? `${coverage.possibly_truncated_authorship_papers} papers reach OpenAlex’s 100-author limit; additional countries may be missing.` : '',
  ].filter(Boolean).join(' ');
  return(
    <div className="insights-grid">
      <InsightChart
        id="venue-title" title="Top publication venues" metric="Distinct supporting papers"
        rows={(result.venue_data || []).map(row => ({ ...row, id: row.id || 'other-venues', value: row.papers }))}
        description="Counts distinct supporting papers by their primary journal or conference source. Other venues combines the remaining known venues."
        coverage={missing(coverage.missing_venue_papers, 'publication-venue')}
      />
      <InsightChart
        id="country-title" title="Top countries by author affiliation" metric="Distinct supporting papers"
        rows={(result.country_data || []).map(row => ({ ...row, id: row.country_code || 'other-countries',
          label: row.is_other ? row.label : countryLabel(row.country_code), value: row.papers }))}
        description="Each paper counts once for each represented author-affiliation country. Multinational papers appear under multiple countries, so totals can exceed the number of papers. Other countries sums the remaining country counts."
        coverage={countryCoverage}
      />
      <InsightChart
        id="cited-title" title="Top five most-cited supporting papers" metric="Citations" cited
        rows={(result.top_cited_papers || []).map(row => ({ ...row, label: row.title, value: row.cited_by_count }))}
        description="Ranked by OpenAlex citation counts, not views or downloads. Full titles, publication years, and paper links are available below."
        coverage={missing(coverage.missing_citation_papers, 'citation-count')}
      />
    </div>
  )
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

          {status ===  'ready' && ['ok', 'no_years'].includes(result?.status) && (
            <SupportingInsights result={result} />
          )}

          <p className="results-note">
          A connection is supported by papers that record that exact relationship between both concepts.
          CS-KG covers computer-science literature published roughly between 2010 and 2022, so later years will not appear.
        </p>
      </section>
    </div>
  );
}
        















