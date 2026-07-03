"""VentureScope planner -- Fable-5's winning decomposition.

The god `plan` node is split into five nodes, exactly as proposed in the
Twilight of the Gods materials:

    tick     -> iteration entry, terminal caps, bootstrap gate
    prepare  -> decompositions / recipes / schema
    select   -> deterministic decision ladder
    decide   -> the pure LLM call
    guard    -> post-LLM decision rewrites, then dispatch

    START -> tick -> {finish | ask_user | prepare}
    prepare -> select -> {guard (decision found) | decide (no decision)}
    decide  -> guard -> {search | ask_user | reflect | calculate | finish}
    <action nodes> -> tick   (cycle back to loop entry)

The executor nodes (search/observe/ask_user/observe_user/calculate/reflect/
finish) are unchanged and imported from the god-node module -- the refactor is
a topology change, not a behavior change. Note the cost the study flags: this
is MORE nodes (12 vs 8), i.e. MORE checkpoint boundaries, not fewer.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from .agent import (
    _ASK_CAP,
    _CALC_FAIL_CAP,
    _MODEL,
    _SEARCH_CAP,
    ask_user_node,
    calculate_node,
    finish_node,
    observe_node,
    observe_user_node,
    reflect_node,
    route_from_search,
    search_node,
)
from .state import (
    BOOTSTRAP_FIELDS,
    CALC_FIELD,
    RAW_INPUT_FIELDS,
    RECIPE,
    PlannerDecision,
    PlannerState,
)
from .tools import decompose


def tick_node(state: PlannerState) -> dict:
    out: dict = {"decision": None, "decision_origin": None,
                 "iterations": state.get("iterations", 0) + 1}
    i = out["iterations"]
    events = state.get("events", [])
    collected = state.get("collected", {})

    if state.get("status") == "aborted" or i > state.get("max_iters", 12):
        out["decision"] = PlannerDecision("finish", reason="early stop: cap/abort")
        out["decision_origin"] = "deterministic"
        out["events"] = events + [f"i{i}: early-stop"]
        return out

    for bf in BOOTSTRAP_FIELDS:
        if bf not in collected:
            spec = next(s for s in RECIPE if s.name == bf)
            out["decision"] = PlannerDecision("ask_user", target=bf, question=spec.question,
                                              reason="bootstrap")
            out["decision_origin"] = "deterministic"
            out["pending_field"] = bf
            out["pending_question"] = spec.question
            out["events"] = events + [f"i{i}: bootstrap {bf}"]
            return out

    out["events"] = events + [f"i{i}: tick"]
    return out


def prepare_node(state: PlannerState) -> dict:
    collected = dict(state.get("collected", {}))
    events = state.get("events", [])
    for spec in RECIPE:
        if spec.source == "derived" and spec.name != CALC_FIELD and spec.name not in collected:
            val = decompose(spec.name, collected)
            if val is not None:
                collected[spec.name] = val
                events = events + [f"i{state.get('iterations')}: derived {spec.name}={val}"]
    return {"collected": collected,
            "schema": {s.name: s.source for s in RECIPE},
            "dynamic_decompositions": {"adoption_rate": ["target_segment_pct"]},
            "recipes": {"som": list(RAW_INPUT_FIELDS) + ["adoption_rate"]},
            "events": events}


def select_node(state: PlannerState) -> dict:
    collected = state.get("collected", {})
    events = state.get("events", [])
    i = state.get("iterations")
    calc_status = state.get("calc_status", "NONE")
    calc_fail = state.get("calc_fail_count", 0)

    def deterministic(decision, note, extra=None):
        out = {"decision": decision, "decision_origin": "deterministic",
               "events": events + [f"i{i}: {note}"]}
        if extra:
            out.update(extra)
        return out

    if calc_status in ("BLOCKED", "ERROR") and calc_fail >= _CALC_FAIL_CAP:
        return deterministic(PlannerDecision("finish", reason="calc cap -> abort"),
                             "calc-cap abort", {"status": "aborted"})
    if calc_status == "SUCCESS":
        return deterministic(PlannerDecision("finish", reason="calc succeeded"), "calc-success finish")

    missing_raw = [f for f in RAW_INPUT_FIELDS if f not in collected]
    if not missing_raw and "adoption_rate" in collected and CALC_FIELD not in collected:
        return deterministic(PlannerDecision("calculate", target=CALC_FIELD, reason="inputs ready"),
                             "-> calculate")

    for spec in RECIPE:
        if spec.source == "derived" or spec.name in collected:
            continue
        if spec.source == "web" and state.get("search_cap", {}).get(spec.name, 0) < _SEARCH_CAP:
            return deterministic(
                PlannerDecision("search", target=spec.name,
                                query=spec.query.format(**collected), reason="fast-path (web)"),
                f"search {spec.name}")
        if spec.source == "user" and state.get("ask_cap", {}).get(spec.name, 0) < _ASK_CAP:
            return deterministic(
                PlannerDecision("ask_user", target=spec.name, question=spec.question,
                                reason="fast-path (user)"),
                f"ask {spec.name}",
                {"pending_field": spec.name, "pending_question": spec.question})

    # no deterministic decision -> fall through to the LLM (decide)
    return {"decision": None, "events": events + [f"i{i}: select -> decide"]}


def decide_node(state: PlannerState) -> dict:
    events = state.get("events", [])
    i = state.get("iterations")
    try:
        decision = _MODEL.structured(state)
        return {"decision": decision, "decision_origin": "llm",
                "events": events + [f"i{i}: llm -> {decision.action} {decision.target or ''}"]}
    except Exception:
        return {"decision": PlannerDecision("finish", reason="llm failed"),
                "decision_origin": "llm", "llm_failed": True,
                "events": events + [f"i{i}: llm-failed finish"]}


def guard_node(state: PlannerState) -> dict:
    decision = state["decision"]
    out: dict = {}
    if state.get("decision_origin") == "llm":
        if decision.action == "ask_user":
            if state.get("ask_cap", {}).get(decision.target, 0) >= _ASK_CAP:
                decision = PlannerDecision("search", target=decision.target,
                                           query=f"{decision.target} in {state.get('collected',{}).get('region','')}",
                                           reason="ask cap -> search")
            else:
                out["pending_field"] = decision.target
                out["pending_question"] = decision.question
        elif decision.action == "search" and \
                state.get("search_cap", {}).get(decision.target, 0) >= _SEARCH_CAP:
            decision = PlannerDecision("ask_user", target=decision.target,
                                       question=f"Please provide {decision.target}:",
                                       reason="search cap -> ask")
            out["pending_field"] = decision.target
            out["pending_question"] = decision.question
    out["decision"] = decision
    out["events"] = state.get("events", []) + [f"i{state.get('iterations')}: guard -> {decision.action}"]
    return out


# ---- routers (pure) --------------------------------------------------------

def route_from_tick(state: PlannerState) -> str:
    d = state["decision"]
    if d is None:
        return "prepare"
    return "finish" if d.action == "finish" else "ask_user"  # bootstrap bypasses guard


def route_from_select(state: PlannerState) -> str:
    return "guard" if state.get("decision") is not None else "decide"


def route_from_guard(state: PlannerState) -> str:
    return state["decision"].action


def build_graph():
    g = StateGraph(PlannerState)
    for name, fn in [("tick", tick_node), ("prepare", prepare_node), ("select", select_node),
                     ("decide", decide_node), ("guard", guard_node),
                     ("search", search_node), ("observe", observe_node),
                     ("ask_user", ask_user_node), ("observe_user", observe_user_node),
                     ("calculate", calculate_node), ("reflect", reflect_node),
                     ("finish", finish_node)]:
        g.add_node(name, fn)

    g.add_edge(START, "tick")
    g.add_conditional_edges("tick", route_from_tick,
                            {"prepare": "prepare", "ask_user": "ask_user", "finish": "finish"})
    g.add_edge("prepare", "select")
    g.add_conditional_edges("select", route_from_select, {"guard": "guard", "decide": "decide"})
    g.add_edge("decide", "guard")
    g.add_conditional_edges("guard", route_from_guard, {
        "search": "search", "ask_user": "ask_user", "reflect": "reflect",
        "calculate": "calculate", "finish": "finish",
    })
    g.add_conditional_edges("search", route_from_search, {"observe": "observe", "plan": "tick"})
    g.add_edge("observe", "tick")
    g.add_edge("ask_user", "observe_user")
    g.add_edge("observe_user", "tick")
    g.add_edge("calculate", "tick")
    g.add_edge("reflect", "tick")
    g.add_edge("finish", END)

    return g.compile(checkpointer=MemorySaver())


NODE_COUNT = 12
