# Primer 4 — Layer 3 Orchestration (Tiered State, Crash Recovery, Forking)

**System:** Multi-Shift Quality Monitoring
**Path:** `Build a Multi-Shift Quality Monitoring System with Claude Orchestration/04-fork-scratchpad/solution/`
**Run:** `python -m shift_monitor run-shift --shift C …` · **Tests:** 33

---

## 1. Concepts

### 1.1 The defining constraint

A manufacturing plant runs three 8-hour shifts a day. This system analyzes defects once
per shift — **as a fresh session every time, forever.** No conversation continuity. Each
run starts cold and must reconstruct exactly enough context to be useful.

That constraint generates every design decision:

- Fresh session → state must live **on disk**, not in a context window.
- Runs forever → state must be **bounded**, or it grows without limit.
- Runs unattended → crashes must be **survivable** without a human.
- Three times a day, indefinitely → every byte in hot state is a **recurring tax**.

> Systems 1 and 2 manage context *within* a conversation. This one manages it *across
> sessions that never meet*.

### 1.2 Tiered state

Three tiers by access frequency and size:

```
┌──────────────────────────────────────────────────────────────┐
│ HOT — hot_state.json                        965 bytes        │
│ Loaded into EVERY prompt. Hard cap 5,120 bytes.              │
│ Last 20 defect ids, current summary, alerts, thresholds.     │
├──────────────────────────────────────────────────────────────┤
│ WARM — warm.sqlite                          40 defects       │
│ Queried per shift, indexed. The model sees a SLICE.          │
│ Authoritative append-only record.                            │
├──────────────────────────────────────────────────────────────┤
│ COLD — cold/YYYY-MM.md                      monthly rollups  │
│ Derived deterministically from warm. Human-readable.         │
│ Never enters a prompt unless explicitly asked for.           │
└──────────────────────────────────────────────────────────────┘
```

The sorting question is **"how often does this need to be in front of the model?"** —
not how important it is. The full defect history is more *valuable* than the current
summary, and it lives in the coldest queryable tier, because it's needed occasionally
and in slices.

### 1.3 Push work down

The model never sees full history. A SQL query with an index does the filtering first:

```
warm tier total          : 40 defects
SQL slice since 2026-04-01: 17 defects sent to the model
withheld from the model  : 23 defects
query plan:
    SEARCH defects USING INDEX idx_defects_ts (ts>?)
```

Two arguments, and the second is the stronger one:

1. **Cost** — token spend would grow without bound as the plant accumulates defects.
2. **Correctness** — a model handed 40 rows and told "consider only recent ones" will
   mostly comply. `WHERE ts > ?` always does.

`SEARCH … USING INDEX` rather than `SCAN` is the *artifact that proves* the work moved
down a layer. Learn to read `EXPLAIN QUERY PLAN` as evidence, not decoration.

### 1.4 Crash recovery: resume vs. fresh

A shift can die mid-analysis (SIGKILL, OOM, host reboot). Without a durable record you
lose every finding. With one, the next invocation can decide.

The non-obvious part is that **resuming is not always better.** A resumed session
re-asserts old premises as current: the model picks up mid-reasoning about a line whose
readings have since moved, with no way to notice. A fresh start with a one-paragraph
summary injected is often *more accurate*, because every fact it reasons over was read
after the gap.

Hence a staleness threshold — 30 minutes, about one-sixteenth of an 8-hour shift, so
resumes stay within the same shift's working set.

### 1.5 Forking

Investigators chase competing hypotheses about a defect cluster in parallel. Forking
gives each one:

