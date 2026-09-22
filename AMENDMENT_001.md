# Amendment 001 — fenced JSON parser correction

This amendment follows preregistration commit `b39b105657d64a02fac8c5158edd23281ee7e7de` and the completed Stage A calibration. It does not reinterpret the affected Haiku trajectories as valid evidence.

## Finding

The action prompt requested JSON. Claude Haiku 4.5 often returned exactly one valid JSON object wrapped in a Markdown `json` code fence. The original parser accepted bare JSON only, turning fenced responses into empty actions. Four of five Haiku trajectories were contaminated from turn 1 onward by the resulting artificial tool errors.

## Prospective correction

`parse_answer` may remove one optional outer Markdown fence labelled `json` (or unlabelled) when the fence contains the entire response, then apply the existing JSON-object requirement. It will continue to reject surrounding prose, multiple blocks, non-object JSON, and malformed JSON. Tests freeze these boundaries.

Any Haiku recalibration must use the same five seeds, task families, 24 turns, 1,200 filler characters per turn, checkpoint schedule, provider, prices, and scoring rules. The invalid Haiku trajectories remain excluded. GLM and DeepSeek are not rerun. Paid execution remains disabled until a separate allocation names a hard cap and this amendment is publicly committed.
