# ADR 0006: Operational Knowledge Ownership

## Status

Accepted

## Context

ChironAI now has clear code ownership boundaries, but operational knowledge was
still spread across planning notes, local agent memory, CI logs, and individual
module READMEs. That creates bus-factor risk: a new contributor can read the
architecture and still miss how to diagnose Qdrant failures, extension startup
problems, proxy journal traces, or API drift.

## Decision

We treat operational knowledge as maintained project documentation:

1. `docs/RUNBOOK.md` owns incident procedures, diagnostics, expected signals,
   and recovery commands.
2. `docs/legacy_map.md` owns active tails: owner, reason kept, removal trigger,
   and verification path.
3. Module READMEs own module-specific diagnostics that should not be duplicated
   in route code or CoreUI.
4. `docs/ONBOARDING.md` owns the contributor walkthrough and points readers to
   the runbook for recovery workflows.
5. LogsManager remains internal-only and documents how agents inspect completed
   proxy journal traces.

## Consequences

- **Positive:**
  - Operational recovery is reviewable and versioned with code changes.
  - New contributors can diagnose common failures without relying on private
    context.
  - Cleanup work can require docs updates when they create or retire a tail.
- **Negative:**
  - Docs must be updated when ownership or recovery commands change.
  - Runbook commands can drift if gates are renamed without a docs update.
- **Neutral:**
  - Human bus-factor work still requires a second contributor; this ADR only
    captures the AI-addressable documentation portion.

## References

- `docs/RUNBOOK.md`
- `docs/legacy_map.md`
- `docs/ONBOARDING.md`
- `CoreModules/LogsManager/README.md`
- `docs/ONBOARDING.md`
