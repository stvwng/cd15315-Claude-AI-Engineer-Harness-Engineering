# Primer 2 — Context Strategy (Position-Aware Compression)

**System:** Retail Support Copilot
**Path:** `Engineer a Long-Conversation Context Strategy for a Retail Support Copilot/04-assemble-and-locate/solution/`
**Run:** `python -m retail_context.run --all` · **Tests:** 30

---

## 1. Concepts

### 1.1 The problem

A support conversation runs 48 turns across three issues for one customer:

| Issue | Status |
|---|---|
| Refund inquiry (order `ORD-77310`) | resolved |
| Subscription cancellation (`SUB-22119`) | resolved |
| Payment-method update | **active** |

Passing the whole history costs 38,708 tokens every turn, forever. Truncating loses
the refund amount the customer will ask about. The engineering question:

> **What can be lossy, what must be byte-exact, and where do you put each?**

### 1.2 Three reduction techniques, in increasing cost and risk

| Technique | Mechanism | Cost | Fidelity |
|---|---|---|---|
| **Pruning** | Deterministic field selection in code | free | perfect on kept fields |
| **Extraction** | One LLM call → strict JSON schema | 1 call | high, schema-validated |
| **Summarization** | One LLM call per segment → prose | N calls | lossy by design |

The discipline is to reach for them in that order. Prune what you can decide
statically; extract what has a known schema; summarize only what's genuinely narrative
— and only when it's *resolved*.

### 1.3 Lost in the middle

Long-context attention is not uniform. Models attend most reliably to the **beginning**
and **end** of a context window; recall degrades in the middle. This is an empirical
property, and it turns context assembly into a *layout* problem, not just a *size*
problem.

The layout that follows:

```
┌─────────────────────────────────────────────┐
│ # Case Facts                                │ ← TOP BOUNDARY: high attention
│   structured, byte-exact, ~204 tokens       │   12 fields the model must not
│                                             │   paraphrase
├─────────────────────────────────────────────┤
│ # Resolved: Refund inquiry          363 tok │ ← MIDDLE: compressible zone.
│ # Resolved: Subscription cancel     567 tok │   Lossy is fine — the facts that
│   LLM summaries, narrative                  │   matter were lifted to the top.
├─────────────────────────────────────────────┤
│ # Active issue: Payment-method update       │ ← BOTTOM BOUNDARY: high attention,
│   VERBATIM, byte-exact, 15,789 tokens       │   adjacent to the new user turn
└─────────────────────────────────────────────┘
```

Key insight: **the middle is where compression loss is cheapest**, because it's also
where recall is weakest. Putting summaries there is not a compromise; it's a match.

And the facts most at risk of being paraphrased away are duplicated to the top
boundary — where attention is strongest — in structured form.

### 1.4 The scratchpad / case-facts pattern

A dense structured block that **survives compression** and sits at the top of context,
so the model can recover transactional facts without scanning thousands of tokens of
narrative. Same concept as the "scratchpad" in agent literature.

Its defining property: it's the one section that is *both* small *and* byte-exact. A
summary can say "the refund went through"; it cannot be trusted to preserve
`AVS_MISMATCH` or `$22.14` verbatim.

### 1.5 Control variants as evidence

Claiming the facts block is load-bearing is cheap. Proving it means running the evals
**again with the block removed** and showing something breaks.

- Full context: **6/6** pass.
- Control (facts block stripped): **Q6 fails**, Q1 still passes.

Q6 asks for "the exact status token from the case record, not a paraphrase." Q1 asks
for the refund amount, which is *also* recoverable from surviving narrative. That
asymmetry is the finding: the block is load-bearing precisely for questions whose
answers are **tokens** rather than **narrative**.

> A control that fails *everything* proves nothing (you deleted the context). A control
> that fails *the predicted subset* proves the mechanism.

---

## 2. Architecture

