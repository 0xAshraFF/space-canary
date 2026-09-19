# Space Canary — Round 2 verdict

Date: 2026-09-19

- **Verdict enum: PURSUE_BOUNDED_PILOT**
- **Confidence: 0.80** that a bounded pilot is worth the investment. This is a subjective decision confidence, not an estimated probability of a positive result or paper acceptance.
- **Evidence status: PRE_EMPIRICAL.** The May calibration experiment never ran. No results exist.
- **Repository suggestion: `space-canary`**
- **Description:** Testing whether context probes predict agent failures before they happen.

Protocol note: No local verdict protocol or enum vocabulary was found. This document uses the requested fields and defines its decision explicitly. The preregistration below is a prospective local specification, not a claim of external registration.

## Scope and verdict

Proceed with Gates 1–2: incremental prediction of task failure, and warning before failure. Defer recovery policies, savings claims, and broad model-transfer studies until the signal earns that investment. At ten hours per week, my previous five gates were too broad for a first study.

Gate 1 alone can plausibly support a focused empirical or workshop paper if it includes credible baselines, held-out task instances, uncertainty, and informative failure analysis. A correlation between two synthetic recall tests would be weak. Gates 1–2 together provide a stronger paper. Neither guarantees acceptance, and neither establishes that recovery works or saves money.

Multiple positions and probe types are a hypothesis about improving measurement. They do not by themselves solve salience bias or establish superiority to one sentinel. Include a single-sentinel comparator and report whether the additional probes earn their overhead.

## Research question and prior art

Primary question: Does a fixed canary score improve prediction of subsequent unprompted constraint violations beyond context length, turn count, and task type?

Secondary question: At a fixed false-alarm budget, does the signal warn earlier or detect more impending violations than those baselines? Report final task success separately, including failures unrelated to context.

