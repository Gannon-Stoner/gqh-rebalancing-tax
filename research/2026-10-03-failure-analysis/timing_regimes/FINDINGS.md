# Why the timing failed: exploratory IS findings

The original portfolio makes most of its money before month-end, then gives
much of it back on the first session of the following month. Holding the same
positions through F1 is a substantial economic choice, rather than a harmless
extra exit day. These findings use only data through 2024-10-01.

## Main timing result

Over the registered common period, October 2015–September 2024 (108 months):

| Variant | Net P&L, $10M reference NAV | Sharpe | Sharpe at 2x costs |
| --- | ---: | ---: | ---: |
| Original P0, entry through F1 | $183,525 | 0.134 | 0.092 |
| Same positions, exit at L | $794,478 | 0.634 | 0.589 |
| L to F1 only, original direction | -$668,491 | -0.996 | -1.076 |
| ES leg only, original full window | $252,678 | 0.211 | 0.191 |
| ZN leg only, original full window | -$69,153 | -0.122 | -0.183 |
| Unfiltered midmonth spread | -$447,091 | -0.388 | -0.431 |

The F1 gross contribution is -$610,953. Each standalone timing row pays a full
round trip, so its net contributions do not add without restoring duplicated
costs. ES-only and ZN-only costs divide the original costs and add exactly.

Exit-at-L earns $409,309 in short-ES events and $385,169 in long-ES events.
F1-only loses $666,166 in short-ES events and $2,325 in long-ES events.
The short-stock first-session exposure explains essentially all the F1 loss in
the common evaluation sample. Exit-at-L is positive in all three fixed eras,
with Sharpe 1.106, 0.790, and 0.478 for 2010–15, 2016–20, and 2021–24.

## Simultaneous executable quotes preserve the relationship

Matched 15:59 bid/ask execution jointly removes early closes or unavailable
quotes on original entry, L, and F1. There are 95 shared trades; flat months
remain in the 108-month Sharpe calculation. No stale quote or settlement
fallback is used. Integer quantities remain the original decision-date sizes.

| Variant | Net P&L | Sharpe | Sharpe at 2x costs |
| --- | ---: | ---: | ---: |
| Original full window | $141,624 | 0.117 | 0.074 |
| Exit at L | $740,649 | 0.661 | 0.616 |
| Original-direction F1 only | -$650,876 | -0.981 | -1.053 |
| Reverse original direction on F1 | $547,127 | 0.833 | 0.758 |
| Original trade into L, reverse for F1 | $1,287,776 | 0.930 | 0.858 |
| Always long ES/short ZN on F1 | $555,958 | 0.849 | 0.775 |
| Always long ES only on F1 | $515,183 | 0.897 | 0.863 |

The reversal and two-stage variants were specified only after seeing the F1
loss. Their discovery sequence is recorded in FOLLOWUP_PLAN.md; they have no
confirmatory status. Flipping pays the full bid/ask and fees twice, including
the two transactions at L. Always-long controls retain the original
dose-dependent quantity magnitudes; they are direction controls, not constant
risk or constant-notional market benchmarks.

Exit-at-L quote P&L remains +$315,615 after removing its best three months;
leave-one-year-out Sharpe ranges from 0.580 to 0.813. The two-stage quote row
remains +$756,984 after deleting its best three months; leave-one-year-out
Sharpe ranges 0.847–1.129. The 2021–24 quote exit-at-L row has Sharpe 0.613,
but deleting that era's best three months turns its $266,543 profit into a
$26,959 loss. Recent-period concentration remains a material weakness.

## Economic interpretation and alternative explanation

The evidence is consistent with flow-related movement before month-end and
different returns after month-end. It does not identify fund flows as the cause.
An always-long ES first-session control performs at least as well as a
drift-conditioned reversal during the common period. Reversal minus the
always-long spread control on matched quotes has mean -0.082 bp/month with a
90% block-bootstrap interval [-2.218, +2.082]. Therefore a generic first-session
equity premium is a serious competing explanation; it is premature to claim
we found rebalancers' inventory unwinding.

Quarter-end does not concentrate the exit-L profits: $107,081 over 34
quarter-end trades versus $687,398 over 70 nonquarter trades. This also weakens
a simple claim that the largest institutional calendar reallocations uniquely
drive the result.

## The old event-path plot was not the traded signal

Its direction was frozen at L-12. The traded signal was frozen at L-5, with
different contract and volatility scaling. Direction changes between these
times for 14.3%, 13.3%, and 18.2% of matched months in the three fixed eras.
In the matched path sample, actual-signal dose-weighted entry-to-L returns are
+0.645, +0.618, and +0.365 daily-sigma units, whereas entry-to-F1 returns are
-0.087, +0.216, and +0.118. The pre-L move weakens but is not flat after 2021.
The original figure cannot by itself establish that the traded opportunity
disappeared. Pre-L-5 paths conditioned on L-5 direction are descriptive and
contain future conditioning; they cannot be interpreted as executable signals.

## Uncertainty and discovery limits

The paired executable improvement from exit-at-L over baseline is +5.547
bp/month, pointwise 90% interval [2.224, 9.121], using circular three-month
blocks and 4,999 draws. These are selected-sample exploratory intervals.
For the initial seven-row family, two-sided centered-block-bootstrap tests
give F1 loss p=0.003 (Holm 0.021) and exit-at-L mean p=0.052 (Holm 0.312).
The adjustment covers only this family, not the 80+ prior strategy looks or
the later reversal family. Chronological stability is encouraging but is
still measured inside previously inspected IS data.

The defensible next hypothesis is to test month-end exit timing with a generic
first-session equity-premium control, using an explicitly revised protocol and
an honestly labeled later evaluation. This analysis does not rescue the
registered remaining-return gate or erase its rejection conditions.

Reproduction: run `analyze.py`, then `followup.py` in this directory with the
repository's Python environment. Both scripts load only IS-filtered parquet
rows, do not write original research inputs, and preserve all evaluated
variants in CSV output.
