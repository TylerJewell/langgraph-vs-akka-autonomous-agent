"""VentureScope planner state.

Reconstructed from the published `current-graph` description of the private
`src/venturescope/planner/agent.py`. Field names mirror the ones named in the
Twilight of the Gods materials: iterations, status, decision, decision_origin,
recipes, schema, dynamic_decompositions, last_observation, llm_failed.

Domain: collect the parameters needed to size a market opportunity (a simple
SOM estimate), gathering each parameter either from web search or from the user
depending on conversation state, then run a calculator once inputs are ready.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, TypedDict


# ---- Domain: the parameters VentureScope must collect ----------------------

# Each field is acquired one of three ways, mirroring the study's note that the
# same parameter can come from search OR the user depending on state:
#   web     -> obtained via the `search` node
#   user    -> obtained via the `ask_user` node
#   derived -> obtained via decomposition of other fields (no external I/O)
FieldSource = Literal["web", "user", "derived"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    source: FieldSource
    question: str = ""          # used when source == "user"
    query: str = ""             # used when source == "web"
    depends_on: tuple[str, ...] = ()   # used when source == "derived"


# The "recipe" for a SOM estimate. `region` and `currency` are the bootstrap
# fields that must be collected first (see god-node duty #2).
RECIPE: tuple[FieldSpec, ...] = (
    FieldSpec("region", "user", question="Which region are we sizing? (e.g. US, EU, SEA)"),
    FieldSpec("currency", "user", question="Which currency should results be reported in?"),
    FieldSpec("population", "web", query="population of {region}"),
    FieldSpec("target_segment_pct", "user", question="What fraction of the population is your target segment? (0-1)"),
    FieldSpec("annual_spend_per_user", "web", query="average annual spend per user in {region} for this category"),
    FieldSpec("adoption_rate", "derived", depends_on=("target_segment_pct",)),
    FieldSpec("som", "derived", depends_on=("population", "target_segment_pct", "annual_spend_per_user", "adoption_rate")),
)

BOOTSTRAP_FIELDS = ("region", "currency")
RAW_INPUT_FIELDS = ("population", "target_segment_pct", "annual_spend_per_user")
CALC_FIELD = "som"


# ---- Planner decision (structured LLM output) ------------------------------

Action = Literal["search", "ask_user", "calculate", "reflect", "finish"]


@dataclass
class PlannerDecision:
    action: Action
    target: Optional[str] = None      # which field this decision is about
    query: Optional[str] = None       # for search
    question: Optional[str] = None    # for ask_user
    reason: str = ""


# ---- Graph state -----------------------------------------------------------

CalcStatus = Literal["NONE", "SUCCESS", "BLOCKED", "ERROR"]


class PlannerState(TypedDict, total=False):
    # iteration / lifecycle
    iterations: int
    max_iters: int
    status: Literal["running", "aborted", "done"]

    # decision plumbing
    decision: Optional[PlannerDecision]
    decision_origin: Optional[Literal["deterministic", "llm"]]
    llm_failed: bool

    # preparation artifacts
    recipes: dict
    schema: dict
    dynamic_decompositions: dict

    # collected values + acquisition bookkeeping
    collected: dict            # field name -> value
    ask_cap: dict              # field name -> times asked (retry caps)
    search_cap: dict           # field name -> times searched

    # calculator lifecycle
    calc_status: CalcStatus
    calc_result: Optional[float]
    calc_fail_count: int

    # I/O for the interrupt/resume pair
    last_observation: Optional[str]
    _search_value: Optional[float]      # value carried search -> observe
    pending_question: Optional[str]     # set by ask_user, consumed by observe_user
    pending_field: Optional[str]
    user_answer: Optional[str]          # supplied on resume

    # audit trail (governance): every state-changing hop appends an event here.
    # In LangGraph this is hand-rolled; contrast with Akka's runtime event stream.
    events: list
