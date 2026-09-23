# Haiku parser-repair recalibration

Date: 2026-09-23

## Verdict

**NOT EVALUABLE — pause paid runs and redesign the task environment.**

Claude Haiku 4.5 completed all five corrected trajectories without a task error or constraint violation. Its 0% failure rate is below the preregistered 20% qualification floor. Together with the original 0/5 results for GLM 5.3 and DeepSeek V3.2, the frozen environment provides no positive outcomes for Gate 1 prediction.

This result does not show that canary signals lack predictive value. It shows that this task distribution cannot test the hypothesis on these models.

## Audit

- Five trajectories, 24 actions and 7 isolated probes per trajectory.
- All 120 actions succeeded: 96 responses used a single Markdown JSON fence and 24 used bare JSON. The amended parser handled both forms.
- Each canary type scored 34/35. At the sole zero-scored checkpoint, Haiku supplied all three correct values under `calibration_code`, `multiplier`, and `schema_constraint` rather than the required `arbitrary`, `relevant`, and `constraint` keys. This is a schema-compliance miss, not evidence that the facts were forgotten.
- No context/constraint, arithmetic/value, or format/action outcome failures occurred.
- OpenRouter billed **$1.672573**, below the approved **$1.85** cap, for 155 successful calls.
- Combined billed calibration spend is **$3.954492**: $2.281919 for the original Stage A run and $1.672573 for this repair run.

## Decision

Do not run Opus or the planned main sample. A descriptive frontier arm cannot repair the absence of outcome variation in the economical arms.

The next artifact should be a new, versioned task-environment design developed without treating the completed calibration as confirmatory evidence. It should create delayed dependencies and realistic opportunities for context-specific errors, validate that failures are not parser or arithmetic artifacts, and then freeze a fresh calibration protocol before any more paid model calls.
