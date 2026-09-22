# Space Canary

Testing whether context probes predict agent failures before they happen.

**Status: Stage A calibration is complete but invalid for model qualification. Stage B and the main run remain locked.** GLM and DeepSeek produced no failures at the frozen difficulty. Haiku exposed a response-parser defect, so its apparent failures are harness artifacts. See `CALIBRATION_STAGE_A.md` and `AMENDMENT_001.md`.

## Reproduce

Python 3.9+:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m space_canary dry-run
python -m space_canary analyze
```

The run produces `results/mock/raw.jsonl`, request/response caches, individual trajectory files, a SQLite reservation ledger, a JSON ledger export, analysis JSON, three plots and a one-page findings summary. Repeating the same command resumes existing trajectories. If a trajectory is interrupted, replay reconstructs its environment from hashed cached responses without new mock calls. Changing configuration requires a new output directory. Use one runner per output directory; the ledger itself serializes reservations transactionally.

```sh
python -m space_canary estimate --config config.glm.yaml --output results/glm-plan
```

This prints the locked allocation without running any model. Paid execution is locked in the checked-in configuration after the completed Stage A allocation. No API key is needed for estimates, dry runs, tests, or analysis.

The prospective parser-repair rerun is Haiku-only and has an independent disabled approval switch and $1.85 hard cap:

```sh
python -m space_canary recalibrate-haiku --config config.glm.yaml --output results/live/haiku-recalibration-v1
```

It refuses all network calls until `haiku_recalibration.live_enabled` and its paid approval field are set in a public commit.

## Cost choices

| Allocation, including calibration | Estimated total | Opus share |
| --- | ---: | ---: |
| Haiku + DeepSeek + 15 Opus trajectories | $27.12 | $17.36 |
| GLM 5.3 + DeepSeek + 6 Opus trajectories | $14.53 | $6.94 |

The original allocation fails the $25 total / $8 frontier caps. The locked design uses GLM and DeepSeek as inferential arms and reduces Opus to a descriptive control. Opus receives no delta-AUROC confidence interval and cannot affect PASS/STOP. If GLM's five-trajectory calibration failure rate is below 20%, Haiku replaces it on the same frozen task design. Model definitions and published catalog pricing are in the config files; the captured source is [OpenRouter's public catalog](https://openrouter.ai/api/v1/models). Prices vary by endpoint and must be pinned before live use.

Estimates use UTF-8/4 input approximations and maximum configured output tokens, without caching discounts or retries. They are planning estimates, not guaranteed bills. The SQLite ledger reserves an upper bound before dispatch, rejects cap overruns, and retains unresolved reservations across restarts. A paid transport must supply a validated upper bound and reconcile actual usage; display estimates must never substitute for that bound.

Calibration is staged. Stage A runs GLM and DeepSeek only, adding Haiku only if the prespecified replacement rule fires, under a $2.40 hard cap. Stage B contains the descriptive Opus arm and remains locked pending Stage A qualification and separate approval. Before every dispatch, reservations use model-specific measured input tokens plus the configured maximum output; the byte estimator is display-only.

## Research protocol

Preregistration commit: [`b39b105657d64a02fac8c5158edd23281ee7e7de`](https://github.com/0xAshraFF/space-canary/commit/b39b105657d64a02fac8c5158edd23281ee7e7de). No paid calls preceded this commit.

Read `PREREGISTRATION.md` and `verdict.md`. The smaller pilot cannot meet the earlier decision-grade minimum of 30 failed plus 30 successful trajectories per economical model. An underpowered result remains inconclusive. No main sample size is approved yet.

Current analysis evaluates any next-window failure, uses grouped outer CV and nested training-only alarm selection, and excludes post-failure checkpoints. It emits per-type ablations and paired cluster intervals. A constraint-specific confirmatory endpoint, placement ablations, stronger task diversity, native tokenization and live provider integration remain future work. The cleaning environment is deliberately small; this is not yet a full coding-agent benchmark.

Constraint paraphrase scoring uses a conservative lexical rubric. Token positions are estimates. API determinism cannot be promised by setting a local seed; exact replay depends on cached responses.

## Files

- `space_canary/environment.py`: mock tools and mechanical outcomes.
- `space_canary/probes.py`: canary metadata, isolated probes, scoring and future labels.
- `space_canary/storage.py`: atomic cache writes and transactional cost reservations.
- `space_canary/runner.py`: deterministic mock client, resumable trajectories and planning estimates.
- `space_canary/analysis.py`: grouped diagnostics and plots.
- `tests/`: behavioral verification of isolation, scoring, budgets, resume and metrics.

## Prior art

[Hermes drift-canary proposal](https://github.com/NousResearch/hermes-agent/issues/55550) overlaps with the runtime sentinel concept. [AdaCoM](https://arxiv.org/abs/2605.30785) studies adaptive context management. This project investigates predictive validity; it makes no invention-of-canaries claim.