- a **shared baseline** (a copy of hot state at fork time),
- an **isolated scratchpad** (findings don't cross-contaminate),
- an explicit **merge** back into the main stream.

This mirrors the Layer 2 fork primitive (`context: fork` in Primer 3) at the
orchestration layer, using state-file copies instead of sub-agents. Same semantics,
different mechanism.

---

## 2. Architecture

```
shift_monitor/
├── state.py       ← HotState (Pydantic, frozen) + write_atomic. THE budget.
├── warm.py        ← WarmStore: SQLite, indexed defects_since, month rollups
├── cold.py        ← ColdStore: monthly Markdown summaries from warm
├── invocation.py  ← thin / rich / resumed prompt shapes
├── pipeline.py    ← run_shift(): the once-per-shift orchestration
├── manifest.py    ← Step / ManifestState / Manifest (JSONL + fsync)
├── recovery.py    ← STALE_RESUME_THRESHOLD_MINUTES + decide()
├── fork.py        ← fork_for_hypothesis / merge_findings
├── scratchpad.py  ← typed append-only findings (JSONL + fsync)
├── client.py      ← ClaudeClient Protocol; Recorded + Anthropic impls
└── __main__.py    ← argparse CLI
```

Exercise arc: **1** tiered state (9 tests) → **2** invocation pipeline (+6 = 15) →
**3** crash recovery (+14 = 29) → **4** fork/scratchpad (+4 = 33).

> ### ⚠️ What is actually wired, and what is not
>
> Worth knowing before you go looking for call sites. `run_shift` imports only
> `client`, `invocation.rich`, `scratchpad`, `state`, and `warm`. The CLI adds nothing
> beyond `pipeline`, `client`, `state`, `warm`.
>
> | Module | Status |
> |---|---|
> | `state.py`, `warm.py`, `scratchpad.py`, `client.py` | wired into `run_shift` |
> | `invocation.rich` | wired |
> | `invocation.thin`, `invocation.resumed` | built + tested, **no runtime caller** |
> | `manifest.py` | built + tested, **no runtime caller** |
> | `recovery.py` | built + tested, **no runtime caller** |
> | `fork.py` | built + tested, **no runtime caller** |
> | `cold.py` | built + tested, invoked separately, not per-shift |
>
> `grep` confirms it: outside their own modules, `manifest`, `recovery`, and `fork` are
> imported **only by `tests/`**.
>
> This is not a defect — each is an exercise deliverable with its own passing tests, and
> the capstone evidence run drives them directly rather than through `run_shift`. But it
> does mean the crash-recovery and fork machinery described in §6–§8 is **available
> rather than active**: a real deployment would still need to call `Manifest.append_step`
> around each pipeline stage and consult `decide()` at startup. Read §6–§8 as "here is
> the mechanism and why it's shaped this way," not "here is what happens every shift."

One shift:

```
hot_state.json ──► HotState.from_path()
                          │
warm.sqlite ──► gather_new_defects(since_ts)   [SQL, indexed]  17 of 40
                          │
                  build_rich_prompt(role, hot_state, new_defects)
                          │
                  client.complete([Message(...)])   ← EXACTLY ONE CALL
                          │
              _parse_hot_state_update(response)  [```json fence]
                          │
              HotState(hashes=_new_hashes(...), summary, alerts, thresholds)
                          │
                  _trim_to_budget()  ──► write_atomic()  ──► hot_state.json
                          │
                  Scratchpad.append(ScratchpadEntry(...))
                          ▼
                     ShiftResult
```

---

## 3. `state.py` — the hot tier and its budget

```python
MAX_RECENT_HASHES = 20
HOT_STATE_BYTE_BUDGET = 5_120


class HotState(BaseModel):
    """In-context shift state. Kept under ~5 KB so it fits in every prompt."""

    model_config = ConfigDict(frozen=True)

    recent_defect_hashes: list[str] = Field(max_length=MAX_RECENT_HASHES)
    current_shift_summary: str
    active_alerts: list[str]
    threshold_statuses: dict[str, str]
```

Two structural defenses, both declarative:

- **`Field(max_length=20)`** — construction fails if you exceed it. Not a runtime check
  you might forget; a property of the type.
- **`frozen=True`** — updates go through `model_copy(update={...})`, so mutation is
  always explicit and traceable.

### 3.1 Atomic write

```python
    def write_atomic(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_json_bytes()
        if len(payload) > HOT_STATE_BYTE_BUDGET:
            raise ValueError(
                f"hot state {len(payload)} bytes exceeds {HOT_STATE_BYTE_BUDGET}-byte budget"
            )
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, delete=False,
            prefix=".hot_state.", suffix=".tmp"
        ) as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)
