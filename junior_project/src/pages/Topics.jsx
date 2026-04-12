import { useState } from 'react';

export default function Topics() {
  const [searchValue, setSearchValue] = useState('Machine Learning');
  const [status] = useState(
    'Topics page is intended for deeper topic analysis. This is also the correct place for citation impact and two-topic knowledge graph relationship charts.'
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
          <div className="card-header">Topic Distribution</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Horizontal Bar Chart</div>
              <div><strong>X-axis:</strong> % of Publications</div>
              <div><strong>Y-axis:</strong> Topic Name</div>
              <div><strong>Contents:</strong> Topic name, paper count, percentage of total</div>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-header">Topic Growth Over Time</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Multi-line Chart</div>
              <div><strong>X-axis:</strong> Year</div>
              <div><strong>Y-axis:</strong> Number of Papers</div>
              <div><strong>Contents:</strong> One line per topic</div>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-header">Citation Impact</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Scatter Plot</div>
              <div><strong>X-axis:</strong> Publication Year</div>
              <div><strong>Y-axis:</strong> Citation Count</div>
              <div><strong>Contents:</strong> CSKG entity/triple + year of appearance + paper IDs, enriched with OpenAlex citation counts</div>
            </div>
          </div>
        </section>
      </div>

      <div className="footer-note">This page is intentionally structural. The overview page is the polished demo page with actual graphs.</div>
    </>
  );
}
