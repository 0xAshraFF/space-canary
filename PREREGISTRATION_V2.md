# V2 development calibration protocol

Status: prospective, paid execution disabled. References: original preregistration `b39b105657d64a02fac8c5158edd23281ee7e7de` and v1 final report commit `c301c5d9af6cbae42dece00ce26df5eb28295716`.

## Frozen allocation proposed for approval

Use `config.v2.yaml` with seeds 202609301, 202609302, and 202609303, each in both families and both conditions. Run 12 trajectories per model: six delayed and six refreshed, 24 in total. Use DeepSeek V3.2 on GMICloud FP8 and Haiku 4.5 on Anthropic with the inherited price ceilings and no routing fallback. GLM and Opus are excluded from this development allocation.

Each trajectory contains 24 actions and 7 isolated probes, for 372 calls per model, 744 total. The proposed combined hard cap is $6; no earlier approval funds this allocation. Planning input counts use an approximation and ideal action transcripts, with 512 output tokens budgeted per call. Live dispatch must instead reserve measured model-specific input plus the maximum output at pinned price ceilings, using the existing transactional ledger. Retain uncertain requests and stop at the cap even if the design remains incomplete.

Before paid calls, record fresh endpoint availability and price checks, explicit approval, and this protocol's public commit hash in the config, then push that config. Any necessary change to models, tasks, or request settings requires a dated amendment before the affected calls. Use a new output directory. Store the exact config in its manifest.

## Qualification and audit rules

This calibration determines whether an environment is worth studying. It cannot produce a confirmatory Gate 1 PASS/STOP or an effect-size confidence interval.

For each model, use only its six `delayed` trajectories for qualification. A candidate must have **2–4 trajectories with at least one constraint or policy-update error**, inclusive, and **no more than one trajectory with a format/action error**. Report task success and all error categories alongside this composite. Dependency-only or local selection failures cannot qualify the model for a study of policy adherence. A schema bug in the harness invalidates the affected trajectories and halts qualification pending public amendment.

Compare paired refreshed outcomes descriptively; do not use their results to select seeds or difficulty. Fewer policy-related failures when rules are repeated would motivate further study, not prove forgetting. If failures are concentrated in local work, parsing, or schema compliance, stop and audit the environment. No automatic model substitutions, extra seeds, longer contexts, or repeats to obtain a target rate.

If neither model qualifies, stop this paid calibration and report the result; do not initiate another redesign or collection automatically. If one qualifies, only a single-model follow-up could be considered. Even if both qualify, a reviewed analysis plan, precision simulation, release-aware baseline, and separate allocation are needed before main collection. No frontier call is authorized by this protocol.

Retain all completed and partial traces. Paired conditions and both models sharing a seed/family must remain in one group in any future split. Calibration instances must be excluded from the eventual main evaluation.

## Protocol changes relative to v1

The tasks, seeds, grouping, model allocation, and qualification endpoint are explicitly new. Reuse the transport, provider pins, tokenizer sources, caching, and ledger. Do not pool v1 calibration with v2 outcomes. Probe schema violations become missing measurements; raw answers remain available for audit. Frozen v1 result files are preserved.
