import React, { useState } from 'react';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Positions from './pages/Positions';
import { useHealth } from './hooks/useHealth';

export default function App() {
  const { health, isLoading, isError } = useHealth();
  const [currentView, setCurrentView] = useState('DASHBOARD');

  // Show a dark loading screen while strictly checking session auth
  if (isLoading && !health) {
    return <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-500 font-mono">Initializing System...</div>;
  }

  // If endpoint fails entirely, show safe fallback
  if (isError) {
    return <div className="min-h-screen bg-gray-950 flex items-center justify-center text-red-500 font-mono">Data unavailable - retrying</div>;
  }

  // If token is not active, force Login
  if (health?.token_status !== 'active') {
    return <Login healthData={health} />;
  }

  // Basic View Router
  return currentView === 'DASHBOARD' ? (
    <Dashboard healthData={health} navigateToPositions={() => setCurrentView('POSITIONS')} />
  ) : (
    <Positions navigateToDashboard={() => setCurrentView('DASHBOARD')} />
  );
}
