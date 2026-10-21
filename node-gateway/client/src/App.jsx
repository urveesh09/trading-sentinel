import React, { useState } from 'react';
import useSWR from 'swr';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Positions from './pages/Positions';
import BacktestLab from './pages/BacktestLab';
import ResearchCenter from './pages/ResearchCenter';
import PartnerCoach from './pages/PartnerCoach';
import StandardCapital from './pages/StandardCapital';
import { useHealth } from './hooks/useHealth';
import { fetcher } from './api/client';
import { evidenceModeEnabled } from './evidenceMode';

// "/?view=coach" (where the partner's Zerodha login lands) opens the coach page.
const initialView = () => (
  typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('view') === 'coach'
    ? 'COACH' : 'DASHBOARD'
);

export default function App() {
  const { health, isLoading, isError } = useHealth();
  // [O21-PK] A coach-only session from the partner's own Zerodha login sees
  // only their review, whatever the owner's token state.
  const { data: authStatus, isLoading: authLoading } = useSWR(
    evidenceModeEnabled ? null : '/api/auth/status', fetcher, { revalidateOnFocus: false });
  const [currentView, setCurrentView] = useState(initialView);

  if (authStatus?.partner_view && !authStatus?.authenticated) {
    return <PartnerCoach partnerView />;
  }

  // Show a dark loading screen while strictly checking session auth
  if ((isLoading && !health) || (authLoading && !authStatus)) {
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
  if (currentView === 'BACKTESTS') {
    return <BacktestLab navigateToDashboard={() => setCurrentView('DASHBOARD')} />;
  }
  if (currentView === 'RESEARCH') {
    return <ResearchCenter navigateToDashboard={() => setCurrentView('DASHBOARD')} navigateToBacktests={() => setCurrentView('BACKTESTS')} />;
  }
  if (currentView === 'POSITIONS') {
    return <Positions navigateToDashboard={() => setCurrentView('DASHBOARD')} />;
  }
  if (currentView === 'COACH') {
    return <PartnerCoach navigateToDashboard={() => setCurrentView('DASHBOARD')} />;
  }
  if (currentView === 'CAPITAL') {
    return <StandardCapital navigateToDashboard={() => setCurrentView('DASHBOARD')} />;
  }
  return (
    <Dashboard
      healthData={health}
      navigateToPositions={() => setCurrentView('POSITIONS')}
      navigateToBacktests={() => setCurrentView('BACKTESTS')}
      navigateToResearch={() => setCurrentView('RESEARCH')}
      navigateToCoach={() => setCurrentView('COACH')}
      navigateToCapital={() => setCurrentView('CAPITAL')}
    />
  );
}
