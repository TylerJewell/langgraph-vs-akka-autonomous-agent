"""External-effect helpers: web search, the calculator, and decomposition.

Kept deterministic/offline so the reconstruction runs anywhere. These are the
same regardless of which planner topology (god node vs Fable-5) drives them.
"""
from __future__ import annotations

from .state import CALC_FIELD, RAW_INPUT_FIELDS

# Canned "search" results so the loop terminates deterministically.
_SEARCH_RESULTS = {
    "population": 331_000_000.0,
    "annual_spend_per_user": 240.0,
}


def web_search(field: str, query: str) -> tuple[str, float]:
    """Return (observation_text, value) for a web-sourced field."""
    value = _SEARCH_RESULTS.get(field)
    if value is None:
        return (f"no result for '{query}'", float("nan"))
    return (f"search[{query}] = {value}", value)


def decompose(field: str, collected: dict) -> float | None:
    """Derive a value from already-collected fields (no external I/O)."""
    if field == "adoption_rate":
        seg = collected.get("target_segment_pct")
        return None if seg is None else round(min(0.9, float(seg) * 1.5), 4)
    if field == "som":
        try:
            return (float(collected["population"])
                    * float(collected["target_segment_pct"])
                    * float(collected["adoption_rate"])
                    * float(collected["annual_spend_per_user"]))
        except (KeyError, TypeError, ValueError):
            return None
    return None


def run_calculator(collected: dict) -> tuple[str, float | None]:
    """The SOM calculator. Returns (status, result).

    BLOCKED if a required raw input is missing; SUCCESS once everything is
    present. Mirrors the study's calculator lifecycle (SUCCESS/BLOCKED/ERROR).
    """
    missing = [f for f in RAW_INPUT_FIELDS if f not in collected]
    if missing:
        return ("BLOCKED", None)
    if "adoption_rate" not in collected:
        return ("BLOCKED", None)
    result = decompose(CALC_FIELD, collected)
    if result is None:
        return ("ERROR", None)
    return ("SUCCESS", result)
