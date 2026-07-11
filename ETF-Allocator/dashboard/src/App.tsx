import { BrowserRouter, Navigate, Routes, Route } from 'react-router-dom';
import AiriDashboard from './pages/AiriDashboard';
import Trends from './pages/Trends';
import InvestmentHistory from './pages/InvestmentHistory';
import NavBar from './components/NavBar';
import { ThemeProvider } from './contexts/ThemeContext';

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <div className="min-h-screen font-sans bg-[#FFFBF0]">
          <NavBar />
          <Routes>
            <Route path="/" element={<AiriDashboard />} />
            <Route path="/simulator" element={<Navigate to="/" replace />} />
            <Route path="/trends" element={<Trends />} />
            <Route path="/investments" element={<InvestmentHistory />} />
          </Routes>
        </div>
      </BrowserRouter>
    </ThemeProvider>
  );
}
