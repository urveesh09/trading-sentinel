"""The frozen arms, and what each is compared on.

A lottery ticket's rules only. A and B stay as they are: nothing tried on the eight sessions improved them
without leaning on one day or breaking under worse fills.
"""
from __future__ import annotations

from dataclasses import replace

import e011_lab as L

TRAIL_3X = ((2.0, .60), (4.0, .60))      # the native 60% keep, starting where the bank fires instead of at 5x

ARMS = {
    "C": L.C_NATIVE,                                                     # the main book's ticket
    "E01": L.E01,                                                        # the benchmark
    "STOP25": replace(L.E01, stop=.25),                                  # one change at a time
    "RECOVER": replace(L.E01, bank="recover"),
    "TRAIL3X": replace(L.E01, trails=TRAIL_3X),
    "E011": replace(L.E01, stop=.25, bank="recover", trails=TRAIL_3X),   # primary: cost back, the rest runs, floor from 3x
    "E011R": replace(L.E01, stop=.25, bank_at=None, trails=TRAIL_3X),    # primary: no bank, the whole ticket runs on the floor
    # neighbours: they judge the primaries, they never replace them
    "E011_S20": replace(L.E01, stop=.20, bank="recover", trails=TRAIL_3X),
    "E011_S30": replace(L.E01, stop=.30, bank="recover", trails=TRAIL_3X),
    "E011_K50": replace(L.E01, stop=.25, bank="recover", trails=((2.0, .50), (4.0, .60))),
    "E011R_S20": replace(L.E01, stop=.20, bank_at=None, trails=TRAIL_3X),
    "E011R_S30": replace(L.E01, stop=.30, bank_at=None, trails=TRAIL_3X),
    "E011R_K50": replace(L.E01, stop=.25, bank_at=None, trails=((2.0, .50), (4.0, .60))),
}
PRIMARY = ("E011", "E011R")
# Rules that change which ticket is bought. September can't test them, so they are reported apart and never carried.
ENTRY_READINGS = {
    "E011_BOX35": replace(ARMS["E011"], box_max_bp=35.0),
    "E011_BOX25": replace(ARMS["E011"], box_max_bp=25.0),
    "E011_BOX45": replace(ARMS["E011"], box_max_bp=45.0),
    "E011_BAND50": replace(ARMS["E011"], band_hi=.5),
    "E011R_BOX35": replace(ARMS["E011R"], box_max_bp=35.0),
    "E011R_BAND50": replace(ARMS["E011R"], band_hi=.5),
}
