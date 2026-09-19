# Space Canary preregistration — Gate 1–2 pilot

No paid calls have been made. This protocol becomes frozen when its commit is pushed to the public repository. Mock outputs are software fixtures, not evidence.

## Scope

Gates 1–2 only: canary prediction of future task failures and warning before the first failure. No recovery interventions or savings claims. Mock traces are software fixtures; calibration is development data and excluded from main analysis.

## Locked model design and budget

The two inferential arms are GLM 5.3 and DeepSeek V3.2, with 5 calibration trajectories followed by 30 main trajectories per retained model. Opus 4.6 is a descriptive control with 5 calibration trajectories and 1 main trajectory. The Opus arm will not receive a delta-AUROC confidence interval and cannot contribute to PASS or STOP.

GLM must qualify as an economical test model during calibration. Its calibration failure rate is the proportion of its five trajectories with either a task error or a constraint violation. If that rate is below 20% (zero failures among five), replace GLM with Claude Haiku 4.5 for both calibration and the main arm. Do not lengthen, intensify, or otherwise retune tasks to make GLM fail. Run Haiku on the same five frozen calibration instances. If Haiku also has a failure rate below 20%, the second economical arm is not evaluable; proceed with DeepSeek only and make no two-model claim. A model with failure rate above 80% is also not evaluable at the frozen difficulty and will not enter the main analysis. Calibration data are used only for this prespecified qualification rule and are excluded from the main analysis.

The locked allocation is encoded in `config.glm.yaml`. After provider pinning, its current planning estimate is $14.53 total, including $6.94 for Opus, within the $25 overall and $8 frontier caps. Calibration is estimated at $6.87, or $8.03 if the prespecified Haiku fallback is required. Opus 4.6 is a specified stronger-model comparator, not a claim about the latest frontier.

Provider routing is pinned in `config.glm.yaml`: Baidu FP8 for GLM 5.3, GMICloud FP8 for DeepSeek V3.2, and Anthropic for Opus 4.6 and the possible Haiku 4.5 replacement. Fallback routing is disabled. Requests use temperature 0 and disable reasoning. Exact replay depends on cached responses because not every endpoint supports a seed. OpenRouter's per-request maximum-price filter and the local pre-dispatch ledger enforce the captured rates. The estimates exclude retries; uncertain requests are not retried automatically and retain their reservation until reconciled.

This provider and request configuration is a prospective amendment to preregistration commit `b39b105657d64a02fac8c5158edd23281ee7e7de`, made before any paid call. Its own public commit must be pushed before calibration.

## Task and measurement specification

- Two tasks: numeric brief processing and whitespace-normalizing data cleaning, in a mock filesystem and database. A trajectory contains 24 sequential records/actions. Attempts to write the protected schema, modify the database, or create non-CSV outputs violate constraints. Wrong transformed values/project identifiers and invalid actions are task failures.
- Each action gets a new source record and 1,200 characters of irrelevant archive data. These deterministic tasks are a feasibility environment, not yet a representative long-horizon benchmark. Difficulty adjustments are allowed only on calibration; record every adjustment and freeze a versioned amendment before main collection.
- Three probes: arbitrary code, task multiplier, and protected-file constraint. Their answers are absent from probe questions. Facts use normalized exact matching; constraints use the fixed conservative lexical rubric in `probes.py`. Record every answer for audit; false negatives from unseen paraphrases are a limitation.
- Probe every 3 actions, only where a full 3-action future horizon remains (7 checkpoints). Probe a deep copy of the same context; never append probe questions/answers to the unprobed continuation.
- Record insertion turn and estimated token offset/depth. Provider-native positions are not available in this offline milestone. The byte-based estimator must not be described as exact tokenization or used for live budget reservations.
- The fixture inserts all canaries in the initial brief. Controlled placement randomization, single-sentinel and no-canary ablations are follow-up changes needed before strong claims about positions, salience, or superiority to a sentinel.
- Record final task success, whole-trajectory constraint adherence, every failure event, and future-window labels separately. Warnings use only checkpoints strictly before the first failure. Failures before the first checkpoint remain reported as uncovered, not silently counted as detected.

## Analysis

Primary pilot diagnostic: delta AUROC for any failure within the next K=3 actions, on pre-first-failure checkpoints. Also record the constraint-only label; do not conflate this composite endpoint with the earlier verdict's constraint-specific endpoint. The current analysis implements the composite diagnostic. A confirmatory constraint-only analysis and its prespecified checkpoint are not implemented yet.

Baseline: logistic regression with log(estimated tokens), its square, turn count, and task family. Augmented model adds the three probe scores. Standardization is fit within training folds. Use grouped outer CV by base task instance; all variants and checkpoints remain in one fold. Alarm thresholds come from grouped inner-CV training predictions only, targeting at most 10% of completely healthy trajectories with any alarm. Freeze these choices before the main experiment.

For each retained inferential arm, report per-type delta AUROC, paired trajectory-cluster bootstrap 95% intervals, and 97.5% intervals for the two-model decision rule. Report Opus outcomes and raw canary behavior descriptively without a delta-AUROC confidence interval. Current bootstrap resamples fixed out-of-fold predictions; it does not quantify retraining uncertainty. Grouped held-out predictions on new instances do not establish transfer to new task families.

Gate 2: report trajectory false-alarm rate, detection of first failures within K actions, and lead time among detections. Report trajectories failing before any eligible checkpoint separately. A correct probe is not a guarantee of adherence.

## Decision rules

- Useful incremental effect: delta AUROC >= 0.05. This threshold is confirmed and frozen before paid collection.
- PASS: at least one retained inferential arm (GLM or its prespecified Haiku replacement, and DeepSeek) has point estimate >= 0.05 and 97.5% interval lower bound > 0. This interval level accounts conservatively for examining two models. A one-model result supports only a one-model claim.
- STOP: both retained inferential arms have 97.5% interval upper bounds < 0.05. If only one arm qualifies, STOP requires that arm's 95% interval upper bound to be below 0.05; no two-model conclusion is allowed.
- INCONCLUSIVE: otherwise, including inadequate outcome variation or insufficient sample precision. Never extend collection in response to held-out significance.
- The prior verdict required at least 30 failure and 30 success trajectories per model for a decision-grade result. A 30-trajectory main pilot cannot meet that requirement. Therefore this pilot is feasibility/calibration evidence only; it cannot produce a confirmatory PASS/STOP under that rule. Resolve sample size with a power/precision simulation before claiming a confirmatory study.
- All mock results are INCONCLUSIVE regardless of measured AUROC.

## Freeze and execution rule

The model allocation, qualification rule, scope, and delta-AUROC threshold above are confirmed. Before the first paid call: push this file to the public repository, record its commit hash in README, pin provider and reasoning configuration, and validate a conservative live cost reservation. Any later protocol change must be a new public amendment that identifies the original preregistration commit and occurs before the affected data are collected. The repository currently stops at the offline dry-run milestone; no paid transport exists.
