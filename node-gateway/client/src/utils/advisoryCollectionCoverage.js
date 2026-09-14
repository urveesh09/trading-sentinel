const STATES = new Set(['NEVER_ATTEMPTED', 'ATTEMPTED_UNAVAILABLE', 'PARTIAL', 'STALE', 'COMPLETE']);

export function advisoryCoverageRows(readiness, indices = ['NIFTY', 'SENSEX']) {
  const attempts = readiness?.advisory_collection_attempts;
  return indices.map((index) => {
    const raw = attempts?.per_index?.[index];
    const state = STATES.has(raw?.state) ? raw.state : 'UNAVAILABLE';
    return {
      index,
      state,
      attempted: Number.isInteger(raw?.attempted) ? raw.attempted : null,
      expected: Number.isInteger(raw?.expected) ? raw.expected : null,
      missing: Number.isInteger(raw?.missing_schedule_count) ? raw.missing_schedule_count : null,
      incomplete: Number.isInteger(raw?.incomplete_count) ? raw.incomplete_count : null,
      latest: raw?.latest_updated_at_utc || null,
      sessionDate: attempts?.session_date || null,
    };
  });
}
