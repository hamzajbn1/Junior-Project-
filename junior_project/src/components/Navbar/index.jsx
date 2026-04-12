import { Link } from 'react-router-dom';
import styles from './styles.module.css'

const tabs = [
  { label: 'Overview', path: '/' },
  { label: 'Topics', path: '/topics' },
  { label: 'Authors', path: '/authors' },
  { label: 'Organizations', path: '/organizations' },
  { label: 'Explorer', path: '/explorer' },
];

export default function Layout({ children }) {

  return (
    <div>
      <header className={styles["topbar"]}>
        <div className={styles["topbar-inner"]}>
          <div className={styles["hero-box"]}>
            <h1 className={styles["hero-title"]}>Research Trend Explorer</h1>
            <p className={styles["hero-sub"]}>Knowledge graph-driven dashboard prototype</p>
          </div>

          <div className={styles["domain-box"]}>
            <div className={styles["domain-label"]}>Domain Selector</div>
            <select className={styles["domain-select"]}>
              <option>Computer Science</option>
              <option>Artificial Intelligence</option>
              <option>Any</option>
            </select>
          </div>

          <nav className={styles["tabs-box"]}>
            <div className={styles["tabs"]}>
              {tabs.map((tab) => {
                return (
                  <Link
                    key={tab.path}
                    to={tab.path}
                    className={styles["tab-link"]}
                  >
                    {tab.label}
                  </Link>
                );
              })}
            </div>
          </nav>
        </div>
      </header>

      <main className="page">
        {children}
      </main>
    </div>
  );
}
