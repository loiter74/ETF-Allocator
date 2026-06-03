import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AiriDashboard from './pages/AiriDashboard';
import Simulator from './pages/Simulator';
import Trends from './pages/Trends';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AiriDashboard />} />
        <Route path="/simulator" element={<Simulator />} />
        <Route path="/trends" element={<Trends />} />
      </Routes>
    </BrowserRouter>
  );
}
