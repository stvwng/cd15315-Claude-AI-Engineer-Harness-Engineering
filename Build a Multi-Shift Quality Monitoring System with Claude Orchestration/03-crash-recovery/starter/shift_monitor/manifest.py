"""Incremental crash-recovery manifest backed by JSON lines + fsync."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

InvocationShape = Literal["thin", "rich", "resumed"]


class Step(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_id: str
    name: str
    ts: datetime
    invocation_shape: InvocationShape
    payload: dict[str, Any]


class ManifestState(BaseModel):
    complete: bool
    steps: list[Step]


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append_step(self, step: Step) -> None:
        # TODO: Append a single JSON line for `step` and make it durable.
        #
        #   1. Make sure self.path.parent exists.
        #   2. Open the file in binary append mode: open(self.path, "ab").
        #      Text mode buffers the write through Python's text layer, so
        #      `flush()` + `os.fsync()` won't actually guarantee bytes hit disk.
        #      Use binary append ("ab") for fsync semantics.
        #   3. Encode `step.model_dump_json() + "\n"` as UTF-8 and write it.
        #   4. Flush and fsync the file descriptor *before* returning, so a
        #      crash one nanosecond after this call still leaves the line on disk.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "ab") as f:
            # The newline is what makes a line "complete" — a reader arriving
            # mid-append sees whole lines only, never a half-written record.
            f.write((step.model_dump_json() + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())

    @classmethod
    def load(cls, path: Path) -> ManifestState:
        # TODO: Read the manifest at `path`.
        #
        #   - If the file does not exist, return ManifestState(complete=False, steps=[]).
        #   - Otherwise, parse each non-empty line as a Step (Step.model_validate_json).
        #   - `complete` is True iff there is at least one step AND the last
        #     step's name == "complete". (An empty manifest is *not* complete.)
        if not path.exists():
            return ManifestState(complete=False, steps=[])
        steps: list[Step] = []
        with open(path, "rb") as f:
            for raw in f:
                line = raw.decode("utf-8").strip()
                if line:
                    steps.append(Step.model_validate_json(line))
        return ManifestState(complete=len(steps) > 0 and steps[-1].name == "complete", steps=steps)
