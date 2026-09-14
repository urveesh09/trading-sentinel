import React from 'react';
import { Clock } from 'lucide-react';
import { describePhase } from '../utils/sessionPhase';

// [WORKFLOW-J.8 2026-09-13] Operator session-phase card.
//
// Reads ``health.session_phase`` (a bounded string from the
// Node /health response, exposed by the J.6 Node mirror and
// produced bit-perfect with the J.1 Python classifier) and
// renders a card-shaped indicator suitable for the Dashboard
// header area. The card shows:
//   - The bounded phase string (one of 10 documented values)
//   - A human-readable label
//   - The execution-allowed verdict (broker orders will / will
//     not be accepted by the J.7 server gate)
//   - A short phase description for context
//
// The component never throws. Missing / null / unknown phase
// falls back to ``UNKNOWN`` (red, broker orders blocked).
const PHASE_DESCRIPTION = {
  CLOSED: 'Outside trading hours. Broker orders are blocked.',
  PRE_MARKET: 'Pre-open session. Broker orders blocked by default; override available on the Node side.',
  CONTINUOUS_TRADING: 'Regular continuous trading. Broker orders accepted.',
  CAS_REFERENCE_PRICE_WINDOW: 'Closing auction reference-price window (15:15-15:20 IST). No new orders.',
  CAS_ORDER_ENTRY: 'Closing auction order-entry window (15:20-15:25 IST). No new orders.',
  CAS_LIMIT_ENTRY_ONLY: 'Closing auction limit-entry-only window (15:25-15:30 IST). No new orders.',
  CAS_MATCHING: 'Closing auction matching (15:30-15:35 IST). No new orders.',
  CAS_POST: 'Closing auction post-close (15:35-16:00 IST, cash). No new orders; derivatives are CAS-aligned.',
  DERIVATIVES_CAS_ALIGNED: 'Derivatives CAS-aligned band (15:30-15:40 IST). Broker orders accepted for F&O.',
  UNKNOWN: 'Could not classify the current session. Broker orders blocked for safety.',
};

export default function SessionPhaseCard({ phase }) {
  const { phase: safe, label, colorClass, executionBlocked } =
    describePhase(phase);
  return (
    <div
      data-testid="session-phase-card"
      data-phase={safe}
      data-execution-blocked={executionBlocked}
      className={`flex items-start gap-3 rounded-lg border p-4 ${colorClass}`}
    >
      <Clock size={22} className="mt-0.5" />
      <div className="flex-1">
        <div className="text-xs uppercase tracking-wider opacity-80">
          Session Phase
        </div>
        <div className="mt-1 flex flex-wrap items-baseline gap-2">
          <span className="text-lg font-bold">{label}</span>
          <span className="font-mono text-xs opacity-70">{safe}</span>
        </div>
        <div className="mt-2 text-xs opacity-90">
          {PHASE_DESCRIPTION[safe]}
        </div>
        <div className="mt-2 text-xs">
          {executionBlocked ? (
            <span className="inline-flex items-center gap-1 font-semibold">
              <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              Broker orders blocked
            </span>
          ) : (
            <span className="font-semibold">Broker orders accepted</span>
          )}
        </div>
      </div>
    </div>
  );
}
