# VentureScope: LangGraph vs Akka AutonomousAgent — structural comparison

Same agent, same single model, same result (`SOM = 1,191,600,000 USD`). The
question is not "which produces a better number" — it is **which is easier to
govern, maintain, and change.** All counts below are from the code in this repo.

## Source of truth

- LangGraph "before/after" reconstructed from the published Twilight of the Gods
  materials (the ~350-line `plan_node` god node and the winning **Fable-5**
  `tick/prepare/select/decide/guard` refactor). The original agent source is
  private; this is a faithful reconstruction, not the original code.
- Akka side built against the shipped `AutonomousAgent` API (SDK `3.6.0-M1`),
  verified: `mvn test` → task `COMPLETED`, `SOM = 1.19B USD`, guardrail passed.

## Maintainability (lines / structure)

| Concern | LangGraph god node | LangGraph Fable-5 | Akka AutonomousAgent |
|---|---|---|---|
| Orchestration node(s) | `plan_node`, 122 lines* | `tick/prepare/select/decide/guard` | **none** (runtime loop) |
| Graph nodes total | 8 | 12 (more checkpoints) | 0 |
| Conditional edge fns | 2 (must be pure) | 3 | 0 |
| State schema | 108-line `TypedDict` | same + 2 fields | typed task record, 4 fields |
| Iteration/`max_iters` code | hand-written | hand-written | `.maxIterationsPerTask(8)` |
| Checkpoint/serialization | per node boundary | per node boundary | runtime, implicit |
| Audit trail | hand-appended `events[]` | hand-appended `events[]` | runtime `notificationStream()` |
| Planner orchestration LOC | ~122 | ~150 across 5 nodes | **~28** (goal + 2 capabilities) |

\* Our reconstruction condenses the study's ~350-line original to 122; the ratio
to the Akka orchestration is the point, not the absolute number.

**The tell:** Fable-5's award-winning fix makes the graph *bigger* (8 → 12
nodes) because in LangGraph the only way to make routing legible is to promote it
to a node — and every node is a checkpoint write. The god node existed to *avoid*
that tax. Akka removes the dilemma: deterministic logic is plain code, the loop
is the runtime's, and only real durability boundaries cost anything.

## Governance

| Capability | LangGraph | Akka |
|---|---|---|
| Per-iteration audit (tokens, task, struggle) | instrument yourself | `notificationStream()`, free |
| Policy enforcement | a branch inside `plan_node` | `TextGuardrail`, logged/metered/traced by runtime |
| Struggle / stuck detection | build it | `TaskStruggleDetected`, `TaskApproachingMaxIterations` events |
| Intervention hook | none built-in | subscribe to the stream, react |

`CurrencyPolicyGuard` (34 lines) is an isolated, named, testable unit the runtime
evaluates on every response. In the god node the same rule is one more `if` in a
122-line function.

## Flexibility — three change scenarios

**1. Add a new user-sourced parameter (`competitor_count`).**
- Akka: add one `@FunctionTool` (or a branch in `askUser`) + widen `calculateSom`.
  Touches `VentureScopeTools.java`. No orchestration change.
- LangGraph: add to `RECIPE` (`state.py`), add a ladder branch + cap bookkeeping
  in `plan_node` (`agent.py`) **and** in `select_node` (`agent_refactored.py`),
  extend the calculator. Touches 3 files across both topologies.

**2. Delegate a hard-to-source parameter to a specialist.**
- Akka: **already implemented** — `MarketSpecialist` + `.capability(Delegation.to(...))`,
  one line on the planner. Proof by existence in the tree.
- LangGraph: new node(s), new edges, new routing in `plan_node`, new checkpoint
  boundaries, plus wiring the sub-result back into state.

**3. Tighten a stop policy (lower the iteration cap, add an abort condition).**
- Akka: change `.maxIterationsPerTask(8)`; add/adjust a guardrail. One line.
- LangGraph: edit `_CALC_FAIL_CAP` / `max_iters` handling inside the god node's
  duty-1 and duty-4 blocks (and the mirror in `tick_node`/`select_node`).

## Honest caveats

- The LangGraph side is a reconstruction from published excerpts, not the private
  original.
- Akka's first-class durable **human-input gate** ("External input capability") is
  documented but **not yet shipped**; `ask_user` here is a tool over an answer
  source. This is the one place LangGraph's `interrupt()` is currently more mature.
- We fixed a single model and did not race runtimes for latency — the claim is
  about structure, governance, and change cost, not model quality.