[Hermes #55550](https://github.com/NousResearch/hermes-agent/issues/55550) proposes a sentinel echo, consecutive-miss detection, and a compaction trigger. It is close conceptual prior art; the inspected page is a proposal, not controlled validation. [AdaCoM](https://arxiv.org/abs/2605.30785) studies adaptive context management using a trained external manager. The contribution here is controlled evaluation of the diagnostic signal, not the invention of runtime canaries or adaptive context management.

## Smallest next artifact

Produce a **reproducible pilot bundle**: task generator, checkpoint-fork runner, mechanical outcome checker, JSONL traces, and one short results notebook/report. Do not build a dashboard or recovery library yet.

Time box: **10–12 hands-on hours**, approximately one to two weeks at the available schedule:

| Work | Hours |
| --- | ---: |
| Freeze task schema, outcomes, probes, and logging | 2 |
| Implement one API route and checkpoint forks | 3 |
| Implement mechanical scoring and inspect sample traces | 2 |
| Run pilot and check failures, costs, and leakage | 2–3 |
| Write feasibility decision and lock confirmatory plan | 1–2 |

Pilot: 36 independent trajectories total, 12 each on two economical models from different families and one frontier control. Use two mechanically checkable task templates, such as selecting records under exclusion constraints and editing a structured artifact while preserving forbidden fields. Vary context size and irrelevant-content placement. This is a feasibility sample, not sufficient evidence of predictive validity.

Use a few fixed checkpoints and a small, fixed probe set covering arbitrary facts, relevant facts, and constraints. Keep context sizes bounded initially, for example 8K–32K input tokens. Preserve the constraints in the actual supplied context; accidental truncation must be logged separately.

**API budget:** target $10–25, with a proposed hard pilot ceiling of $25. These are planning allowances, not a current provider quote. Before running, record exact model IDs, provider routes, current token prices, maximum calls, and a conservative upper-bound cost including long probe inputs, outputs, and retries. Reduce the planned run if it exceeds the cap; record incomplete execution rather than pretending it is the planned sample. Existing account access does not imply free calls. No paid runs are authorized or initiated by this document.

OpenRouter can be a convenient initial route if it serves the selected models. Pin the backend where possible and log provider changes. Avoid spending the first week building three interchangeable clients.

## Measurement safeguards

1. Probe a fork of each checkpoint with the same model configuration. Evaluate the main continuation without adding probe questions or answers. This measures a proxy from the same context, not an observation of the main continuation's hidden state.
2. Keep planted canaries identical across baseline and probe-predictor comparisons. A small no-canary control should check whether insertion itself changes behavior. Repeated echoed markers must be recognized as refreshed information.
3. Score unprompted behavior mechanically where possible. Audit a fixed sample manually; an LLM judge and arbitrary agreement threshold are unnecessary for exact structured outcomes.
4. Group all checkpoints, forks, and repeated variants of a base task into the same split. Hold out task instances, and fit preprocessing, predictor settings, and alarm thresholds using development data only.
5. Compare the same simple predictor with and without the fixed canary features. Give the baseline nonlinear length terms or a prespecified comparable model capacity so a weak baseline cannot manufacture an advantage.
6. Freeze a primary checkpoint before the scored action, selected by task structure rather than observed failure. Use one primary observation per trajectory for Gate 1. Analyze repeated checkpoints separately for Gate 2.
7. Include only checkpoints before the first violation in early-warning analysis. Report missed failures and false alarms per trajectory, not just lead time among successful detections.

## Prospective Gate 1 stop rule

The pilot is development data and is excluded from confirmatory evaluation. Before collecting confirmatory trajectories, commit the exact task distribution, seeds/split method, model configurations, predictor definitions, sample size, budget, and analysis script. Use pilot failure prevalence and simulations to choose a fixed sample size that can resolve the effect of interest. Do not inspect held-out results and then expand the sample until significance appears.

Primary endpoint: whether the unprobed continuation violates at least one prespecified constraint after the primary checkpoint and before the fixed task horizon.

Primary effect: **delta AUROC = AUROC(baseline + canary features) minus AUROC(baseline)** on held-out trajectories. Report results separately for each economical model. Compute a paired 95% bootstrap confidence interval, resampling independent task groups together across both predictors. Also report precision-recall performance and failure prevalence; AUROC is not an operational alarm policy.

Choose **0.05 AUROC improvement** as the minimum effect worth further effort for this project. This is a prospective project choice, not a universal scientific threshold.

- **PASS:** On at least one of the two prespecified economical models, delta AUROC is at least 0.05 and the lower confidence bound exceeds zero, with correction for testing two models. Use 97.5% per-model two-sided intervals for this decision. Report the other model regardless of outcome; a single-model result supports only a limited claim.
- **KILL for insufficient signal:** On both economical models, the upper bound of the corresponding interval is below 0.05. Stop development of this canary predictor; document that a useful incremental effect was not supported in the tested setting.
- **INCONCLUSIVE:** All other outcomes, including too few positive/negative outcomes or a budget-limited sample too small to resolve the effect. Do not label this evidence that canaries cannot work. Pause expansion at the cap and write up the uncertainty.

Require at least 30 failure and 30 success trajectories per model in held-out evaluation before treating its result as decision-grade; this is a minimum sanity check, not a power guarantee. If the planned sample cannot meet it, report inadequate information rather than silently selecting only failing cases.

Proposed total allocation through the Gate 1 decision: **30–40 hands-on hours and at most $100 in API spend, including the pilot**. If simulation and actual pricing show that meaningful precision cannot fit this allocation, the next result is a feasibility decision, not an underpowered claim of success or failure. These caps are recommendations for a subsequent run, not spending already performed.

## Gate 2 and next decision

If Gate 1 passes, use the already-logged pre-failure checkpoints to evaluate early warning. Set alarm thresholds on development data at a prespecified 10% trajectory-level false-alarm target; report the realized held-out false-alarm rate, failure detection rate, and lead time in agent actions. This initial target is an operating point for comparison, not a production standard.

The frontier model is a control and descriptive comparison in the pilot. A low failure count means its predictive performance is not estimable; it does not invalidate a useful economical-model result. Expansion of its sample is conditional on budget and the paper's claims.

Recommended sequence: pilot bundle → Gate 1 decision → Gate 2 analysis and focused paper → recovery experiment only if warranted. Keep the contradiction benchmark outside this first study.