```
retail_context/
├── transcript.py   ← load + segment by issue_id; Turn/Segment/Transcript
├── tokens.py       ← THE canonical counter. Everything measures through here.
├── pruner.py       ← deterministic 57→5 field projection. NO anthropic import.
├── case_facts.py   ← LLM extraction → 12-field schema → Markdown block
├── compressor.py   ← per-resolved-segment summarization; active preserved
├── assemble.py     ← position-aware layout; exact header contract
├── evaluate.py     ← 6 eval questions + the control variant
├── client.py       ← get_client / get_model / complete_with_system
├── prompts/
│   └── compression_prompt.md   ← committed, reviewed template
└── run.py          ← orchestration; writes budget.json and artifacts
```

Pipeline:

```
transcript_48turns.json
      │ transcript.load()
      ▼
Transcript ──────────────────────────► baseline_tokens = 38,708
      │                                        (tokens.count on full_text)
      ├─► case_facts.extract()  [1 LLM call] ──► CaseFacts (12 fields)
      │                                          + case_facts_call.json
      └─► compressor.compress() [2 LLM calls] ─► Compressed
                                                   ├ summaries{refund, subscription}
                                                   └ active_text (byte-exact)
                          │
                  assemble.build()
                          ▼
              AssembledContext ──► context.md      (16,905 tokens, −56.33%)
                          │       └► budget.json
                          ▼
              evaluate.run_questions()  [6 calls] ─► eval.jsonl        6/6
              evaluate control          [2 calls] ─► eval_control.jsonl Q6 fails
```

---

## 3. `transcript.py` — segmentation

```python
@dataclass(frozen=True)
class Turn:
    turn: int
    role: Role            # "customer" | "agent"
    text: str
    issue_id: IssueId     # "refund" | "subscription" | "payment_update"

    def render(self) -> str:
        return f"Turn {self.turn} ({self.role}): {self.text}"
```

`render()` is the **single definition of a turn's serialized form**. It's used for the
baseline count, for segment text, and for the byte-exact active section — so "byte-exact"
is a claim you can actually check, because there's only one renderer.

```python
def load(path):
    ...
    by_issue: dict[IssueId, list[Turn]] = {}
    order: list[IssueId] = []
    for t in turns:
        if t.issue_id not in by_issue:
            by_issue[t.issue_id] = []
            order.append(t.issue_id)          # ← first-appearance order
        by_issue[t.issue_id].append(t)

    status_map = {
        sid: ("active" if sid == data["active_issue_id"] else "resolved")
        for sid in order
    }
```

Two decisions encoded here:

1. **Segments preserve first-appearance order**, so refund precedes subscription in the
   assembled output deterministically.
2. **Status is data, not inference.** The fixture names `active_issue_id`; the code
   doesn't guess which thread is live. In production this would come from your CRM.

Turns for one issue may be interleaved in the raw transcript; grouping by `issue_id`
de-interleaves them. That's what makes "compress the resolved threads" expressible at
all.

---

## 4. `tokens.py` — one counter, recorded methodology

### 4.1 The module

```python
_CHARS_PER_TOKEN = 3.8

def methodology() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "Anthropic messages.count_tokens endpoint (model-authoritative)"
    return f"len(text) / {_CHARS_PER_TOKEN} heuristic (no API key available)"

@lru_cache(maxsize=4096)
def count(text: str) -> int:
    if not text:
        return 0
    if os.environ.get("ANTHROPIC_API_KEY"):
        resp = get_client().messages.count_tokens(
            model=get_model(),
            messages=[{"role": "user", "content": text}],
        )
        return int(resp.input_tokens)
    return max(1, int(len(text) / _CHARS_PER_TOKEN))
```

### 4.2 Why this matters more than it looks

The module docstring says it outright: *"Tokenization specifics are out of scope, so
the choice of algorithm does not matter here. What matters is that every measurement in
this project flows through this single function."*

Three properties:

- **One function.** A 56% reduction is meaningless if the baseline was counted one way
  and the result another. Single-source counting makes the ratio honest.
- **Methodology is recorded.** `budget.json` carries the `methodology()` string
  verbatim, so a reviewer can interpret the numbers rather than trusting them.
- **Two paths, identical interface.** Model-authoritative when a key is available;
  documented heuristic otherwise. The fallback is *declared*, not hidden.
- `@lru_cache` matters because the SDK path is a network call and the same strings get
  counted repeatedly.

---

