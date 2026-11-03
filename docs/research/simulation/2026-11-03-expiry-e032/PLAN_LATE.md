# E03.2 Phase 1b — the late slice (15:00-15:15), written after the morning failed and before any late entry is scored

The morning test (freeze `68db264`, `morning-results.json`) failed every check: E02's entry loses before
13:00 in both years and is worse than random entries there. Most morning tickets end on the eight-minute
clock: the option does not move in time. E02's edge looks tied to the last hours before expiry.

E02's genome only ever ended entries at 14:30 or 15:00. **No entry between 15:00 and 15:15 has ever been
scored.** Option prices in that slice were seen only as exits of tickets bought before 15:00.

Arms `L_E02`, `L_E03`, `L_E031`: the frozen rules with decisions only from 15:00 to 15:15 (`start=900`,
`end=915`), flat from 15:28 as always. Same scenarios, books, 40 random seeds and the same pass test as the
morning. If it passes, the main book's entry window ends at 15:15 instead of 15:00 (same two tickets, same
Rs 2,500 a day). If it fails, 15:00 stays.
