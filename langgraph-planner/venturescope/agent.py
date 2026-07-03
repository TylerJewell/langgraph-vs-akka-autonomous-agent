"""VentureScope planner -- the ORIGINAL "god node" topology.

Reconstructed from the published graph:

    planner_start -> plan -> {search, ask_user, reflect, calculate, finish}
    search   -> observe (if last_observation) else plan
    observe  -> plan
    ask_user -> observe_user -> plan
    calculate-> plan
    reflect  -> plan
    finish   -> planner_end

Everything of consequence happens inside `plan_node`: iteration control,
bootstrap questions, preparation, the deterministic decision ladder, the LLM
call, the post-LLM guard rewrites, and bookkeeping. This is the ~350-line
monolith the Twilight of the Gods study set out to decompose. The other nodes
are thin executors that loop back to `plan`.

Governance/audit is hand-rolled: every node appends to state["events"].
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from .llm import get_model
from .state import (
    BOOTSTRAP_FIELDS,
    CALC_FIELD,
    RAW_INPUT_FIELDS,
    RECIPE,
    PlannerDecision,
    PlannerState,
)
from .tools import decompose, run_calculator, web_search

_MODEL = get_model()
_ASK_CAP = 2
_SEARCH_CAP = 2
_CALC_FAIL_CAP = 2


def _ev(state: PlannerState, msg: str) -> list:
    return state.get("events", []) + [f"i{state.get('iterations', 0)}: {msg}"]


def _coerce(field: str, raw):
    if field in ("region", "currency"):
        return str(raw).strip()
    try:
        return float(raw)
    except (TypeError, ValueError):
        return raw


# ===========================================================================
# THE GOD NODE. One function, every responsibility. This is the thing under
# study -- note how much routing logic is hidden here rather than in the graph.
# ===========================================================================
def plan_node(state: PlannerState) -> dict:
    out: dict = {}
    collected = dict(state.get("collected", {}))
    events = state.get("events", [])

    # -- duty 1: iteration control + early stop ----------------------------
    iterations = state.get("iterations", 0) + 1
    out["iterations"] = iterations
    out["decision_origin"] = None
    out["decision"] = None
    if state.get("status") == "aborted" or iterations > state.get("max_iters", 12):
        out["decision"] = PlannerDecision("finish", reason="early stop: cap/abort")
        out["decision_origin"] = "deterministic"
        out["events"] = events + [f"i{iterations}: early-stop"]
        return out

    # -- duty 2: bootstrap region/currency first ---------------------------
    for bf in BOOTSTRAP_FIELDS:
        if bf not in collected:
            spec = next(s for s in RECIPE if s.name == bf)
            out["decision"] = PlannerDecision("ask_user", target=bf, question=spec.question,
                                              reason="bootstrap")
            out["decision_origin"] = "deterministic"
            out["pending_field"] = bf
            out["pending_question"] = spec.question
            out["events"] = events + [f"i{iterations}: bootstrap {bf}"]
            return out

    # -- duty 3: preparation (decompositions, recipes, schema) -------------
    for spec in RECIPE:
        if spec.source == "derived" and spec.name != CALC_FIELD and spec.name not in collected:
            val = decompose(spec.name, collected)
            if val is not None:
                collected[spec.name] = val
                events = events + [f"i{iterations}: derived {spec.name}={val}"]
    out["collected"] = collected
    out["schema"] = {s.name: s.source for s in RECIPE}
    out["dynamic_decompositions"] = {"adoption_rate": ["target_segment_pct"]}
    out["recipes"] = {"som": list(RAW_INPUT_FIELDS) + ["adoption_rate"]}

    # -- duty 4: deterministic decision ladder -----------------------------
    calc_status = state.get("calc_status", "NONE")
    calc_fail = state.get("calc_fail_count", 0)

    if calc_status in ("BLOCKED", "ERROR") and calc_fail >= _CALC_FAIL_CAP:
        out["decision"] = PlannerDecision("finish", reason="calc cap exceeded -> abort")
        out["decision_origin"] = "deterministic"
        out["status"] = "aborted"
        out["events"] = events + [f"i{iterations}: calc-cap abort"]
        return out

    if calc_status == "SUCCESS":
        out["decision"] = PlannerDecision("finish", reason="calc succeeded")
        out["decision_origin"] = "deterministic"
        out["events"] = events + [f"i{iterations}: calc-success finish"]
        return out

    missing_raw = [f for f in RAW_INPUT_FIELDS if f not in collected]
    if not missing_raw and "adoption_rate" in collected and CALC_FIELD not in collected:
        # all inputs present -> calculate
        out["decision"] = PlannerDecision("calculate", target=CALC_FIELD, reason="inputs ready")
        out["decision_origin"] = "deterministic"
        out["events"] = events + [f"i{iterations}: -> calculate"]
        return out

    # acquisition fast path: pursue the first open externally-sourced field
    for spec in RECIPE:
        if spec.source == "derived" or spec.name in collected:
            continue
        if spec.source == "web":
            if state.get("search_cap", {}).get(spec.name, 0) < _SEARCH_CAP:
                out["decision"] = PlannerDecision("search", target=spec.name,
                                                  query=spec.query.format(**collected),
                                                  reason="fast-path acquire (web)")
                out["decision_origin"] = "deterministic"
                out["events"] = events + [f"i{iterations}: search {spec.name}"]
                return out
        elif spec.source == "user":
            if state.get("ask_cap", {}).get(spec.name, 0) < _ASK_CAP:
                out["decision"] = PlannerDecision("ask_user", target=spec.name,
                                                  question=spec.question,
                                                  reason="fast-path acquire (user)")
                out["decision_origin"] = "deterministic"
                out["pending_field"] = spec.name
                out["pending_question"] = spec.question
                out["events"] = events + [f"i{iterations}: ask {spec.name}"]
                return out

    # -- duty 5: LLM decide (only if the ladder produced nothing) ----------
    try:
        decision = _MODEL.structured({**state, "collected": collected})
        out["decision_origin"] = "llm"
    except Exception:
        out["decision"] = PlannerDecision("finish", reason="llm failed")
        out["decision_origin"] = "llm"
        out["llm_failed"] = True
        out["events"] = events + [f"i{iterations}: llm-failed finish"]
        return out

    # -- duty 6: guard / post-LLM correction -------------------------------
    if decision.action == "ask_user":
        if state.get("ask_cap", {}).get(decision.target, 0) >= _ASK_CAP:
            decision = PlannerDecision("search", target=decision.target,
                                       query=f"{decision.target} in {collected.get('region','')}",
                                       reason="ask cap -> search fallback")
        else:
            out["pending_field"] = decision.target
            out["pending_question"] = decision.question
    if decision.action == "search" and state.get("search_cap", {}).get(decision.target, 0) >= _SEARCH_CAP:
        decision = PlannerDecision("ask_user", target=decision.target,
                                   question=f"Please provide {decision.target}:",
                                   reason="search cap -> ask fallback")
        out["pending_field"] = decision.target
        out["pending_question"] = decision.question

    # -- duty 7: bookkeeping ----------------------------------------------
    out["decision"] = decision
    out["events"] = events + [f"i{iterations}: llm/guard -> {decision.action} {decision.target or ''}"]
    return out


# ---- thin executor nodes ---------------------------------------------------

def search_node(state: PlannerState) -> dict:
    d = state["decision"]
    obs, value = web_search(d.target, d.query or "")
    caps = dict(state.get("search_cap", {}))
    caps[d.target] = caps.get(d.target, 0) + 1
    return {"last_observation": obs, "pending_field": d.target, "search_cap": caps,
            "_search_value": value, "events": _ev(state, f"search {d.target} -> {value}")}


def observe_node(state: PlannerState) -> dict:
    field = state.get("pending_field")
    value = state.get("_search_value")
    collected = dict(state.get("collected", {}))
    if field is not None and value is not None:
        collected[field] = value
    return {"collected": collected, "last_observation": None, "pending_field": None,
            "events": _ev(state, f"observe {field}")}


def ask_user_node(state: PlannerState) -> dict:
    # The SOLE human-interrupt node. Suspends the graph; resumes with the answer.
    answer = interrupt({"question": state.get("pending_question"),
                        "field": state.get("pending_field")})
    return {"user_answer": answer}


def observe_user_node(state: PlannerState) -> dict:
    field = state.get("pending_field")
    answer = state.get("user_answer")
    collected = dict(state.get("collected", {}))
    caps = dict(state.get("ask_cap", {}))
    if field is not None:
        collected[field] = _coerce(field, answer)
        caps[field] = caps.get(field, 0) + 1
    return {"collected": collected, "ask_cap": caps, "pending_question": None,
            "pending_field": None, "user_answer": None,
            "events": _ev(state, f"observe_user {field}={collected.get(field)}")}


def calculate_node(state: PlannerState) -> dict:
    status, result = run_calculator(state.get("collected", {}))
    out = {"calc_status": status, "events": _ev(state, f"calculate -> {status}")}
    if status == "SUCCESS":
        collected = dict(state.get("collected", {}))
        collected[CALC_FIELD] = result
        out["collected"] = collected
        out["calc_result"] = result
    else:
        out["calc_fail_count"] = state.get("calc_fail_count", 0) + 1
    return out


def reflect_node(state: PlannerState) -> dict:
    return {"events": _ev(state, "reflect")}


def finish_node(state: PlannerState) -> dict:
    return {"status": "done", "events": _ev(state, "finish")}


# ---- conditional edges (pure -- they must NOT mutate state) ----------------

def route_from_plan(state: PlannerState) -> str:
    return state["decision"].action


def route_from_search(state: PlannerState) -> str:
    return "observe" if state.get("last_observation") else "plan"


# ---- graph assembly --------------------------------------------------------

def build_graph():
    g = StateGraph(PlannerState)
    g.add_node("plan", plan_node)
    g.add_node("search", search_node)
    g.add_node("observe", observe_node)
    g.add_node("ask_user", ask_user_node)
    g.add_node("observe_user", observe_user_node)
    g.add_node("calculate", calculate_node)
    g.add_node("reflect", reflect_node)
    g.add_node("finish", finish_node)

    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", route_from_plan, {
        "search": "search", "ask_user": "ask_user", "reflect": "reflect",
        "calculate": "calculate", "finish": "finish",
    })
    g.add_conditional_edges("search", route_from_search, {"observe": "observe", "plan": "plan"})
    g.add_edge("observe", "plan")
    g.add_edge("ask_user", "observe_user")
    g.add_edge("observe_user", "plan")
    g.add_edge("calculate", "plan")
    g.add_edge("reflect", "plan")
    g.add_edge("finish", END)

    return g.compile(checkpointer=MemorySaver())


# node count for the maintainability comparison
NODE_COUNT = 8