## 5. `pruner.py` — deterministic, LLM-free

57 fields in, 5 out, no model involved:

```python
KEPT_FIELDS: tuple[str, ...] = (
    "order_id",
    "order_date",
    "order_total_usd",
    "fulfillment_status",
    "return_eligible_until",
)

def prune_lookup_order(raw: dict) -> dict:
    missing = [f for f in KEPT_FIELDS if f not in raw]
    if missing:
        raise PrunerMissingFieldError(...)
    return {field: raw[field] for field in KEPT_FIELDS}
```

The docstring justifies each field against the decision it supports — e.g.
`return_eligible_until` is "the deadline the agent must compare against the current
date… the most decision-load-bearing field in the entire 57-field response."

**The AST audit `test_pruner_has_no_anthropic_import` enforces the LLM-free property.**
The learning objective is *deterministic* pruning; reaching for a model to "decide"
which fields matter would defeat it, and the audit is the reviewer's proof you didn't.

Also note: **raises on missing fields** rather than skipping them. A pruner that
silently drops `return_eligible_until` produces a smaller context and a wrong answer.

---

## 6. `case_facts.py` — schema-constrained extraction

### 6.1 The 12 fields

```python
REQUIRED_FIELDS = (
    "customer_id",
    "refund_order_id", "refund_amount_usd", "refund_status",
    "subscription_id", "subscription_plan",
    "subscription_cancel_reason", "subscription_status",
    "active_payment_method_last4", "new_payment_method_last4",
    "payment_update_failure_code", "payment_update_status",
)
```

Field order is the contract: the tuple, the dataclass, `to_markdown()`, and the prompt
all follow it.

### 6.2 The extraction prompt's rules

```
- Every field is required. If a field cannot be located in the transcript, set it to
  the JSON value null — DO NOT invent.
- Preserve identifiers verbatim. Preserve `last4` values as zero-padded strings.
- Preserve status tokens verbatim (snake_case strings exactly as they appear …).
- `refund_amount_usd` is a number (48.99), not a string. Strip "$".
- Output ONLY the JSON object. No prose, no markdown, no code fences.
```

Every rule targets a specific failure: invention, reformatted IDs, `"0042"` → `42`,
paraphrased status tokens, numbers as strings, output wrapped in fences.

### 6.3 No silent fill

```python
missing = [f for f in REQUIRED_FIELDS if f not in raw or raw[f] is None or raw[f] == ""]
if missing:
    raise CaseFactExtractionError(missing=missing, raw=raw)
```

Three ways to be missing — absent, `null`, empty string — all fail, and the exception
carries both the list and the raw payload for debugging. **The prompt says "null on
missing," the code refuses nulls.** That's not contradictory: the prompt forbids
*invention*, the code forbids *proceeding with gaps*. Together they turn "the model
couldn't find it" into a loud failure instead of a blank in the context.

### 6.4 The audit log

`log_path` writes `case_facts_call.json` with model, token counts, and raw output —
the extraction is one LLM call whose output everything downstream trusts, so it's
recorded verbatim.

### 6.5 Rendering

`to_markdown()` groups fields under `**Customer.**`, `**Refund (resolved).**`,
`**Subscription (resolved).**`, `**Payment update (active).**` — mirroring the three
issues and marking status inline, so the model can tell at a glance which facts are
historical and which are live.

---

## 7. `compressor.py` — tiered compression

### 7.1 The refusal

```python
def summarize_segment(segment: Segment, *, model=None) -> Summary:
    if segment.status != "resolved":
        raise ValueError(
            f"Refusing to summarize segment {segment.issue_id!r} with status "
            f"{segment.status!r}. Only resolved segments are compressed; the active "
            f"segment is preserved verbatim."
        )
```

The invariant is enforced at the function boundary, not left to the caller's
discipline. You cannot accidentally summarize the live thread.

### 7.2 The dispatch

```python
for seg in transcript.segments:
    if seg.status == "resolved":
        summaries[seg.issue_id] = summarize_segment(seg, model=model)
    else:
        active_text = "\n\n".join(t.render() for t in seg.turns)   # byte-exact
        active_id = seg.issue_id
if not active_id:
    raise RuntimeError("Transcript has no active segment.")
```

