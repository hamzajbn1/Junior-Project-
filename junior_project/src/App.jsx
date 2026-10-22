import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Navbar/index';
import Overview from './pages/Overview';
import Assistant from './pages/Assistant';
import Agent2Test from './pages/agent2Test';
import './design/style.css';

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/assistant" element={<Assistant />} />
          <Route path="/agent2-test" element={<Agent2Test />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
