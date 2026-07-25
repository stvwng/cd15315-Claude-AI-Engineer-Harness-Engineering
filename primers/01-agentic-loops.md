# Primer 1 — Agentic Loops (`stop_reason`-Driven Control Flow)

**System:** Insurance Claims Intake Agent
**Path:** `Build a Claims Intake Agent with a stop_reason-Driven Loop/exercises/03-dynamic-decomposition/solution/`
**Run:** `python -m claims_intake.run --all` · **Tests:** 29

---

## 1. Concepts

### 1.1 An agent harness is a loop the model controls

The defining inversion: your code owns the *loop*, the model owns the *decision to
continue*. Each iteration does exactly one thing — send messages to the model — then
reads `response.stop_reason` to decide what happens next.

```
        ┌──────────────────────────────────────┐
        │  send working_messages to the model  │
        └──────────────────┬───────────────────┘
                           ▼
                  read response.stop_reason
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
    "tool_use"         "end_turn"         anything else
        │                  │                  │
  execute tools,        return          raise loudly
  append results      FinalState     UnexpectedStopReason
  as ONE user turn
        │
        └──► loop again
```

Three branches, no fourth. `max_tokens`, `stop_sequence`, `pause_turn`, `refusal` all
hit the raise — they mean something happened you didn't plan for, and guessing is
worse than stopping.

### 1.2 Why `stop_reason` and not text

The tempting alternative is to read the model's output: *"if the response looks
finished, stop."* This is the anti-pattern the whole module is built around.

`stop_reason` is a **structural** signal from the API. Text is a *sample* from a
distribution. Control flow on the first is deterministic; on the second it's a coin
flip that usually lands right.

### 1.3 Prompt chain vs. dynamic decomposition

A **prompt chain** is a fixed pipeline: `extract → classify → assess → route`. It
works when the steps are known ahead of time. Most production "agents" that fail
interestingly are prompt chains in disguise.

**Dynamic decomposition** means the right next action depends on what was just
learned. A claim opens with *"my basement is flooded."* A fixed pipeline must commit
to `property_damage` or `liability` from those words alone. The agentic loop can
notice the ambiguity in its own accumulated facts, emit `request_clarification`
("what was the source of the water?"), read the reply, *and then* commit.

That clarifying step was in no plan. It emerged from the model inspecting its own
partial state. Same loop, same tools — the *plan* emerged from inspection.

### 1.4 Tool schemas are the agent's API

The set of tools you register is the set of actions the model can take. When the model
chooses between "ask a clarifying question" and "commit to a classification," it is
choosing between two schemas you wrote.

The sharp consequence: **decision logic does not belong in Python.** The moment your
harness contains `if "water" in transcript: claim_type = "property_damage"`, the
decision has moved out of the model. If the model is deciding, the harness has nothing
to branch on — the model's tool choice carries the decision.

### 1.5 The four named anti-patterns

How decision logic sneaks back into Python:

1. **Natural-language termination** — `"done" in text` to decide whether to stop.
2. **Integer-literal iteration caps** — `for _ in range(10)` as the primary stop
   mechanism. A `Budget` is the safety net; a literal cap is not.
3. **Text-content completion checks** — exiting because the response *looks* finished
   rather than because `stop_reason == "end_turn"`.
4. **`if claim_type == "..."` branching** — Python deciding based on what the model said.

Enforced by AST audit (§6), not by convention.

---

## 2. Architecture

```
claims_intake/
├── loop.py           ← THE CORE. run(): the stop_reason branch.
├── tools.py          ← TOOL_SCHEMAS + executors. The action space.
├── system_prompt.py  ← Layer 1. The only place insurance domain lives.
├── session.py        ← ClaimSession: per-claim mutable state.
├── budget.py         ← Budget/BudgetExceeded. Token + wall-clock safety net.
├── tracer.py         ← Append-only JSONL. One object per turn.
├── client.py         ← Anthropic factory; DEFAULT_MODEL.
├── pricing.py        ← Token → USD estimator.
└── run.py            ← Layer 3-ish: fixture runner, run dir, summary.md.
```

Data flow for one claim:

```
fixture JSON ──► ClaimSession (empty)
                      │
                 make_executor(session)  ← closes over session
                      │
    run.py ──► loop.run(client, model, system, tools, messages,
                        tool_executor, budget, tracer)
                      │
              ┌───────┴────────┐
              │  turn loop     │  every tool call mutates `session`
              └───────┬────────┘
                      ▼
                 FinalState + a fully-populated session
                      │
              _summary_row() ──► summary.md, queues/*.jsonl, escalations.jsonl
```

