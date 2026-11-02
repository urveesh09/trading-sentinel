"""Compact the eight archived sessions once. The source database is opened read-only."""
import e011_lab as L

for day, u in L.recorded_keys():
    print(L.prepare_session(day, u), flush=True)
