# Audit display-precision correction

After the24 exact artifact-repair reruns, the checker stopped at carried2024
VOL_CLOCK opening equity: native `result.start_equity` is212025.95, whereas
reconstructed raw four-decimal closes sum to212025.9529. The native public result
rounds opening equity to two decimals. The discrepancy is0.0029 rupees, below
one paise; it is not a missing trade, deposit or floor reset.

The opening-display comparison now uses the same one-paise tolerance as the
end-cash/state checks. Underlying per-trade fee calculations retain their stricter
0.001-rupee tolerance. No input, economic result, trading rule, floor decision or
acceptance threshold changed. Both failed checker invocations are retained in
the tool record and this document; full audit must still pass all60 books.