```

Every line earns its place:

| Line | Why |
|---|---|
| `raise` on over-budget | **Fails loudly rather than truncating.** A system that silently dropped alerts to fit would degrade invisibly across thousands of shifts. |
| `dir=path.parent` | Temp file on the **same filesystem** — `os.replace` is only atomic within a filesystem. |
| `tmp.flush()` + `os.fsync()` | Bytes reach the disk, not just the OS page cache. |
| `os.replace(tmp, path)` | Atomic rename. A reader sees either the old file or the new one — never a half-written one. |

**Why it matters:** a crash between truncate and write in a naive `open(path, "w")`
leaves corrupt state, and then the *next* shift fails to start. One transient crash
becomes a permanent outage. No successful run can ever exhibit the difference — which
is precisely why `test_hotstate_atomic_write` exists.

### 3.2 What it looks like in practice

965 bytes of a 5,120-byte budget — **18.8% used**:

```json
{
  "recent_defect_hashes": ["DEF-20260429-001", "…17 ids…"],
  "current_shift_summary": "Shift C 2026-04-30: 3 high + 2 medium defects on
                            capacitor-bank-C-7, all from lot 2026-0430-B …",
  "active_alerts": ["capacitor-bank-C-7 elevated night-shift defect rate …", "…"],
  "threshold_statuses": {
    "defect_rate_per_shift": "ALARM",
    "critical_count_24h": "OK",
    "lot_defect_concentration": "ALARM"
  }
}
```

---

## 4. `warm.py` — SQLite and the indexed query

### 4.1 Schema

```sql
CREATE TABLE IF NOT EXISTS defects (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    shift TEXT NOT NULL,
    component TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_defects_shift_ts ON defects (shift, ts);
CREATE INDEX IF NOT EXISTS idx_defects_ts ON defects (ts);
```

**Why both indexes.** `defects_since` filters on `ts` alone. SQLite can only use a
composite index when its **leading column** is constrained — so `idx_defects_shift_ts`
is useless for `WHERE ts > ?` and the query degrades to a full scan. The single-column
`idx_defects_ts` is what makes the plan say `SEARCH`.

This is a genuinely easy one to get wrong: you add a composite index, assume it covers
the prefix and the suffix, and never check the plan.

### 4.2 The query and its proof

```python
def defects_since(self, since_ts: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return defects with ts > since_ts, newest first, up to limit rows.

    SQL-side filtering only — no Python-side filtering of severity,
    component, or time.
    """
    with self._connect() as conn:
        cur = conn.execute(
            "SELECT * FROM defects WHERE ts > ? ORDER BY ts DESC LIMIT ?",
            (since_ts, limit),
        )
        return [dict(row) for row in cur.fetchall()]

def explain_defects_since(self, since_ts, limit=50) -> list[tuple[Any, ...]]:
    # returns EXPLAIN QUERY PLAN rows: (id, parent, notused, detail)
```

`explain_defects_since` exists **so the test can assert the index is used.** That's the
pattern worth stealing: if a performance property is part of your contract, make it
observable and test it, rather than trusting that it holds.

### 4.3 Bulk insert

```python
    def insert_many(self, rows: Iterable[Mapping[str, Any]]) -> None:
        payload = [
            (r["id"], r["ts"], r["shift"], r["component"], r["severity"], r["description"])
            for r in rows
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO defects "
                "(id, ts, shift, component, severity, description) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                payload,
            )
```

Two things: **`INSERT OR REPLACE`** makes re-seeding idempotent — the same fixture can
be loaded twice without error. And rows are **projected to explicit tuples** rather than
passed straight through, so extra keys in a source row can't break the bind. (Named
`:id`-style placeholders are the alternative; they bind from mappings directly but
reject any mapping carrying keys the statement doesn't name.)

### 4.4 The month-scoping foot-gun

```python
    def count_for_month(self, year: int, month: int) -> int:
        prefix = f"{year:04d}-{month:02d}"
        ...
            "SELECT COUNT(*) FROM defects WHERE ts LIKE ?", (f"{prefix}-%",)
```

Timestamps are `2026-04-…`. The `:02d` is load-bearing: an unpadded
`f"{year}-{month}-%"` yields `2026-4-%`, which matches **nothing** for every month
before October — and returns `0` rather than raising. A silent wrong answer, not a
crash. `top_components_for_month` uses the same prefix and adds `ORDER BY c DESC,
component ASC`, so ties break deterministically instead of by SQLite's row order.

---

## 5. `pipeline.py` — one shift, one call

```python
def run_shift(shift_id, client, warm, hot_state_path, scratchpad_path,
              since_ts, role="quality engineer") -> ShiftResult:
    log.info("run_shift start: shift=%s since=%s", shift_id, since_ts)
    hot_state = HotState.from_path(hot_state_path)
    new_defects = gather_new_defects(warm, since_ts, limit=50)
    prompt = build_rich_prompt(role=role, hot_state=hot_state, new_defects=new_defects)
    response = client.complete([Message(role="user", content=prompt)])   # ← EXACTLY ONE
```

**One shift = exactly one Claude call.** Everything above the call narrows context;
everything below consumes the single response. Contrast with System 1, where the
*model* decides how many turns it needs. Here the orchestration decides, because a
per-shift batch job has no interactive user and no reason to iterate.

### 5.1 Pure pass-through to SQL

```python
def gather_new_defects(warm, since_ts, limit=50) -> list[dict[str, Any]]:
    # Pure pass-through to SQL: no Python-side narrowing of severity, component,
    # or time. A test scans this function's source and rejects branching or
    # comprehension tokens, so keep the body a single delegating return.
    return warm.defects_since(since_ts, limit=limit)
```

An AST-style audit reads this function's **source text** and rejects `if `, `for `,
`filter(`, `[r for`, `[d for`. Same idea as System 1's anti-pattern tests: make the
architectural boundary mechanically checkable.

> Amusing consequence encountered in practice: a TODO comment that *described* the
> rule ("rejects any `if` / `filter` …") contained the substring `if ` and failed the
> test. Source-text audits don't distinguish comments from code.

### 5.2 Merging the response into state

```python
    parsed = _parse_hot_state_update(response.content)     # ```json fence
    parsed_summary = parsed.get("current_shift_summary") if parsed else None
    summary = (
        parsed_summary if isinstance(parsed_summary, str)
        else _short_summary_from_response(response.content, shift_id)
    )
    ...
    updated = HotState(
        recent_defect_hashes=_new_hashes(new_defects, hot_state.recent_defect_hashes),
        current_shift_summary=summary,
        active_alerts=active_alerts,
        threshold_statuses=threshold_statuses,
    )
    updated = _trim_to_budget(updated)
    updated.write_atomic(hot_state_path)
```

Every parsed field is **type-checked and falls back to the prior value**:

```python
active_alerts = (
    [str(a) for a in parsed_alerts] if isinstance(parsed_alerts, list)
    else list(hot_state.active_alerts)
)
```

A malformed or missing fence never drops state on the floor — the shift keeps the
previous alerts rather than clearing them. The model's output is treated as
*untrusted input*, which is the correct posture for anything an LLM emits into
persistent state.

### 5.3 The budget trimmer

```python
def _trim_to_budget(state: HotState) -> HotState:
    if len(state.to_json_bytes()) <= HOT_STATE_BYTE_BUDGET:
        return state
    alerts = list(state.active_alerts)
    while alerts and len(state.to_json_bytes()) > HOT_STATE_BYTE_BUDGET:
        alerts.pop()
        state = state.model_copy(update={"active_alerts": alerts})
    return state
```

Note the layered defense: `_trim_to_budget` drops the *lowest-priority* field (oldest
alerts) to fit, and if that isn't enough, `write_atomic` still **raises**. Graceful
degradation first, loud failure as backstop — never silent truncation.

---

## 6. `manifest.py` + `recovery.py` — crash recovery

### 6.1 The append

```python
    def append_step(self, step: Step) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = step.model_dump_json() + "\n"      # ← the newline is the commit marker
        with open(self.path, "ab") as f:          # ← binary append, not text
            f.write(line.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
```

Three deliberate choices:

1. **`"ab"` not `"a"`.** Text mode buffers through Python's text layer, so `flush()` +
   `os.fsync()` don't actually guarantee bytes hit disk. Binary append gives real fsync
   semantics.
2. **The trailing newline is the commit marker.** Without it every record concatenates
   onto one line and the file becomes one unparseable blob. It's also what makes a
   concurrent reader safe: it sees complete lines or nothing.
3. **fsync before returning**, so a crash one nanosecond later still leaves the line on
   disk.

### 6.2 The load

```python
    @classmethod
    def load(cls, path: Path) -> ManifestState:
        if not path.exists():
            return ManifestState(complete=False, steps=[])
        steps: list[Step] = []
        with open(path, "rb") as f:
            for raw in f:
                line = raw.decode("utf-8").strip()
                if line:
                    steps.append(Step.model_validate_json(line))
        complete = bool(steps) and steps[-1].name == "complete"
        return ManifestState(complete=complete, steps=steps)
```

**An empty manifest is not complete** — `bool(steps) and …`. Easy to miss, and without
it a zero-step manifest reports complete and the shift silently never runs. Note also
the `if line:` guard: a blank or torn trailing line is skipped rather than crashing the
load, which matters because crash-truncated files are exactly what this class exists to
read.

### 6.3 The decision

```python
# The 30-minute rule sounds arbitrary, but it's anchored to a real operational
# tempo: a shift is 8 hours, and the working set rolls over with each shift.
# Resuming an hour-old partial means asking the model to pick up where it was
# when the world has moved on. Starting fresh with the prior findings injected
# as a one-paragraph summary is cheaper and produces a better answer.
STALE_RESUME_THRESHOLD_MINUTES = 30


def decide(state: ManifestState, now: datetime) -> Decision:
    if len(state.steps) == 0:
        return "fresh"
    if state.complete:
        return "fresh"
    if now - state.steps[-1].ts <= timedelta(minutes=STALE_RESUME_THRESHOLD_MINUTES):
        return "resume"
    return "fresh"
```

Three cases, and the empty case is separate from the complete case on purpose — they're
easy to conflate and they mean different things (nothing started vs. everything
finished).

**The boundary is inclusive** (`<=`). Verified:

```
last step  5m old -> resume
last step 30m old -> resume     ← inclusive
last step 31m old -> fresh
after complete step -> fresh
```

---

## 7. `fork.py` — isolation and merge

```python
def fork_for_hypothesis(base_hot_state_path: Path, hypothesis_id: str,
                        forks_root: Path) -> Path:
    fork_dir = forks_root / hypothesis_id
    fork_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base_hot_state_path, fork_dir / "hot_state.json")
    return fork_dir


def merge_findings(scratchpad_paths: Iterable[Path], main_scratchpad: Path) -> None:
    main = Scratchpad(main_scratchpad)
    for path in scratchpad_paths:
        if not path.exists():          # a fork may have produced nothing
            continue
        for entry in Scratchpad(path).read():
            main.append(entry)
```

The module docstring names the framing precisely:

> `fork_session` here is the application-side framing: the SDK / CLI primitive lives at
> Layer 2; here we reproduce the *semantics* (shared baseline, isolated scratchpads, no
> cross-contamination) using state-file copies.

**`merge_findings` routes every write through `Scratchpad.append`** rather than raw
`open(..., "a")`. Two reasons: fsync semantics stay uniform system-wide, and reading
through the typed reader rejects a corrupt fork scratchpad at the source instead of
merging bad lines into main.

Verified isolation:

```
base hot_state unchanged by forking: True  (sha256 110086f286fa379d…)
H1 sees H2 findings? False
H2 sees H1 findings? False
main scratchpad: 1 entries before merge -> 3 after
merged ids: ['shift-C', 'H1-lot-2026-0430-B', 'H2-vp4-vent-cycle']
```

The base hash being **byte-identical before and after** is the isolation proof. And
merge is pure append — `test_merge_findings_appends_without_rewriting_existing` checks
the pre-existing bytes are untouched, which a passing run alone would never reveal.

---

## 8. `invocation.py` — three prompt shapes

| Shape | Carries | Intended for | Wired? |
|---|---|---|---|
| `thin` | prompt only | one-shot, no project state | no |
| `rich` | hot state + new defects | the normal shift run | **yes** — `pipeline.py` |
| `resumed` | prior steps + summary + new defects since last step | recovering a partial run | no |

`rich` renders defects one per line:

```
- DEF-20260429-001 / 2026-04-29T12:05:28Z / C / capacitor-bank-C-7 / high / …
```

and closes with an instruction to return an updated hot state as a JSON block — which
is what `_parse_hot_state_update` reads back. **The prompt's requested keys must match
what the parser consumes** (`current_shift_summary`, `active_alerts`,
`threshold_statuses`); asking for keys nothing reads is a silent no-op.

`resumed` exists because of §1.4: a resumed session is still a *new* session, so the
partial findings have to be carried forward in the prompt itself — there's no
conversation to pick back up. That's the shape `decide() == "resume"` is meant to
select. Note the wiring gap flagged in §2: nothing currently calls `decide()` or
`resumed()` at runtime, so this pairing is designed but not yet connected.

---

## 9. `client.py` and `scratchpad.py`

**`ClaudeClient` is a `Protocol`** with `complete(messages) -> Message`, implemented by
`AnthropicClaudeClient` (live) and `RecordedClaudeClient` (replays a fixture, counts
calls). That's what makes `test_run_shift_invokes_client_exactly_once…` possible, and
what lets the whole System 4 evidence run happen offline at zero API cost.

**`Scratchpad`** is typed append-only JSONL with the same fsync discipline as
`Manifest`:

```python
class ScratchpadEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    hypothesis_id: str
    evidence: str
    conclusion: str
    ts: datetime
```

Typed entries are why `merge_findings` can validate rather than blindly copy.

---

## 10. Gotchas

| Gotcha | Symptom | Fix |
|---|---|---|
| Composite index doesn't serve a suffix column | Plan says `SCAN` | Add a single-column index on the filtered column |
| Unpadded month pattern | `2026-4-%` matches nothing, returns 0 | `f"{year:04d}-{month:02d}-%"` |
| Text-mode append | fsync doesn't guarantee durability | `open(path, "ab")` |
| Missing trailing newline | All records concatenate; file unparseable | `model_dump_json() + "\n"` |
| Empty manifest treated as complete | Shift silently never runs | `len(steps) > 0 and …` |
| Exclusive staleness boundary | 30m-old partial discarded | Use `<=`, not `<` |
| Default `--since` is 8h ago | Real-world default vs. historical fixtures → 0 rows | Pass `--since` explicitly when demoing |
| Raw `open(..., "a")` in merge | Bypasses fsync; can merge corrupt lines | Route through `Scratchpad.append` |

That `--since` one is worth expanding: the CLI defaults to 8 hours ago, which is right
for production and wrong for fixtures dated months back. A run against the defaults
reports `0 new defects` and **exits 0** — a green run that demonstrates nothing.
Always check that your slice is non-empty before treating a run as evidence.

---

## 11. Blast radius

Worth reasoning through, because it's the practical payoff of the design.

If this system misbehaves it writes a wrong `current_shift_summary` and wrong
`threshold_statuses` into hot state — and because every later shift starts from that
file, **one bad shift poisons every subsequent shift**, not just its own.

Containment:

- **The model has no tools.** `pipeline.py` makes one `complete()` call; the *code* does
  every write. It can corrupt hot state but cannot touch the warm tier, cold summaries,
  or anything outside `data/`.
- **Hot state is 965 bytes of plain text** — a human can read and hand-correct it in a
  minute.
- **The warm tier is append-only and authoritative** — hot state can be rebuilt from
  SQLite.
- **Forks are contained by construction** — verified by the unchanged base hash.
- **`decide()` would bound propagation** — anything older than 30 minutes forces a
  fresh start rather than resuming from poisoned context. Stated in the conditional
  because, per §2, nothing calls it at runtime yet; today this is a designed control,
  not an active one.

---

## 12. Self-check

1. Why does the warm tier need `idx_defects_ts` when `idx_defects_shift_ts` already
   indexes `ts`?
2. Walk through `write_atomic`. Name what each of `dir=path.parent`, `os.fsync`, and
   `os.replace` prevents.
3. A manifest has two steps, last one 45 minutes old, not complete. What does `decide()`
   return, and why is that *more* accurate than resuming?
4. `_trim_to_budget` drops alerts, and `write_atomic` raises. Why both?
5. How is fork isolation *proved* rather than asserted? Which artifact?
6. Compare System 2's and System 4's context management: same principle, different
   mechanism — state both, with numbers.
7. `gather_new_defects` is one line but has a dedicated source-scanning test. What
   property does that test protect, and why can't a behavioral test protect it?
