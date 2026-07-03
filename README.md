# Twilight of the Gods → VentureScope: LangGraph vs Akka AutonomousAgent

A runnable, side-by-side reconstruction inspired by
[Twilight of the Gods](https://wtf.korridzy.com/twilight-of-the-gods/), where 11
models refactored a 350-line LangGraph "god node." This repo asks the follow-on
question: **was the god node a LangGraph artifact?** It rebuilds the same
parameter-collecting planner (`VentureScope`, a market-size/SOM estimator) three
ways and compares them on **governance, maintainability, and flexibility** — not
model quality. One model, held fixed. Same result on every path: `SOM = 1.19B USD`.

## Layout

```
langgraph-planner/   VentureScope on LangGraph
  venturescope/agent.py             the god-node topology (plan_node + 8-node graph)
  venturescope/agent_refactored.py  Fable-5's winning tick/prepare/select/decide/guard
  run.py                            drive either topology end to end
akka-planner/        VentureScope as an Akka AutonomousAgent (SDK 3.6.0-M1)
  .../VentureScopePlanner.java      goal + task + tools + guardrail + delegation (~28 LOC)
  .../VentureScopeTools.java        search / ask_user / calculate as plain @FunctionTools
  .../CurrencyPolicyGuard.java      governance-as-code (TextGuardrail)
  .../api/VentureScopeEndpoint.java start + status + free notificationStream audit
comparison/metrics.md               the honest counts and change-scenario diffs
linkedin-post.md                    the writeup
```

## Run it

LangGraph (both topologies produce the same SOM; the refactor just adds checkpoints):

```bash
cd langgraph-planner && pip install -r requirements.txt
python run.py god
python run.py refactored
```

Akka (deterministic, offline — scripted model, no API key needed):

```bash
cd akka-planner && mvn test
```

## The claim

The god node was durable control-loop plumbing LangGraph forces you to hand-build,
because every node is a checkpoint write. Fable-5's award-winning fix makes the
graph *bigger* (8 → 12 nodes) to make routing legible. Akka's `AutonomousAgent`
provides the loop, the durability, the iteration cap, and the audit stream as
runtime features — so the same planner is ~28 lines of orchestration with no
graph, and governance/flexibility become one-line capabilities. See
[`comparison/metrics.md`](comparison/metrics.md) for the receipts and the caveats.
