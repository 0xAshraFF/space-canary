# Space Canary — post-calibration verdict

Date: 2026-09-23

- **Verdict enum: PAUSE_AND_REDESIGN**
- **Confidence: 0.92** that the current frozen environment should not proceed to Stage B or the main study.
- **Evidence status: CALIBRATION_COMPLETE, HYPOTHESIS_UNTESTED.**

All three economical candidates completed five valid trajectories with zero task failures after correcting the Haiku parser defect. Gate 1 therefore has no positive outcome variation and cannot be estimated. Spending on Opus would be descriptive only and would not change that decision.

The project idea remains worth a bounded redesign because the core question—whether isolated canary probes predict later unprompted constraint failures—was not answered. The present task mostly repeats short, mechanically simple transformations over contexts that reached roughly 18k prompt tokens. Strong models completed it reliably.

## Smallest next artifact

Create a versioned environment v2 specification and offline validator before making another paid call. Time box: **6–10 hours**. API budget: **$0** for this artifact.

The specification should add two or three task families with delayed dependencies, conflicting but clearly ordered instructions, and irreversible action opportunities. It should define mechanical labels that distinguish context/constraint loss from arithmetic, formatting, and tool-schema failures. Use deterministic fixtures to prove that each intended failure mode is reachable, then preregister a fresh, small calibration with explicit stop rules and its own spending approval.

Do not tune the existing frozen instances until a chosen model fails. Treat environment v2 as a new development study, record all iterations, and freeze the final distribution before collecting qualification data.
