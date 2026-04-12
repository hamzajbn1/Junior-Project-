import { useState } from 'react';

export default function Explorer() {
  const [searchValue, setSearchValue] = useState('Machine Learning');
  const [status] = useState(
    'Explorer page is intended for dynamic knowledge-graph interaction, task-specific querying, and custom results exploration.'
  );

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
          <div className="section-title-small">Prototype Page</div>
          <button className="search-btn">Placeholder Action</button>
        </div>
      </div>

      <div className="status">{status}</div>

      <div className="placeholder-grid">
        <section className="card">
          <div className="card-header">Query Controls</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Input + Button Section</div>
              <div><strong>X-axis:</strong> N/A</div>
              <div><strong>Y-axis:</strong> N/A</div>
              <div><strong>Contents:</strong> Select entity type, input value, run query</div>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-header">Results Table</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Data Table</div>
              <div><strong>X-axis:</strong> Columns</div>
              <div><strong>Y-axis:</strong> Rows</div>
              <div><strong>Contents:</strong> Task, Work ID, Authors, Year, Venue</div>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-header">Top Venues for Specific Research Tasks</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Horizontal Bar Chart</div>
              <div><strong>X-axis:</strong> Number of Papers</div>
              <div><strong>Y-axis:</strong> Venue / Journal Name</div>
              <div><strong>Contents:</strong> Aggregates OpenAlex venue metadata for a queried method or task and shows top 10 venues</div>
            </div>
          </div>
        </section>
      </div>

      <div className="footer-note">This page is intentionally structural. The overview page is the polished demo page with actual graphs.</div>
    </>
  );
}