Note the shape: **the loop returns `FinalState`, but the useful output is the
side-effect on `session`.** Tools write into the session; the loop never inspects it.
That's what keeps `loop.py` domain-free.

---

## 3. `loop.py` in detail

### 3.1 The contract, stated in the module docstring

```python
"""The agentic loop.

The defining contract:
- Control flow is driven by `response.stop_reason`.
- Loop continues iff stop_reason == "tool_use".
- Loop returns iff stop_reason == "end_turn".
- Any other stop_reason raises UnexpectedStopReason.
"""
```

### 3.2 The loop body

```python
while True:
    turn += 1
    budget.check()                        # ← raises BudgetExceeded, never truncates
    t0 = time.monotonic()
    response = client.messages.create(
        model=model, max_tokens=max_tokens,
        system=system, tools=tools, messages=working_messages,
    )
    latency_ms = (time.monotonic() - t0) * 1000.0

    input_tokens = int(response.usage.input_tokens)
    output_tokens = int(response.usage.output_tokens)
    total_input += input_tokens
    total_output += output_tokens
    budget.record_input_tokens(input_tokens)
```

`while True` is deliberate — there is no turn cap. The only bound is `budget.check()`
at the top of each iteration, which raises rather than silently stopping.

### 3.3 Tracing before branching

```python
    tool_calls = [
        {"id": b.id, "name": b.name, "input": b.input}
        for b in response.content
        if getattr(b, "type", None) == "tool_use"
    ]
    tracer.write({
        "turn": turn, "stop_reason": response.stop_reason,
        "tool_calls": tool_calls, "latency_ms": round(latency_ms, 1),
        "input_tokens": input_tokens, "output_tokens": output_tokens,
    })
```

Every turn is recorded *before* any control decision. That ordering matters: if the
next branch raises, the trace still explains why.

### 3.4 The three branches

```python
    if response.stop_reason == "end_turn":
        working_messages.append({"role": "assistant", "content": response.content})
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
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_content,
            })
        working_messages.append({"role": "user", "content": tool_results})
        continue

    raise UnexpectedStopReason(
        f"turn {turn}: unexpected stop_reason={response.stop_reason!r}"
    )
```

Four things worth burning in:

1. **All tool results go in ONE user turn.** The model may emit several `tool_use`
   blocks in a single turn; every result is collected into one message with a list of
   `tool_result` blocks. Sending them as separate user turns breaks the API contract.
2. **`tool_use_id` must round-trip.** Each result carries the `id` of the call it
   answers.
3. **The loop never inspects `block.name`.** It doesn't know or care that
   `route_to_adjuster` is terminal — it executes whatever the model asked for. The
   terminal-ness lives in `session.terminal_called`, which only `run.py` reads.
4. **Errors are returned, not raised.** `ToolExecutor` returns a JSON string with
   `is_error: true`; it never throws. A raising executor would kill the loop on a
   recoverable problem.

### 3.5 Reading a real trace

From `claim_05_auto_collision.jsonl`:

```
turn 1: stop_reason=tool_use   tools=[lookup_policy, record_claim_fact ×6]
turn 2: stop_reason=tool_use   tools=[classify_claim]
turn 3: stop_reason=tool_use   tools=[assess_severity]
turn 4: stop_reason=tool_use   tools=[route_to_adjuster]     ← terminal tool
turn 5: stop_reason=end_turn   tools=[]                      ← loop returns
```

The instructive detail: **turn 4 does not stop the loop.** Calling the terminal tool
is just another `tool_use`. The loop continues, hands back the result, and the *model*
chooses to stop at turn 5. That's the inversion in §1.1, visible in an artifact.

---

## 4. `tools.py` — the action space

### 4.1 The seven tools

| Tool | Purpose | Terminal? |
|---|---|---|
| `lookup_policy` | Confirm policy, read coverage | |
| `record_claim_fact` | One normalized fact into the case file | |
| `classify_claim` | Commit type + confidence + rationale | |
| `assess_severity` | Commit low/medium/high + rationale | |
| `request_clarification` | Ask the claimant ONE question | |
| `route_to_adjuster` | Send to matching queue | ✅ |
| `escalate_to_human` | Hand to a human reviewer | ✅ |

### 4.2 Descriptions carry the loop contract

The two terminal tools have overlapping inputs — both accept the accumulated case file,
either could plausibly end a claim. Disambiguation is a *number*, not a vibe:

