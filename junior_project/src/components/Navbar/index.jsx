import { Link } from 'react-router-dom';

export default function Layout({ children }) {

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/" aria-label="Research Trend Explorer home">
          <span className="brand-mark" aria-hidden="true">↗</span>
          <span>Research Trend<span className="brand-second">Explorer</span></span>
        </Link>
        <div className="page-heading">
          <nav aria-label="Main navigation"><Link to="/" aria-current="page">Overview</Link></nav>
          <span className="domain"><span aria-hidden="true" />Computer Science</span>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
