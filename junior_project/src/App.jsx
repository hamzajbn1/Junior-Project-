import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Navbar/index';
import Overview from './pages/Overview';
import Topics from './pages/Topics';
import Authors from './pages/Authors';
import Organizations from './pages/Organizations';
import Explorer from './pages/Explorer';
import './style.css';

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/topics" element={<Topics />} />
          <Route path="/authors" element={<Authors />} />
          <Route path="/organizations" element={<Organizations />} />
          <Route path="/explorer" element={<Explorer />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
