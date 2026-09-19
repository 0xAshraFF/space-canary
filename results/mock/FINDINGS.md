# Findings — mock dry run

**Verdict: INCONCLUSIVE. No paid/model experiment has run.**

36 scripted trajectories; manufactured probe/failure correlation. Actual API spend: $0.

| Mock model | Delta AUROC | 95% interval |
| --- | ---: | --- |
| haiku | 0.491 | [0.140, 0.800] |
| deepseek | 0.491 | [0.140, 0.800] |

opus: mock delta AUROC 0.041, descriptive only; no interval

Gate 2 metrics and per-type ablations are in results/mock/analysis.json. These describe a scripted fixture only. The fixture deliberately includes warnings before failures.

The cost estimate exceeds both requested caps; a paid run must be resized or repriced first. Provider tokenization, live transport, provider pinning and scientific sample sufficiency remain unvalidated.
