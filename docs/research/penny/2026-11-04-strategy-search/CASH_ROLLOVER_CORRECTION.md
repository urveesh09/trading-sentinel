# Smart cash-rollover correction before validation

The new research replay initially called the runtime flat-book rollover at the
start of a session only. Runtime checks on every observation. When an unresolved
prior-day position closed after the first observation, the initial replay left
the old day latched and missed the rest of that day's entry opportunities.

The correction calls the unchanged rollover function before every observation
and resets only the local closed-trade cursor when a new daily book is created.
Carried capital includes realised losses; it is never replenished. A targeted
test settles the carry on the first look and verifies that the next look uses
the current day and Rs 1,995 rather than Rs 2,000.

Original training outcomes are retained. `smart-v2/` repeats all eight identical
baseline/candidate parameter sets before finalist selection and validation.
There was one overnight close in each initial V1, V2 and patient baseline arm;
the first retest and participation arms had none. No new parameter is selected
from validation. No Production code, configuration or live book changes.

Daily genome ranking had one economically duplicate finalist (G07/G09). Both
trial records remain. `genome-selection-v2.json` removes duplicate training and
calibration trade histories and selects G07 and G05 before validation. G09 is
not presented as independent confirmation. The initial and corrected selectors
are both retained. No validation outcome was opened for either correction.
