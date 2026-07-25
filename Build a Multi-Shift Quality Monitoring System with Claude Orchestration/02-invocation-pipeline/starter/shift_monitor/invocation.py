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
    prompt = f"""
    You are the on-call {role} for Northridge Plant 3.
    ## Current hot state
    {hot_state.recent_defect_hashes}
    {hot_state.current_shift_summary}
    {hot_state.active_alerts}
    {hot_state.threshold_statuses}
    ## New defects since last shift
    {new_defects}
    ## Latest instruction
    Provide a summary of the current hot state, any new defects since the last shift, and any recommended actions.
    Update the hot state with the new defects and any recommended actions.
    Return the updated hot state as a JSON block.
    The JSON block should be a valid Python dictionary with the following keys:
    - "recent_defect_hashes": a list of recent defect hashes
    - "current_shift_summary": a summary of the current shift
    - "active_alerts": a list of active alerts
    - "threshold_statuses": a list of threshold statuses
    - "recommended_actions": a list of recommended actions
    - "updated_hot_state": a dictionary with the same keys as the input hot state, but with the new defects and recommended actions applied.
    """
    return Invocation(shape="rich", prompt=prompt)

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
    prompt = f"""
    ## Prior partial findings
    {prior_steps}
    ## Prior summary
    {summary}
    ## New defects since last partial step
    {new_defects}
    ## Latest instruction
    {latest_message}
    """
    return Invocation(shape="resumed", prompt=prompt)
