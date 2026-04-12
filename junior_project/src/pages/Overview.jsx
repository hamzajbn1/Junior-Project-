import { useState, useEffect, useRef } from 'react';
import { Chart, registerables } from 'chart.js';
import ChartDataLabels from 'chartjs-plugin-datalabels';
import OVERVIEW_MOCK_DATA from '../data/overviewMockData';

Chart.register(...registerables, ChartDataLabels);

function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}

function getOverviewData() {
  return new Promise((resolve) => {
    setTimeout(() => resolve(OVERVIEW_MOCK_DATA), 450);
  });
}

export default function Overview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Loading overview data...');
  const [searchValue, setSearchValue] = useState('Machine Learning');

  const mainChartRef = useRef(null);
  const citationChartRef = useRef(null);
  const topicsChartRef = useRef(null);
  const authorsChartRef = useRef(null);
  const orgsChartRef = useRef(null);

  const mainChartInstance = useRef(null);
  const citationChartInstance = useRef(null);
  const topicsChartInstance = useRef(null);
  const authorsChartInstance = useRef(null);
  const orgsChartInstance = useRef(null);

  useEffect(() => {
    getOverviewData()
      .then((d) => {
        setData(d);
        setStatus('Overview loaded successfully using prototype data. This page is ready for real back-end integration.');
      })
      .catch((err) => {
        setError(err.message || 'Failed to load overview data.');
        setStatus('Overview failed to load.');
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!data) return;

    // Destroy previous instances
    [mainChartInstance, citationChartInstance, topicsChartInstance, authorsChartInstance, orgsChartInstance].forEach(r => {
      if (r.current) { r.current.destroy(); r.current = null; }
    });

    const pc = data.publications_citations;
    const ct = data.citation_trend;

    // Main chart
    mainChartInstance.current = new Chart(mainChartRef.current, {
      data: {
        labels: pc.map(r => r.year),
        datasets: [
          {
            type: 'bar',
            label: 'Publications',
            data: pc.map(r => r.publications),
            backgroundColor: 'rgba(125,181,216,0.78)',
            borderColor: 'rgba(125,181,216,1)',
            borderWidth: 1,
            yAxisID: 'y'
          },
          {
            type: 'line',
            label: 'Citations',
            data: pc.map(r => r.citations),
            borderColor: '#1f2937',
            backgroundColor: '#1f2937',
            borderWidth: 2,
            pointRadius: 4,
            tension: 0.25,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom' },
          datalabels: { display: false }
        },
        scales: {
          y: { beginAtZero: true, title: { display: true, text: 'Publications' } },
          y1: { beginAtZero: true, position: 'right', title: { display: true, text: 'Citations' }, grid: { drawOnChartArea: false } },
          x: { title: { display: true, text: 'Year' } }
        }
      }
    });

    // Citation trend chart
    citationChartInstance.current = new Chart(citationChartRef.current, {
      type: 'line',
      data: {
        labels: ct.map(r => r.year),
        datasets: [{
          label: 'Average Citations per Paper',
          data: ct.map(r => r.avg_citations),
          borderColor: '#2e5f88',
          backgroundColor: 'rgba(46,95,136,0.15)',
          borderWidth: 2,
          pointRadius: 4,
          tension: 0.28,
          fill: true
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom' },
          datalabels: { display: false }
        },
        scales: {
          y: { beginAtZero: true, title: { display: true, text: 'Average Citations' } },
          x: { title: { display: true, text: 'Year' } }
        }
      }
    });

    // Horizontal bar helper
    const hbar = (ref, instanceRef, rows, label, color) => {
      instanceRef.current = new Chart(ref.current, {
        type: 'bar',
        data: {
          labels: rows.map(r => r.name),
          datasets: [{
            data: rows.map(r => r.papers !== undefined ? r.papers : r.value),
            backgroundColor: color,
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          indexAxis: 'y',
          plugins: {
            legend: { display: false },
            datalabels: {
              anchor: 'end',
              align: 'right',
              color: '#17212b',
              font: { weight: '700' },
              formatter: v => v
            }
          },
          scales: {
            x: { beginAtZero: true, title: { display: true, text: label } },
            y: { ticks: { autoSkip: false } }
          }
        }
      });
    };

    hbar(topicsChartRef, topicsChartInstance, data.top_topics, 'Number of Publications', 'rgba(125,181,216,0.82)');
    hbar(authorsChartRef, authorsChartInstance, data.top_authors.map(a => ({ name: a.name, papers: a.papers })), 'Number of Publications', 'rgba(46,95,136,0.82)');
    hbar(orgsChartRef, orgsChartInstance, data.top_organizations.map(o => ({ name: o.name, papers: o.papers })), 'Number of Publications', 'rgba(83,138,181,0.82)');

    return () => {
      [mainChartInstance, citationChartInstance, topicsChartInstance, authorsChartInstance, orgsChartInstance].forEach(r => {
        if (r.current) { r.current.destroy(); r.current = null; }
      });
    };
  }, [data]);

  function handleSearch() {
    const v = searchValue.trim();
    if (v) {
      setStatus(`Prototype search triggered for "${v}". Overview is front-end ready; real back-end data can be connected later.`);
    }
  }

  const s = data?.summary;
  const ins = data?.trend_insights;

  return (
    <>
      <div className="search-row">
        <div className="search-card">
          <div className="search-label">Search topic / material / task</div>
          <input
            className="search-input"
            value={searchValue}
            onChange={e => setSearchValue(e.target.value)}
          />
        </div>
        <div className="action-card">
          <div className="section-title-small">Run / Filter</div>
          <button className="search-btn" onClick={handleSearch}>Run Search</button>
        </div>
      </div>

      <div className="status">{status}</div>

      {loading && <div style={{ padding: '12px', color: 'var(--muted)' }}>Loading...</div>}
      {error && <div style={{ padding: '12px', color: '#b91c1c' }}>{error}</div>}

      {data && (
        <section className="overview-grid">
          {/* LEFT */}
          <div className="left-col">
            <section className="card">
              <div className="card-header">Summary Panel</div>
              <div className="card-body metric-list">
                <div className="metric-item"><span className="metric-label">Period</span><span className="metric-value">{s.from_year} - {s.to_year}</span></div>
                <div className="metric-item"><span className="metric-label">Selected Topic</span><span className="metric-value">{searchValue || s.selected_topic}</span></div>
                <div className="metric-item"><span className="metric-label">Total Publications</span><span className="metric-value">{formatNumber(s.total_publications)}</span></div>
                <div className="metric-item"><span className="metric-label">Total Citations</span><span className="metric-value">{formatNumber(s.total_citations)}</span></div>
                <div className="metric-item"><span className="metric-label">Average Citations per Paper</span><span className="metric-value">{s.avg_citations_per_paper.toFixed(1)}</span></div>
                <div className="metric-item"><span className="metric-label">H-Index</span><span className="metric-value">{s.h_index}</span></div>
                <div className="metric-item"><span className="metric-label">Top Publisher</span><span className="metric-value">{s.top_publisher}</span></div>
                <div className="metric-item"><span className="metric-label">Data Source</span><span className="metric-value">{s.data_source}</span></div>
              </div>
            </section>

            <section className="card">
              <div className="card-header">Filters (Optional)</div>
              <div className="card-body">
                <ul className="note-list">
                  <li>Year range</li>
                  <li>Entity type: Topic / Material / Task</li>
                  <li>Sort by publications / citations</li>
                  <li>Top N = 5 / 10 / 20</li>
                </ul>
              </div>
            </section>
          </div>

          {/* RIGHT */}
          <div className="right-col">
            <section className="card">
              <div className="card-header">Publications &amp; Citations</div>
              <div className="card-body">
                <div className="chart-meta">Main overview chart. Bar chart = publications. Line chart = citations.</div>
                <div className="chart-wrap"><canvas ref={mainChartRef}></canvas></div>
              </div>
            </section>

            <section className="card">
              <div className="card-header">Citation Trend</div>
              <div className="card-body">
                <div className="chart-meta">Average citations per paper over time.</div>
                <div className="chart-wrap small"><canvas ref={citationChartRef}></canvas></div>
              </div>
            </section>

            <div className="two-col">
              <section className="card">
                <div className="card-header">Top Topics</div>
                <div className="card-body">
                  <div className="chart-meta"><strong>X-axis:</strong> Number of Publications</div>
                  <div className="chart-wrap small"><canvas ref={topicsChartRef}></canvas></div>
                </div>
              </section>
              <section className="card">
                <div className="card-header">Top Authors</div>
                <div className="card-body">
                  <div className="chart-meta"><strong>X-axis:</strong> Number of Publications</div>
                  <div className="chart-wrap small"><canvas ref={authorsChartRef}></canvas></div>
                </div>
              </section>
            </div>

            <div className="two-col">
              <section className="card">
                <div className="card-header">Top Organizations</div>
                <div className="card-body">
                  <div className="chart-meta"><strong>X-axis:</strong> Number of Publications</div>
                  <div className="chart-wrap small"><canvas ref={orgsChartRef}></canvas></div>
                </div>
              </section>
              <section className="card">
                <div className="card-header">Trend Insights (Optional)</div>
                <div className="card-body insight">
                  <p><strong>Trend Direction:</strong> {ins.trend_direction}</p>
                  <p><strong>Peak Year:</strong> {ins.peak_year}</p>
                  <p><strong>Most Active Topic:</strong> {ins.most_active_topic}</p>
                  <p><strong>Note:</strong> {ins.note}</p>
                  <p><strong>KG Note:</strong> Two-topic co-occurrence analysis is better suited for Topics or Explorer.</p>
                </div>
              </section>
            </div>
          </div>
        </section>
      )}

      <div className="footer-note">Overview is the polished demo page. Other pages remain structured prototypes with clear chart specifications.</div>
    </>
  );
}
