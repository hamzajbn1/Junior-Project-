import { useState, useEffect, useRef } from 'react';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

// ─── Reusable Relationship Chart Component ────────────────────────────────────
// This tiny component manages its OWN loading and data. 
// It fetches from the new Flask endpoint we just built!
function RelationshipChart({ s, p, o }) {
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(true);
  const chartRef = useRef(null);
  const chartInst = useRef(null);

  // Fetch the data just for this specific chart
  useEffect(() => {
    setLoading(true);
    const url = `http://127.0.0.1:5000/api/relationship?s=${s}&p=${p}&o=${o}`;
    
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

  // Draw the chart once the data arrives
  useEffect(() => {
    if (!chartData || chartData.length === 0) return;

    if (chartInst.current) {
      chartInst.current.destroy();
    }

    chartInst.current = new Chart(chartRef.current, {
      type: 'line',
      data: {
        labels: chartData.map(row => row.year),
        datasets: [{
          label: `${s} ${p} ${o} (Publications)`,
          data: chartData.map(row => row.publications),
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
        scales: {
          y: { beginAtZero: true },
          x: { title: { display: true, text: 'Year' } }
        }
      }
    });

    return () => {
      if (chartInst.current) chartInst.current.destroy();
    };
  }, [chartData, s, p, o]);

  return (
    <div className="card" style={{ marginBottom: '18px' }}>
      <div className="card-header">
        {s} <strong>{p}</strong> {o}
      </div>
      <div className="card-body">
        {loading ? (
          <div className="status">Querying OpenAlex pipeline...</div>
        ) : chartData && chartData.length > 0 ? (
          <div className="chart-wrap small">
            <canvas ref={chartRef}></canvas>
          </div>
        ) : (
          <div className="status">No data found for this relationship.</div>
        )}
      </div>
    </div>
  );
}

// ─── Main Overview Dashboard ────────────────────────────────────────────────
export default function Overview() {
  // Here is your exact list of relationships to track!
  const relationshipsToTrack = [
    { s: "machine_learning", p: "uses", o: "random_forest" },
    { s: "machine_learning", p: "includes", o: "random_forest" },
    { s: "machine_learning", p: "adopts", o: "Precision" }
  ];

  return (
    <>
      <div className="status">
        Loading Relationship Trends via Async Architecture...
      </div>

      <section className="overview-grid">
        {/* LEFT COLUMN */}
        <div className="left-col">
          <section className="card">
            <div className="card-header">Architecture Notes</div>
            <div className="card-body insight">
              <p>Each chart on the right fetches its data completely independently.</p>
              <p>If one takes 5 seconds, it won't block the others from loading instantly!</p>
            </div>
          </section>
        </div>

        {/* RIGHT COLUMN */}
        <div className="right-col">
          {/* Loop through your list and render a smart component for each one! */}
          {relationshipsToTrack.map((rel, index) => (
            <RelationshipChart 
              key={index} 
              s={rel.s} 
              p={rel.p} 
              o={rel.o} 
            />
          ))}
        </div>
      </section>
    </>
  );
}