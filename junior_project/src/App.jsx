import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Navbar/index';
import Overview from './pages/Overview';
import './style.css';

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Overview />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