> `route_to_adjuster` — "**TERMINAL TOOL.** Route this claim to the matching adjuster
> queue. Call this exactly once when classification confidence is at least **0.6** and
> severity has been assessed. After this, your next response should be a brief
> confirmation and stop with `end_turn`."

> `escalate_to_human` — "**TERMINAL TOOL.** Escalate … when classification confidence
> is below **0.6** even after clarification, or when the claim cannot be routed safely
> (multiple plausible types, missing critical facts the claimant cannot supply, policy
> disputes)."

Notice the description tells the model *about the loop* — "stop with `end_turn`". The
tool description is doing Layer 1 work about a Layer 2 mechanism.

### 4.3 Structured errors

```python
def _err(category: str, retryable: bool, message: str) -> str:
    return json.dumps({
        "is_error": True,
        "error_category": category,
        "is_retryable": retryable,
        "message": message,
    })
```

`is_retryable` is the payload a bare string can't carry. The system prompt leans on it
directly: *"Tool errors return JSON with `is_error: true`. Read the message and adapt
— do not retry blindly."*

### 4.4 Tools enforce ordering the prompt merely requests

```python
def _t_route_to_adjuster(session, inp) -> str:
    if session.terminal_called:
        return _err("permanent", False, "terminal tool already called this claim")
    ...
    if session.classification is None:
        return _err("permanent", False, "classify_claim must be called before routing")
    if session.severity is None:
        return _err("permanent", False, "assess_severity must be called before routing")
```

The prompt *asks* for classify → assess → route. The tool *enforces* it. Same idea as
Primer 0 §3: the sequencing is checkable, so it lives in code — while *which* queue
remains the model's call.

### 4.5 The clarification dispatcher

```python
def _t_request_clarification(session, inp) -> str:
    ...
    qlow = question.lower()
    for pattern, reply in session.clarification_responses.items():
        if pattern.lower() in qlow:
            return _ok({"claimant_reply": reply})
    return _ok({"claimant_reply": "NO_RESPONSE"})
```

The fixture supplies a keyword → reply map (`{"source": "...", "neighbor": "..."}`).
Loose substring matching simulates a claimant. Unmatched → `NO_RESPONSE`, and the
prompt covers that case: *"If you receive `NO_RESPONSE`, do not ask the same question
again. Either commit to a classification or escalate."*

> **Note the placement.** This is a string-membership test — the very thing the AST
> audit forbids. But it lives in `tools.py`, not `loop.py`, and it drives a *tool
> result*, not control flow. The audit only parses `loop.py`. The distinction is
> exactly right: matching a scripted fixture reply is data lookup; deciding whether to
> keep looping is control flow.

---

## 5. Supporting modules

### 5.1 `budget.py` — the safety net that replaces the turn cap

```python
@dataclass
class Budget:
    max_input_tokens: int
    max_wall_clock_s: float
    _start: float = 0.0
    input_tokens_used: int = 0

    def check(self) -> None:
        if self.input_tokens_used > self.max_input_tokens:
            raise BudgetExceeded(...)
        elapsed = time.monotonic() - self._start
        if elapsed > self.max_wall_clock_s:
            raise BudgetExceeded(...)
```

Bounds **cost**, not conversation shape. Defaults: 500,000 input tokens, 180s.

Why this is not just a fancier `range(10)`: a turn cap says "conversations are at most
N turns," which is a claim about the *domain* and is usually wrong. A token budget says
"this may cost at most X," which is a claim about your *wallet* and is always right.

### 5.2 `session.py` — where "done" is defined

```python
@property
def terminal_called(self) -> bool:
    return self.routing is not None or self.escalation is not None

@property
def outcome(self) -> str:
    if self.routing is not None:   return "routed"
    if self.escalation is not None: return "escalated"
    return "incomplete"
```

`incomplete` is the outcome when the loop returned without a terminal tool ever
firing. Keep it in mind for §7.

### 5.3 `tracer.py`

Append-only JSONL, flushed per write, with a `NullTracer` subclass for tests that
collects into a list and never touches disk.

### 5.4 `pricing.py`

```python
rate = _RATES.get(model) or _RATES["claude-sonnet-4-6"]
```

Unknown models fall back to the **Sonnet** rate — deliberately conservative. Better to
over-estimate than under-estimate when budgeting.

---

## 6. The AST audit (`tests/test_antipatterns.py`)

Four tests parse source with `ast` and assert on structure.

**`test_no_string_membership_against_text_in_loop`** — flags any `Compare` node using
`In` whose left operand is a string constant. Kills `"done" in text`.

**`test_no_integer_literal_iteration_cap_in_loop`** — walks for `for _ in
range(<int literal>)` and `while <x> < <int literal>`. Budgets are fine because they
read their cap from an attribute or argument, not a literal.

