import { useEffect, useRef } from 'react';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

export function ResultChart({ spec }) {
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
        <caption>Annual counts for this result</caption>
        <thead><tr><th scope="col">Publication year</th><th scope="col">Supporting papers</th></tr></thead>
        <tbody>{spec.labels.map((year, index) => <tr key={year}>
          <td>{year}</td><td>{spec.values[index] ?? 'Unknown — incomplete coverage'}</td>
        </tr>)}</tbody>
      </table>
    </details>
  </>;
}
