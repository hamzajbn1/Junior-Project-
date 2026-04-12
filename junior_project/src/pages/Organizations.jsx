import { useState } from 'react';

export default function Organizations() {
  const [searchValue, setSearchValue] = useState('Machine Learning');
  const [status] = useState(
    'Organizations page is intended for institution and country analysis, including leadership by topic.'
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
          <div className="card-header">Top Organizations</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Horizontal Bar Chart</div>
              <div><strong>X-axis:</strong> Number of Publications</div>
              <div><strong>Y-axis:</strong> Organization Name</div>
              <div><strong>Contents:</strong> Organization name and publication count</div>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-header">Top Countries</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Horizontal Bar Chart</div>
              <div><strong>X-axis:</strong> Number of Publications</div>
              <div><strong>Y-axis:</strong> Country</div>
              <div><strong>Contents:</strong> Country name and publication count</div>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-header">Leading Institutions by Topic</div>
          <div className="card-body">
            <div className="axis-block">
              <div><strong>Chart / Section type:</strong> Horizontal Bar / Stacked Bar</div>
              <div><strong>X-axis:</strong> Top institutions for queried topic</div>
              <div><strong>Y-axis:</strong> Institution Name</div>
              <div><strong>Contents:</strong> OpenAlex affiliations can later be grouped by publication year or citation impact</div>
            </div>
          </div>
        </section>
      </div>

      <div className="footer-note">This page is intentionally structural. The overview page is the polished demo page with actual graphs.</div>
    </>
  );
}
