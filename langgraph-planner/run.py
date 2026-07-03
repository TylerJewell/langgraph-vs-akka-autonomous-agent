"""Drive a VentureScope planner to completion, handling ask_user interrupts.

Usage:
    python run.py            # god-node topology
    python run.py refactored # Fable-5 tick/prepare/select/decide/guard topology

Both share state, tools, and model; only the graph topology differs. A scripted
"user" answers the ask_user interrupts so the run is fully reproducible.
"""
from __future__ import annotations

import sys

from langgraph.types import Command

SCRIPTED_ANSWERS = {
    "region": "US",
    "currency": "USD",
    "target_segment_pct": "0.1",
}

INITIAL = {
    "iterations": 0,
    "max_iters": 20,
    "status": "running",
    "collected": {},
    "ask_cap": {},
    "search_cap": {},
    "calc_status": "NONE",
    "calc_fail_count": 0,
    "events": [],
}


def main(which: str) -> None:
    if which == "refactored":
        from venturescope.agent_refactored import build_graph, NODE_COUNT
    else:
        from venturescope.agent import build_graph, NODE_COUNT

    graph = build_graph()
    config = {"configurable": {"thread_id": "demo-1"}}

    result = graph.invoke(INITIAL, config)
    checkpoints = 1
    # resume loop: each ask_user surfaces an interrupt we answer from the script
    while "__interrupt__" in result:
        intr = result["__interrupt__"][0].value
        field = intr["field"]
        answer = SCRIPTED_ANSWERS.get(field, "unknown")
        print(f"  [ask_user] {intr['question']!r} -> {answer!r}")
        result = graph.invoke(Command(resume=answer), config)
        checkpoints += 1

    print(f"\n=== {which} topology ({NODE_COUNT} nodes) ===")
    print(f"status      : {result.get('status')}")
    print(f"iterations  : {result.get('iterations')}")
    print(f"SOM result  : {result.get('calc_result')}")
    print(f"resume hops : {checkpoints}")
    print(f"collected   : {result.get('collected')}")
    print("event trail :")
    for e in result.get("events", []):
        print(f"    {e}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "god")
