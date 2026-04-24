import { useState, useEffect, useRef } from 'react';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

// ─── Reusable Horizontal Bar Chart Component ────────────────────────────────
function AuthorBarChart({ s, p, o }) {
  const [chartData, setChartData] = useState(null); 
  const [loading, setLoading] = useState(true); 
  const chartRef = useRef(null);  
  const chartInst = useRef(null);  

  useEffect(() => {
    setLoading(true);
    const url = `http://127.0.0.1:5000/api/authors/top?s=${s}&p=${p}&o=${o}`;
    
    fetch(url)
      .then(res => res.json())
      .then(result => {
        setChartData(result.data);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch", err);
        setLoading(false);
      });
  }, [s, p, o]);

  useEffect(() => {
    if (!chartData || chartData.length === 0) return;
    
    if (chartInst.current) {
      chartInst.current.destroy();
    }

    chartInst.current = new Chart(chartRef.current, {
      type: 'bar', 
      data: {
        labels: chartData.map(row => row.name), 
        datasets: [{
          label: `Publications`,
          data: chartData.map(row => row.papers), 
          backgroundColor: '#1cc7d0', 
          borderRadius: 4, 
          barPercentage: 0.6, 
          categoryPercentage: 0.8
        }]
      },
      options: {
        indexAxis: 'y', 
        responsive: true,
        maintainAspectRatio: false, 
        scales: {
          x: { 
            beginAtZero: true,
            // 🔥 MATH FIX 1: Adds extra space at the end so the bar doesn't hit the wall
            grace: '5%', 
            title: { display: true, text: 'Number of Publications' },
            ticks: { 
              // 🔥 MATH FIX 2: Auto-scales (by 1s, 5s, 10s) but FORCES whole numbers only
              precision: 0 
            }
          },
          y: { 
            grid: { display: false } 
          }
        },
        plugins: {
          legend: { display: false } 
        }
      }
    });
    
    return () => {
      if (chartInst.current) chartInst.current.destroy();
    };
  }, [chartData, s, p, o]);

  // 45 pixels per author + 80 pixels for the top/bottom axes and padding.
  const dynamicHeight = chartData ? Math.max(200, (chartData.length * 45) + 80) : 250;

  return (
    <div className="card" style={{ marginBottom: '18px' }}>
      <div className="card-header">
        Top Authors: {s} <strong>{p}</strong> {o}
      </div>
      <div className="card-body">
        {loading ? (
          <div className="status">Querying top authors...</div>
        ) : chartData && chartData.length > 0 ? (
          <div className="chart-wrap" style={{ height: `${dynamicHeight}px` }}>
            <canvas ref={chartRef}></canvas>
          </div>
        ) : (
          <div className="status">No authors found for this relationship.</div>
        )}
      </div>
    </div>
  );
}

// ─── Main Authors Page ──────────────────────────────────────────────────────
export default function Authors() {
  const [searchValue, setSearchValue] = useState('Machine Learning');

  const casesToTrack = [
    { s: "machine_learning", p: "usesMethod", o: "random_forest" },
    { s: "machine_learning", p: "includesMethod", o: "random_forest" },
    { s: "machine_learning", p: "adaptsMethod", o: "precision_statistic" }
  ];

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
          <div className="section-title-small">Authors Page</div>
          <button className="search-btn">Filter</button>
        </div>
      </div>

      <div className="status">
        Loading Top Authors for each specific relationship case...
      </div>

      <div className="placeholder-grid" style={{ gridTemplateColumns: '1fr' }}>
        {casesToTrack.map((rel, index) => (
          <AuthorBarChart 
            key={index} 
            s={rel.s} 
            p={rel.p} 
            o={rel.o} 
          />
        ))}
      </div>
    </>
  );
}