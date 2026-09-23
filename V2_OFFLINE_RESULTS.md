# V2 offline results

**Implementation validated; model experiment pending approval. New API spend: $0.**

The deterministic validator ran 60 trajectories: three seeds × two families × two reminder conditions × five scripted action policies, totaling 1,440 actions.

| Scripted policy | Trajectories | Passed | Observed error category | First failure |
| --- | ---: | ---: | --- | --- |
| Correct execution | 12 | 12 | None | None |
| Ignore protected field / restricted route | 12 | 0 | Constraint | Turn 13 |
| Reuse outdated batch | 12 | 0 | Policy update | Turn 13 |
| Omit queued content | 12 | 0 | Delayed dependency | Turn 13 |
| Emit an invalid tool | 12 | 0 | Format/action | Turn 13 |

Each faulty script triggered exactly three events in its intended category, at turns 13, 19, and 24. A checkpoint exists before each release with a full three-turn warning horizon. These are deliberately constructed fixtures, not measurements of LLM failure rates or predictive accuracy. The refreshed condition does not change a scripted policy's behavior.

Additional tests cover wrong values, complete versus partial task success, irreversible attempts, duplicate operation rejection, probe isolation, schema failures as missing values, paired-context equality except for reminders, live lock enforcement, and reconstruction from cached responses. The amended fenced-JSON parser is exercised by half the fixtures.

The complete regression suite passes **41 tests**, including two independent executors that derive their actions solely from visible controller messages instead of calling the environment's reference-action method.

The prepared real-model run uses 24 trajectories across DeepSeek and Haiku. Its planning estimate is **$5.11** using approximate input counts and maximum outputs, with a proposed **$6 combined hard cap**. This estimate is not a quote or approval. Provider availability and pinned price ceilings must be checked again before dispatch. The model experiment is the next step needed to learn whether v2 produces genuine failures.

Artifacts: `results/v2-offline/fixture-results.json`, `fixture-traces.json`, and `cost-estimate.json`. Task specification: `ENVIRONMENT_V2.md`. Prospective development protocol: `PREREGISTRATION_V2.md`.
