"""Three invocation shapes.

thin     — prompt only.
rich     — hot state + new defects.
resumed  — prior partial findings + new defects since the last manifest step.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .state import HotState

InvocationShape = Literal["thin", "rich", "resumed"]


@dataclass(frozen=True)
class Invocation:
    shape: InvocationShape
    prompt: str


# Descriptions are free text from the shop floor and occasionally run long. Cap
# them so prompt size scales with the defect count alone, not with how verbose
# any one operator was.
MAX_DESCRIPTION_CHARS = 120
MAX_PAYLOAD_CHARS = 80


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _defect_bullets(
    defects: Sequence[Mapping[str, Any]], *, include_shift: bool
) -> list[str]:
    """One bullet per defect, or a single `- (none)` when there are none."""
    if not defects:
        return ["- (none)"]
    bullets: list[str] = []
    for d in defects:
        fields = [str(d.get("id", "")), str(d.get("ts", ""))]
        if include_shift:
            fields.append(f"shift {d.get('shift', '')}")
        fields.append(str(d.get("component", "")))
        fields.append(str(d.get("severity", "")))
        fields.append(_truncate(str(d.get("description", "")), MAX_DESCRIPTION_CHARS))
        bullets.append("- " + " | ".join(fields))
    return bullets


def thin(prompt: str) -> Invocation:
    # TODO: Return an Invocation with shape="thin" and the prompt unchanged.
    # The thin shape is for one-shot calls that don't need any project state.
    return Invocation(shape="thin", prompt=prompt)


def rich(
    role: str, hot_state: HotState, new_defects: Sequence[Mapping[str, Any]]
) -> Invocation:
    # TODO: Build a rich prompt that includes:
    #   - A one-line role framing ("You are the on-call {role} for Northridge Plant 3.")
    #   - A "## Current hot state" section listing recent_defect_hashes,
    #     current_shift_summary, active_alerts, threshold_statuses.
    #   - A "## New defects since last shift" section enumerating each new defect
    #     (id / ts / shift / component / severity / description).
    #   - A trailing instruction asking for: Summary, Findings, Recommended
    #     actions, and an Updated hot state proposal as a JSON block.
    # Return an Invocation with shape="rich" and the rendered prompt.
    alerts = [f"- {a}" for a in hot_state.active_alerts] or ["- (none)"]
    thresholds = [f"- {k}: {v}" for k, v in hot_state.threshold_statuses.items()] or ["- (none)"]
    lines = [
        f"You are the on-call {role} for Northridge Plant 3.",
        "",
        "## Current hot state",
        f"Recent defect hashes: {', '.join(hot_state.recent_defect_hashes) or '(none)'}",
        f"Current shift summary: {hot_state.current_shift_summary}",
        "Active alerts:",
        *alerts,
        "Threshold statuses:",
        *thresholds,
        "",
        "## New defects since last shift",
        *_defect_bullets(new_defects, include_shift=True),
        "",
        "## Latest instruction",
        "Respond with these sections:",
        "- Summary: what happened this shift, in two sentences or fewer.",
        "- Findings: what the new defects indicate, with the defect ids as evidence.",
        "- Recommended actions: concrete next steps, most urgent first.",
        "- Updated hot state: a ```json fenced block with the keys",
        '  "current_shift_summary", "active_alerts", "threshold_statuses".',
    ]
    return Invocation(shape="rich", prompt="\n".join(lines))


def resumed(
    session_id: str,
    summary: str,
    latest_message: str,
    prior_steps: Sequence[Mapping[str, Any]],
    new_defects: Sequence[Mapping[str, Any]],
) -> Invocation:
    # TODO: Build a resumed prompt with three required sections:
    #   - "## Prior partial findings" — one line per prior step, showing its
    #     `name` and a truncated representation of its `payload`.
    #   - "## Prior summary" — the supplied summary string.
    #   - "## New defects since last partial step" — enumerate new_defects
    #     (id / ts / component / severity / description), or "- (none)" if empty.
    # Close with the latest_message under "## Latest instruction".
    # Return an Invocation with shape="resumed".
    steps = [
        f"- {s.get('name', '')}: {_truncate(str(s.get('payload', '')), MAX_PAYLOAD_CHARS)}"
        for s in prior_steps
    ] or ["- (none)"]
    lines = [
        f"Resuming session {session_id}.",
        "",
        "## Prior partial findings",
        *steps,
        "",
        "## Prior summary",
        summary,
        "",
        "## New defects since last partial step",
        *_defect_bullets(new_defects, include_shift=False),
        "",
        "## Latest instruction",
        latest_message,
    ]
    return Invocation(shape="resumed", prompt="\n".join(lines))
