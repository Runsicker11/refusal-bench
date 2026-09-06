"""The model boundary.

Everything the graph knows about a language model lives behind this protocol.
The graph never imports a vendor SDK, which buys two things:

  1. The provider is a swap, not a rewrite. LangGraph is model-agnostic and so
     is this.
  2. The graph is testable with no API key and no network. `ScriptedModel`
     replays a fixed list of responses, so the loop mechanics -- does it
     terminate, does the counter increment, does the budget halt it -- are
     verified deterministically and for free.

That second property is not a convenience. Loop mechanics tested against a live
model are tested against a moving target, and a test that costs money per run
is a test that stops being run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ModelResponse:
    """One turn from the model: prose, a tool call, or both."""

    text: str = ""
    tool_call: ToolCall | None = None
    usage: Usage = field(default_factory=Usage)
    # Which model actually served this. Comes from the API response rather than
    # the request, because a provider can route you somewhere else.
    model: str = "scripted"

    @property
    def finish_reason(self) -> str:
        return "tool_calls" if self.tool_call is not None else "stop"


class Model(Protocol):
    def complete(self, prompt: str) -> ModelResponse: ...


class ScriptedModel:
    """Replays a fixed sequence of responses. No key, no network, no cost."""

    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def complete(self, prompt: str) -> ModelResponse:
        self.calls.append(prompt)
        if not self._responses:
            raise AssertionError(
                "ScriptedModel ran out of responses -- the graph made more "
                "model calls than the test scripted. Either the loop is not "
                "terminating or the script is short."
            )
        return self._responses.pop(0)
