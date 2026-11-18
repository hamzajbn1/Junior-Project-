import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Navbar/index';
import Overview from './pages/Overview';
import Assistant from './pages/Assistant';
import './design/style.css';

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/assistant" element={<Assistant />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
