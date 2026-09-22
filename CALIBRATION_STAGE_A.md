# Stage A calibration report

## Verdict

**INVALID FOR QUALIFICATION — do not run Stage B or the main study.**

The run completed 5 trajectories each for GLM 5.3, DeepSeek V3.2, and the prespecified Claude Haiku 4.5 fallback. GLM and DeepSeek had zero failures, below the locked 20% minimum. They are not evaluable at this task difficulty. Haiku's generated qualification file reports 4/5 failed trajectories, but a raw-response audit shows that all four are harness artifacts.

## Qualification audit

| Model | Raw runner result | Audited interpretation |
| --- | --- | --- |
| GLM 5.3 | 0/5 failed | Below minimum; replace under the prespecified rule |
| DeepSeek V3.2 | 0/5 failed | Not evaluable at the frozen difficulty |
| Claude Haiku 4.5 | 4/5 failed | Invalid because of the parser defect below |
| Claude Opus 4.6 | Not run | Stage B remains locked |

Haiku returned a valid `write_file` JSON object inside a Markdown `json` code fence on every action in four trajectories. `parse_answer` accepted only a bare JSON document and converted each fenced response to `{}`. The environment then recorded `task:invalid_action` and `task:missing_output` at all 24 turns. The fifth Haiku trajectory used bare JSON and passed. This formatting difference explains all 192 events: 96 invalid-action events and 96 missing-output events, with zero context/constraint or arithmetic/value events.

Those four continuations are also contaminated: each later model call received a tool error caused by the preceding parser rejection. Regrading cached text cannot recover valid trajectories. Haiku must be rerun after the parser fix if the project continues.

## Spend and operations

The local ledger recorded **$2.281919** billed under the approved **$2.40** hard cap. Cache usage attributes approximately $0.532546 to GLM, $0.081002 to DeepSeek, and $1.668228 to Haiku; per-request microusd rounding accounts for the small difference from the ledger total.

Each model made 155 successful calls: 24 actions and 7 isolated probes across 5 trajectories. One Haiku request received an OpenRouter new-account HTTP 429 before generation. It was retained, manually reconciled at $0, and retried with a distinct audited request hash after adding a 3.1-second Haiku dispatch interval. No Opus calls were made.

## Decision

The calibration does not establish a usable economical pair. It also confirms the concern that the observed Haiku failures were format/action failures rather than loss of context. Stage B would add no decision-relevant evidence and remains locked.

The smallest valid next experiment is a Haiku-only rerun of the same five frozen instances after the parser amendment. Based on observed usage it should cost about $1.67; a proposed hard cap is **$1.85**. This requires a new explicit paid allocation and a public commit containing the amendment before dispatch.
