"""The agentic loop.

The defining contract:
- Control flow is driven by `response.stop_reason`.
- Loop continues iff stop_reason == "tool_use".
- Loop returns iff stop_reason == "end_turn".
- Any other stop_reason raises UnexpectedStopReason.

No string-membership tests against assistant text drive control flow here.
No integer-literal iteration cap is the primary stopping mechanism.
A Budget (token + wall-clock, sourced from config) is the safety net and raises
BudgetExceeded if hit — it never silently truncates.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from claims_intake.budget import Budget
from claims_intake.tracer import Tracer


class UnexpectedStopReason(Exception):
    pass


ToolExecutor = Callable[[str, dict[str, Any]], str]
"""Takes (tool_name, tool_input) and returns the tool_result content as a string.
Errors are returned as a serialized JSON string with is_error=true; never raised."""

TerminationCheck = Callable[[], "str | None"]
"""Asked once per `end_turn`, before the loop returns.

Returns None when the caller is satisfied the task actually finished, or a
corrective message to hand back to the model when it ended its turn without
doing so. The loop stays domain-agnostic: it never inspects assistant text or
tool names to decide what "finished" means — the caller owns that definition.
"""

DEFAULT_MAX_TERMINAL_NUDGES = 2
"""How many times a premature `end_turn` may be corrected before the loop gives
up and returns anyway. Not an iteration cap on the conversation — the Budget
remains the only bound on that — just a bound on this one repair path."""


class MessagesClient(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


@dataclass
class FinalState:
    messages: list[dict[str, Any]]
    total_input_tokens: int
    total_output_tokens: int
    turn_count: int
    final_content: list[Any] = field(default_factory=list)


def run(
    *,
    client: Any,
    model: str,
    system: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tool_executor: ToolExecutor,
    budget: Budget,
    tracer: Tracer,
    max_tokens: int = 4096,
    termination_check: "TerminationCheck | None" = None,
    max_terminal_nudges: int = DEFAULT_MAX_TERMINAL_NUDGES,
) -> FinalState:
    """Run the agentic loop until the model returns stop_reason == "end_turn".

    The loop condition is `response.stop_reason == "tool_use"` — nothing else.
    There is no `while turn < N` cap. The Budget object is the safety mechanism.

    When `termination_check` is supplied, an `end_turn` that the caller does not
    consider terminal is corrected rather than accepted: the loop appends the
    returned message and continues. This is still stop_reason-driven — `end_turn`
    is what triggers the check — it just stops treating the model's decision to
    stop as automatically correct.
    """
    working_messages = list(messages)
    turn = 0
    total_input = 0
    total_output = 0
    nudges_used = 0

    while True:
        turn += 1
        budget.check()
        t0 = time.monotonic()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=working_messages,
        )
        latency_ms = (time.monotonic() - t0) * 1000.0

        input_tokens = int(response.usage.input_tokens)
        output_tokens = int(response.usage.output_tokens)
        total_input += input_tokens
        total_output += output_tokens
        budget.record_input_tokens(input_tokens)

        tool_calls = [
            {"id": b.id, "name": b.name, "input": b.input}
            for b in response.content
            if getattr(b, "type", None) == "tool_use"
        ]
        tracer.write(
            {
                "turn": turn,
                "stop_reason": response.stop_reason,
                "tool_calls": tool_calls,
                "latency_ms": round(latency_ms, 1),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        )

        if response.stop_reason == "end_turn":
            working_messages.append({"role": "assistant", "content": response.content})

            correction = termination_check() if termination_check is not None else None
            if correction is not None and nudges_used < max_terminal_nudges:
                nudges_used += 1
                working_messages.append({"role": "user", "content": correction})
                tracer.write(
                    {
                        "turn": turn,
                        "event": "terminal_nudge",
                        "nudges_used": nudges_used,
                        "reason": "end_turn without a terminal action",
                    }
                )
                continue

            return FinalState(
                messages=working_messages,
                total_input_tokens=total_input,
                total_output_tokens=total_output,
                turn_count=turn,
                final_content=list(response.content),
            )

        if response.stop_reason == "tool_use":
            working_messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                result_content = tool_executor(block.name, dict(block.input))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_content,
                    }
                )
            working_messages.append({"role": "user", "content": tool_results})
            continue

        raise UnexpectedStopReason(
            f"turn {turn}: unexpected stop_reason={response.stop_reason!r}"
        )
