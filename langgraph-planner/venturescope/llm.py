"""The single planning model.

The study fixes ONE model for the comparison. We keep the model pluggable but
default to a deterministic offline `FakeModel` so the graph is runnable with no
API key and the structural comparison stays reproducible. Set VENTURESCOPE_MODEL
to a Claude model id (and ANTHROPIC_API_KEY) to drive it with a real model.

Note: in both the god-node and the Fable-5 refactor, the LLM is only consulted
when the deterministic ladder yields no decision -- matching the study's
"deterministic fast passes over completed tasks" observation.
"""
from __future__ import annotations

import os
from typing import Optional

from .state import RECIPE, PlannerDecision, PlannerState


class FakeModel:
    """Deterministic stand-in: pick the next open, externally-sourced field."""

    def structured(self, state: PlannerState) -> PlannerDecision:
        collected = state.get("collected", {})
        for spec in RECIPE:
            if spec.name in collected or spec.source == "derived":
                continue
            if spec.source == "web":
                return PlannerDecision("search", target=spec.name,
                                       query=spec.query.format(**collected),
                                       reason="llm: next open web field")
            if spec.source == "user":
                return PlannerDecision("ask_user", target=spec.name,
                                       question=spec.question,
                                       reason="llm: next open user field")
        return PlannerDecision("finish", reason="llm: nothing left to acquire")


class AnthropicModel:
    """Real Claude call with structured (tool-forced) output. Optional path."""

    def __init__(self, model_id: str):
        import anthropic
        self._client = anthropic.Anthropic()
        self._model = model_id

    def structured(self, state: PlannerState) -> PlannerDecision:
        open_fields = [s.name for s in RECIPE
                       if s.name not in state.get("collected", {}) and s.source != "derived"]
        tool = {
            "name": "planner_decision",
            "description": "Choose the next planner action.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["search", "ask_user", "calculate", "reflect", "finish"]},
                    "target": {"type": "string"},
                    "query": {"type": "string"},
                    "question": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["action"],
            },
        }
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            tools=[tool],
            tool_choice={"type": "tool", "name": "planner_decision"},
            messages=[{
                "role": "user",
                "content": (
                    "You are VentureScope's planner. Collected so far: "
                    f"{state.get('collected', {})}. Still-open fields: {open_fields}. "
                    "Pick the next action to make progress toward the SOM calculation."
                ),
            }],
        )
        block = next(b for b in msg.content if b.type == "tool_use")
        d = block.input
        return PlannerDecision(
            action=d["action"], target=d.get("target"), query=d.get("query"),
            question=d.get("question"), reason=d.get("reason", "llm"),
        )


def get_model() -> object:
    model_id: Optional[str] = os.environ.get("VENTURESCOPE_MODEL")
    if model_id and os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicModel(model_id)
    return FakeModel()
