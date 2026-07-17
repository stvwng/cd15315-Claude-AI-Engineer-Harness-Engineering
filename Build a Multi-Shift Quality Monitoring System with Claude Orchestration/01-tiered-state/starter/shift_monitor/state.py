"""Hot-state schema and atomic disk I/O."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

MAX_RECENT_HASHES = 20
HOT_STATE_BYTE_BUDGET = 5_120


class HotState(BaseModel):
    """In-context shift state. Kept under ~5 KB so it fits in every prompt."""

    model_config = ConfigDict(frozen=True)

    # TODO: Declare the four required fields with the right types and constraints.
    # The state schema uses exactly these names:
    #   recent_defect_hashes: list[str], capped at MAX_RECENT_HASHES items.
    #     NOTE: In Pydantic v2 the list-length constraint is `max_length`.
    #     Older blog posts use `max_items` — that key was renamed and is silently
    #     ignored, so validation will appear to work but never enforce the cap.
    #   current_shift_summary: str
    #   active_alerts: list[str]
    #   threshold_statuses: dict[str, str]
    recent_defect_hashes: list[str] = Field(max_length=MAX_RECENT_HASHES)
    current_shift_summary: str
    active_alerts: list[str]
    threshold_statuses: dict[str, str]

    def to_json_bytes(self) -> bytes:
        # TODO: Serialize this model to UTF-8 JSON bytes. Pydantic v2 gives you
        # `self.model_dump_json()` for the JSON string; encode it as UTF-8.
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> Self:
        # TODO: Parse JSON bytes back into a HotState instance.
        # `cls` is the class this was called on (HotState, or a subclass),
        # supplied automatically by @classmethod. Building via `cls` rather than
        # hardcoding `HotState` is what makes the `-> Self` contract hold for
        # subclasses: SubState.from_json_bytes(...) returns a SubState.
        #
        # Evaluated inside-out: (1) payload.decode("utf-8") turns raw bytes into
        # a JSON string, then (2) model_validate_json parses it, validates every
        # field against the schema (types, the max_length=20 cap, all four
        # required), and returns a new HotState on success — validation is the
        # gate, and passing it is what constructs the object. Bad JSON or a
        # failed constraint raises ValidationError instead of returning.
        # NOTE: model_validate_json also accepts bytes directly, so the .decode()
        # is optional — Pydantic would decode it for us.
        return cls.model_validate_json(payload.decode("utf-8"))

    @classmethod
    def from_path(cls, path: Path) -> Self:
        # TODO: Read the bytes at `path` and parse them into a HotState.
        return cls.from_json_bytes(path.read_bytes())

    def write_atomic(self, path: Path) -> None:
        # TODO: Durably write `self.to_json_bytes()` to `path`.
        #
        # Requirements:
        #   1. Make sure the parent directory exists.
        #   2. Raise ValueError if the serialized payload is larger than
        #      HOT_STATE_BYTE_BUDGET — the budget is what forces SQL pre-filtering.
        #   3. Write to a tempfile in the *same* directory as `path`, flush + fsync,
        #      then swap it in with os.replace().
        #
        # Use os.replace, not os.rename. They behave the same on POSIX, but
        # os.rename fails on Windows when the destination already exists. The
        # whole point of an atomic write is that the destination *does* exist.
        
        # Ensure the destination directory exists so the write can't fail on a
        # missing parent (e.g. first run before any state dir has been created).
        path.parent.mkdir(parents=True, exist_ok=True)

        # Enforce the hot-state budget: if the serialized state won't fit in the
        # prompt, fail loudly here rather than silently persisting an oversized
        # blob. This is the pressure that forces older state into the SQL tier.
        payload = self.to_json_bytes()
        if len(payload) > HOT_STATE_BYTE_BUDGET:
            raise ValueError(f"hot state {len(payload)} bytes exceeds {HOT_STATE_BYTE_BUDGET}-byte budget")

        # Write to a temp file in the SAME directory as `path`. Same directory =
        # same filesystem, which is what makes the later os.replace atomic (a
        # cross-filesystem rename degrades to a non-atomic copy+delete).
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False,
                                          prefix=".hot_state.", suffix=".tmp") as tmp:
            tmp.write(payload)          # bytes -> Python's buffer
            tmp.flush()                 # Python's buffer -> kernel page cache (still volatile)
            os.fsync(tmp.fileno())      # kernel cache -> physical disk (survives power loss)
            tmp_path = Path(tmp.name)

        # Atomically swap the fully-written temp file over `path`. Any reader
        # sees either the complete old file or the complete new one, never a
        # half-written one. os.replace overwrites an existing dest on all OSes.
        os.replace(tmp_path, path)
