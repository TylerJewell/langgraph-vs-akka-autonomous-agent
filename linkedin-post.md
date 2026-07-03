# LinkedIn post

---

**What a 350-line "god node" teaches us about agent frameworks**

There's a sharp writeup called *Twilight of the Gods* worth your time:
https://wtf.korridzy.com/twilight-of-the-gods/

The setup: a real LangGraph agent had a single `plan` node that had grown to ~350
lines — iteration control, bootstrap questions, routing, the LLM call, post-hoc
corrections, and bookkeeping all fused together. The author handed that node to 11
frontier models and asked each to refactor it, then had the models rank each
other's proposals. Fable-5's five-node decomposition (`tick / prepare / select /
decide / guard`) won the consensus.

It's a great study. But notice what every proposal — including the winner —
took as given: *the fix is a better graph.* Fable-5's winning answer actually
makes the graph **bigger**, from 8 nodes to 12. In LangGraph the only way to make
hidden routing legible is to promote it to a node, and every node boundary is a
checkpoint write. The god node existed to avoid exactly that cost. The refactor
trades a monolith for more checkpoints.

That made me want to run the comparison at the framework level. I rebuilt the same
market-sizing planner two ways — the LangGraph god-node topology, and as an Akka
`AutonomousAgent` — and ran both. Same single model, same result (SOM ≈ $1.19B).
Only the architecture differs.

**LangGraph vs Akka — the same agent, side by side:**

Orchestration
• LangGraph: a 122-line `plan_node` plus an 8-node graph and pure conditional edges
• Akka: ~28 lines — a goal plus two capabilities. No graph, no edges.

State
• LangGraph: a 108-line typed state schema you define and keep serializer-safe
• Akka: a 4-field typed task record; the runtime owns the rest

Iteration control
• LangGraph: hand-written step counter and `max_iters` checks inside the node
• Akka: `.maxIterationsPerTask(8)`

Durability
• LangGraph: a checkpoint write at every node boundary you design around
• Akka: implicit and runtime-owned — you write nothing

Audit / observability
• LangGraph: append to an `events[]` list in every node yourself
• Akka: a runtime `notificationStream()` emitting every iteration, token count,
  task transition, and struggle signal

Governance
• LangGraph: policy is another `if` branch inside the god node
• Akka: a `TextGuardrail` the runtime evaluates, logs, meters, and traces on every response

Adding a specialist for a hard parameter
• LangGraph: new nodes, new edges, new routing, new checkpoints
• Akka: one line — `.capability(Delegation.to(MarketSpecialist.class))`

The pattern underneath: most of that 350-line node was never planning logic. It
was durable-control-loop plumbing the framework made you build by hand. A runtime
that provides the loop, the persistence, the iteration caps, and the audit stream
turns that plumbing into a handful of declarations — and it turns governance and
extensibility into one-line capabilities instead of graph surgery.

The graph-as-representation model is a real strength when the control flow *is*
the product. But when your orchestration is mostly a durable loop around one LLM
call, the god node isn't a design smell — it's the framework showing through.

Repo with both sides runnable in the comments.

#AI #AgenticAI #LangGraph #Akka #SoftwareArchitecture #LLM

---

## First comment

Study: https://wtf.korridzy.com/twilight-of-the-gods/
Akka AutonomousAgent: https://doc.akka.io/sdk/autonomous-agents.html
Repo: <link>
