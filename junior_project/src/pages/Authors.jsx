import { useState } from 'react';

export default function Authors() {
  const [searchValue, setSearchValue] = useState('Machine Learning');
  const [status] = useState(
    'Authors page is intended for author-level ranking and topic-specific leadership analysis.'
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
          <div className="card-header">Top Authors by Publications</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Horizontal Bar Chart</div>
              <div><strong>X-axis:</strong> Number of Publications</div>
              <div><strong>Y-axis:</strong> Author Name</div>
              <div><strong>Contents:</strong> Author name and publication count</div>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-header">Top Authors by Citations</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Horizontal Bar Chart</div>
              <div><strong>X-axis:</strong> Number of Citations</div>
              <div><strong>Y-axis:</strong> Author Name</div>
              <div><strong>Contents:</strong> Author name and citation count</div>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-header">Leading Authors by Topic</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Horizontal Bar / Stacked Bar</div>
              <div><strong>X-axis:</strong> Top authors for queried topic</div>
              <div><strong>Y-axis:</strong> Author Name</div>
              <div><strong>Contents:</strong> Bars can later be stacked by publication year or split by citation impact</div>
            </div>
          </div>
        </section>
      </div>

      <div className="footer-note">This page is intentionally structural. The overview page is the polished demo page with actual graphs.</div>
    </>
  );
}
