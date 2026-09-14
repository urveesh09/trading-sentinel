import React from 'react';
import { describePhase } from '../utils/sessionPhase';

// [WORKFLOW-J.8 2026-09-13] Compact session-phase chip.
//
// Reads ``health.session_phase`` (a string from the
// Node /health response, exposed by the J.6 mirror
// and produced bit-perfect by the J.7 verdict) and
// renders a coloured chip. The chip is intentionally
// compact: the StatusBar already shows "Market:
// Open/Closed" as the binary, and the chip adds the
// bounded phase as a second indicator. ``executionBlocked``
// surfaces a small lock icon when the phase blocks
// broker orders so the operator's eye sees the
// tradeable state at a glance.
//
// The component never throws. Missing / null /
// unknown phase -> ``UNKNOWN`` chip (red).
export default function SessionPhaseBadge({ phase }) {
  const { phase: safe, label, colorClass, executionBlocked } =
    describePhase(phase);
  return (
    <span
      data-testid="session-phase-badge"
      data-phase={safe}
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold ${colorClass}`}
      title={
        executionBlocked
          ? `${label} -- broker orders are blocked in this phase`
          : `${label} -- broker orders are allowed`
      }
    >
      {executionBlocked && (
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="11"
          height="11"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
      )}
      <span>{label}</span>
    </span>
  );
}
