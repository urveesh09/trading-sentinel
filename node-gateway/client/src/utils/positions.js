export const isActivePosition = (position) =>
  position?.status === 'OPEN' ||
  (position?.status === 'CLOSED_T1' && !position?.exit_date);