The active branch calls the **same `render()`** used for the baseline count — which is
why "byte-exact" is verifiable rather than aspirational. `assemble.py` stores it as
`active_raw_text` and an audit compares the assembled body against it.

### 7.3 The committed prompt template

`prompts/compression_prompt.md` is a reviewed deliverable, not an inline f-string. It
specifies exact output shape:

```
**Outcome.** <one sentence, past tense>

**Key facts.**
- <3–6 bullets: amounts, IDs, statuses, dates, reasons>

**Resolution.** <one sentence, terminal state>
```

with rules that mirror the case-facts discipline:

> Preserve every numeric value, ID, and status code verbatim from the source — do not
> round, paraphrase, or generalize ("about $50" is forbidden when the source says
> "$48.99"). Total length: ≤ 500 tokens.

Why a file and not a string literal: it's the artifact a reviewer reads to judge
whether your compression is safe. Burying it in Python hides the most
consequential prose in the system.

---

## 8. `assemble.py` — layout as contract

```python
RESOLVED_TITLES = {
    "refund": "# Resolved: Refund inquiry",
    "subscription": "# Resolved: Subscription cancellation",
}
ACTIVE_TITLES = {
    "payment_update": "# Active issue: Payment-method update",
}
```

Exact strings, level-1 headings only — an AST/regex audit matches against them.
Machine-checkable structure means the *ordering* claim can be tested, not just asserted.

```python
def build(case_facts, compressed) -> AssembledContext:
    case_block = case_facts.to_markdown().rstrip() + "\n"

    resolved_blocks = {}
    for issue_id in ("refund", "subscription"):        # declaration order, explicit
        if issue_id not in compressed.summaries:
            raise KeyError(...)
        resolved_blocks[issue_id] = (
            f"{RESOLVED_TITLES[issue_id]}\n\n{compressed.summaries[issue_id].text.strip()}\n"
        )

    active_block = f"{active_title}\n\n{compressed.active_text}\n"

    markdown = (
        case_block + "\n"
        + resolved_blocks["refund"] + "\n"
        + resolved_blocks["subscription"] + "\n"
        + active_block
    )
```

Details that matter:

- `.rstrip() + "\n"` and `.strip()` normalize whitespace so section boundaries are
  predictable — assembled output shouldn't vary with trailing newlines from an LLM.
- **`compressed.active_text` is interpolated raw** — no strip, no reflow. That's the
  byte-exactness guarantee.
- `active_raw_text` mirrors `compressed.active_text` onto the result so a caller can
  check the assembled body against its source without holding the `Compressed` object.
  The shipped `test_active_segment_byte_exact` doesn't actually use it — it asserts
  `compressed.active_text in assembled.markdown`, and again after the active header —
  so the field is available for that check rather than currently driving it.
- Sections are **exclusive** — no interleaving. A reader (human or model) can locate
  "the resolved refund thread" as one contiguous block.

`section_tokens()` counts each block through `tokens.count`, and `total_tokens()` counts
the whole `markdown` string.

> **They don't sum exactly, and that's expected.** In the reference run the sections add
> to **16,923** while the assembled total is **16,905** — an 18-token gap. Tokenization
> is not additive: counting four strings separately and counting their concatenation are
> different operations, because tokens straddle the joins. Treat per-section numbers as
> an accurate *breakdown of where the weight sits*, not as an arithmetic decomposition
> of the total. If you ever see them match to the token, something is summing rather
> than measuring.

---

## 9. `evaluate.py` and the control

```python
EVAL_SYSTEM_PREFIX = (
    "You are a retail customer-support assistant for Pantry Plus. The conversation"
    " context for the current customer is provided below. Answer the question concisely"
    " using only information present in the context. If the answer is not present,"
    " say 'unknown' — do not invent.\n\n"
)

def _passed(expected: str, answer: str) -> bool:
    return expected.lower() in answer.lower()
```

The assembled context goes in as the **system prompt**; the question is the user turn.
Grading is substring containment against `expected_fragment` — crude, but deterministic
and cheap, which is what you want in a regression gate.

