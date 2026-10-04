# Additional exploratory family after observing F1 losses

The initial seven-variant decomposition showed L-to-F1 losses and profitable
exit-at-L timing. These observations motivate the following additional analyses;
they were not proposed before observing the initial outputs and are explicitly
post-observation exploration.

1. Compare baseline, exit-L, F1-only, reversed F1, and a two-stage spread that
   flips at L, using original quantities and explicit additional round-trip costs.
2. Check the same dates and quantities at executable 15:59 bid/ask prices on
   entry, L and F1. Exclude early closes and missing/stale quotes jointly. No
   settlement fallbacks. Show normal and doubled cost stress.
3. Compare reversal with always-long-ES/short-ZN and always-long-ES-only over F1,
   using the same original dose-dependent quantity magnitudes. These controls
   diagnose generic first-session stock returns versus drift-dependent reversal.
4. Report fixed-era, direction, quarter-end, best-three-month removal and annual
   stability. No parameter searches, alternative dates, or OOS data.
5. Report two-sided centered-block-bootstrap p-values for all seven initial
   variants with Holm adjustment within that family. These adjustments do not
   erase earlier searches or confer confirmatory status.