**`test_stop_reason_is_loop_control`** — the positive check. Requires `loop.py` to
reference `stop_reason`, and requires some `while` loop whose body mentions
`stop_reason` and contains a `return` or `raise`.

**`test_no_claim_type_equality_branching_in_package`** — no `if claim_type == "..."`
outside `tools.py`/`pricing.py`.

> **Why AST and not a unit test.** A unit test checks behavior on the paths it
> exercises. An AST audit checks a property across *every* path, including code no test
> covers. It's the difference between "the tests didn't catch a violation" and "a
> violation cannot exist in this file."

---

## 7. Gotchas — measured, not hypothetical

### 7.1 `end_turn` without a terminal tool

The loop is correct and the claim still fails. Observed across three runs:

| Run | Model | Terminated |
|---|---|---|
| `20260725_180221` | Haiku 4.5 | 4/8 |
| (re-run) | Haiku 4.5 | 4/8 |
| `20260725_180619` | Sonnet 4.6 | 3/8 |

Instrumented `claim_01`: the model calls `lookup_policy` + four `record_claim_fact`s,
then asks *"What is your estimated cost of repair or replacement…?"* **as plain text**
instead of calling `request_clarification`. Plain text is an `end_turn`. The loop
correctly returns. `terminal_called` is False → `incomplete`.

Not a model-capability ceiling — Sonnet was *worse*. It's the gap between a prompt
contract and an enforced one.

**The fix** (`terminal-nudge.patch`), which took it to 8/8:

```python
# loop.py — a callback, so the loop stays domain-agnostic
TerminationCheck = Callable[[], "str | None"]
DEFAULT_MAX_TERMINAL_NUDGES = 2

    if response.stop_reason == "end_turn":
        working_messages.append({"role": "assistant", "content": response.content})
        correction = termination_check() if termination_check is not None else None
        if correction is not None and nudges_used < max_terminal_nudges:
            nudges_used += 1
            working_messages.append({"role": "user", "content": correction})
            tracer.write({"turn": turn, "event": "terminal_nudge", ...})
            continue
        return FinalState(...)
```

```python
# run.py — the domain knowledge of what "finished" means
def _terminal_check() -> str | None:
    if session.terminal_called:
        return None
    return ("You ended your turn without taking a terminal action. …")
```

Design points worth internalizing:

- The **loop stays generic**. It asks a callback; it never learns what a claim is.
- It **never picks** the terminal tool — route-vs-escalate stays the model's judgment.
- The nudge cap is a parameter, not a literal in a `while` — so all four anti-pattern
  tests still pass.
- Result: 4/8 → 8/8, 7 routed + 1 escalated, every outcome matching its fixture.
  5 claims needed one nudge, 3 needed none, none needed two.

### 7.2 Cost is superlinear in turns

Every turn resends the whole transcript plus accumulated tool results. Turn 1 costs
~3.5k input tokens; by turn 5 the conversation carries six `record_claim_fact` results
plus the policy record. Baseline run: the three 2-turn `incomplete` claims cost
~$0.0085 each; completed 5-turn claims cost ~$0.023.

Corollary: **incomplete claims are pure waste.** Baseline spent $0.0461 of $0.1337
(34.5%) on claims that produced no routing, no escalation, no queue entry.

### 7.3 Environment: `anthropic==0.39.0` vs `httpx>=0.28`

`pyproject.toml` pins `anthropic` but leaves `httpx` free. `httpx` 0.28 removed the
`proxies` argument that `anthropic` 0.39.0 still passes:

```
TypeError: Client.__init__() got an unexpected keyword argument 'proxies'
```

Fix: `uv pip install "httpx<0.28"`. Note the 29 tests pass either way — they use fakes
and never construct a real client, so the suite cannot catch this.

---

## 8. Self-check

1. Why does calling `route_to_adjuster` not end the loop?
2. The model emits three `tool_use` blocks in one turn. How many messages get appended
   to `working_messages` before the next API call, and what are they?
3. Why is `Budget` acceptable where `for _ in range(10)` is an anti-pattern? Both cap
   the loop.
4. `_t_request_clarification` does `if pattern.lower() in qlow`. Why doesn't that
   violate the string-membership anti-pattern?
5. A claim ends `incomplete`. Walk through what the model did, what `loop.py` did, and
   what `session.outcome` reports — and say which of the three is buggy.
6. You need to guarantee every claim reaches a terminal tool. Give two designs and say
   which keeps `loop.py` domain-agnostic.