The questions are chosen to span sources:

| Q | Asks | Source | Must fail in control? |
|---|---|---|---|
| Q1 | Refund amount for ORD-77310 | `case_facts` | yes |
| Q2 | Why subscription cancelled | `subscription_summary` | no |
| Q3 | Payment failure code | `active_verbatim` | no |
| Q4 | New card last-4 | `active_verbatim` | no |
| Q5 | Proration refund received? | `subscription_summary` | no |
| Q6 | Exact status token | `case_facts` | yes |

Coverage is the design: if only summary-sourced questions were asked, a passing score
wouldn't tell you the verbatim section was pulling weight.

**Observed result:** 6/6 full; control Q6 fails, Q1 passes (marked "UNEXPECTED PASS").
Q1's `22.14` survives in narrative text; Q6's exact status token does not. The
prediction was directionally right and the surprise is itself informative — it shows
which facts are genuinely *only* in the block.

---

## 10. `budget.json` — the artifact

```json
{
  "token_counter_methodology": "Anthropic messages.count_tokens endpoint (model-authoritative)",
  "baseline_tokens": 38708,
  "assembled_tokens": 16905,
  "reduction_pct": 56.33,
  "per_section_tokens": {
    "case_facts": 204,
    "resolved_refund": 363,
    "resolved_subscription": 567,
    "active": 15789
  },
  "compression_api": {
    "refund":       {"input_tokens": 12334, "output_tokens": 350},
    "subscription": {"input_tokens": 11475, "output_tokens": 554}
  }
}
```

Read it as an argument:

- **`active` is 15,789 of 16,905 — 93.4%.** The compression didn't shrink the live
  thread at all; it shrank everything else to near-nothing around it.
- **The resolved sections cost 12,334 + 11,475 input tokens to produce 363 + 567.**
  ~96% reduction on that material — and it's a *one-time* cost, amortized over every
  future turn.
- **`case_facts` is 204 tokens** — the smallest section, and the one that must never be
  touched. Size and importance are uncorrelated.

The rule the numbers reveal:

> **Resolved threads get summarized. The open thread and the structured facts stay
> byte-exact.** Biggest savings come from segments where only the *outcome* matters;
> the smallest section is the one you must not compress.

---

## 11. Gotchas

### 11.1 Two tests skip until you've run the pipeline

A fresh clone reports **28 passed, 2 skipped**, not 30:

```
SKIPPED tests/test_antipatterns.py:94: no run artifacts available —
        run `python -m retail_context.run --build` first
```

Both assert over the assembled context, which doesn't exist yet. After a run: 30
passed.

**The real lesson is about the skip itself.** These tests *skip* rather than fail when
their input is missing, so a careless reader sees green while two checks never
executed. If you write artifact-dependent tests, decide deliberately whether absence
should skip or fail — and say so where someone will read it.

### 11.2 Compression cost is front-loaded

Compressing costs ~24k input tokens once. It pays back on every subsequent turn that
would have carried 38,708 instead of 16,905. For a two-turn conversation this is a
loss; for a long-running session it's a large win. Know which regime you're in.

### 11.3 The heuristic path silently changes your numbers

Without `ANTHROPIC_API_KEY`, `count()` falls back to `len(text)/3.8`. Reductions
computed under the heuristic are not comparable to model-authoritative ones — which is
exactly why `methodology()` is stamped into `budget.json`. If you compare two runs,
check that line first.

---

## 12. Self-check

1. Why is `tokens.count` a single function rather than a helper called wherever
   convenient?
2. `case_facts` is 204 tokens; `active` is 15,789. Which is compressible and why is
   that the opposite of what size suggests?
3. Q1 passed in the control even though it was predicted to fail. Does that weaken the
   claim that the case-facts block is load-bearing? What does Q6 establish that Q1
   can't?
4. Why does `summarize_segment` raise on an active segment instead of letting the
   caller decide?
5. `test_pruner_has_no_anthropic_import` — what would be lost if the pruner used an LLM
   to choose fields, given it'd probably pick the same five?
6. You add a fourth issue that's also resolved. What changes in `transcript.py`,
   `compressor.py`, and `assemble.py`?
