# Primer 3 — Claude Code Configuration as Harness Engineering

**System:** E-Commerce Team Config
**Path:** `Configure Claude Code for a Multi-Surface Monorepo Team/04-plan-mode-and-explore-decision-doc/solution/`
**Run:** `python -m ecommerce_team_config .` → `OK`, exit 0 · **Tests:** 35

---

## 1. Concepts

### 1.1 Configuration is a harness

The other three systems build harnesses in Python. This one builds a harness in
**Markdown** — and the point is that it's the same discipline. `allowed-tools` is an
allowlist exactly as much as a Python permission check is. `context: fork` is context
isolation exactly as much as a subprocess boundary is.

The difference is who writes it: configuration is the harness surface that
non-harness-engineers touch. Which is why this project ships a **validator** — a
Python package that mechanically checks the Markdown, so the config can't rot.

### 1.2 The scope hierarchy

Claude Code resolves configuration across three scopes:

| Scope | Path | Purpose | In git? |
|---|---|---|---|
| **Project** | `./CLAUDE.md`, `.claude/standards/`, `.claude/rules/` | Conventions for *this* repo, shared with the team | ✅ yes |
| **User** | `~/.claude/CLAUDE.md`, `~/.claude/commands/`, `~/.claude/skills/` | Personal preferences | ❌ never |
| **Directory** | `path/CLAUDE.md` in a subdir | Conventions narrower than the repo | ✅ yes |

The boundary is **collaboration**, not technical capability:

> Project scope is a *promise to teammates*. User scope is a *preference that must
> never silently change a colleague's behavior*.

If something would only matter to you — your commit-message style, a personal
`/morning` command — it goes in `~/.claude/`. Anything the whole team should agree on
goes in the repo.

### 1.3 Modular composition via `@import`

A single monolithic `CLAUDE.md` becomes unreadable and unmergeable. The pattern:
keep the entry point scannable, put the actual conventions in focused files:

```markdown
- @.claude/standards/frontend.md
- @.claude/standards/api.md
- @.claude/standards/database.md
- @.claude/standards/testing.md
```

Standards are **always loaded**. Rules (next section) load conditionally.

### 1.4 Path-scoped rules vs. directory-level CLAUDE.md

The key architectural distinction in this project.

- A **directory-level `CLAUDE.md`** attaches conventions to a **location**.
- A **path-scoped rule** attaches conventions to a **file shape**, wherever it lives.

In this monorepo, tests are co-located next to the code they test — scattered across
`src/components/`, `src/pages/`, `src/api/`. So:

```yaml
---
description: Conventions for test files (co-located *.test.ts and *.test.tsx)
paths:
  - "**/*.test.tsx"
  - "**/*.test.ts"
---
```

One rule, every test file in the repo. Reproducing this with directory files means
copying identical conventions into three directories today — and a silent drift problem
the first time someone edits one copy.

The converse holds too, and the repo demonstrates both: `react.md` scopes by
`src/components/**/*` and `src/pages/**/*`, `api.md` by `src/api/**/*`. Those
conventions genuinely *are* locational. **Scope by shape when the convention is
cross-cutting; scope by location when the convention is local.**

### 1.5 Forked context

`context: fork` runs a skill in a sub-agent with its own context window. Two distinct
benefits, often conflated:

1. **Context isolation.** A pre-deploy check reads diffs and git history. None of that
   noise lands in the main session — only the pass/fail summary returns. The subtle
   failure mode without it isn't just wasted tokens: the main session ends up reasoning
   over half-remembered diff fragments.
2. **Blast-radius reduction**, when paired with a read-only `allowed-tools` list. A
   "check" that could write is not a check.

### 1.6 Allowlists at argument granularity

```yaml
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git log:*)
```

`Bash(git status:*)` permits `git status` and not `git push`. Enforcement is at the
**argument** level, not the tool level — bare `Bash` would grant everything. No
`Write`, no `Edit`, no unrestricted `Bash`.

---

## 2. Architecture

```
solution/
├── CLAUDE.md                          ← project entry point; @imports; scope table
├── .claude/
│   ├── standards/                     ← always loaded
│   │   ├── frontend.md  api.md  database.md  testing.md
│   ├── rules/                         ← conditionally loaded by glob
│   │   ├── react.md  api.md  tests.md
│   ├── commands/
│   │   └── review.md                  ← the /review slash command
│   └── skills/
│       └── deploy-check/SKILL.md      ← context: fork + read-only tools
├── docs/
│   └── plan-mode-vs-direct-execution.md
├── src/                               ← React/Node/Postgres scaffold to scope against
└── ecommerce_team_config/             ← THE VALIDATOR (you consume, don't edit)
    ├── __main__.py        ← CLI: aggregates all checks, prints OK / FAIL
    ├── claude_md.py       ← scope-doc + /memory diagnostic checks
    ├── imports.py         ← @-import parsing and resolution
    ├── rules.py           ← frontmatter parsing + glob matching (pathspec)
    ├── command.py         ← /review body structure checks
    ├── skill.py           ← SKILL.md frontmatter + body checks
    ├── frontmatter.py     ← shared YAML frontmatter splitter
    └── tool_allowlist.py  ← read-oriented vs write-capable classification
```

The exercise arc:

| Ex | Builds | Cumulative tests |
|---|---|---|
| 1 | `CLAUDE.md` + `.claude/rules/*` | — |
| 2 | `.claude/commands/review.md` | 21 |
| 3 | `.claude/skills/deploy-check/SKILL.md` | 28 |
| 4 | `docs/plan-mode-vs-direct-execution.md` | 35 |

---

## 3. `CLAUDE.md` — the entry point

Three things the validator requires:

**1. Resolvable `@import`s.**

```markdown
- @.claude/standards/frontend.md
- @.claude/standards/api.md
- @.claude/standards/database.md
- @.claude/standards/testing.md
```

**2. A scope-distinction table** naming project vs. user level, stating user config is
not version-controlled, and giving a concrete user-scope example:

> | **User-level** | `~/.claude/CLAUDE.md`, `~/.claude/commands/` | Personal preferences. **Not shared via version control** — they stay on your laptop and never reach teammates. |

with the worked example: "a personal `/morning` summary command."

**3. A `/memory` diagnostic reference** — the command that shows which config files
actually loaded. This is the debugging entry point when a rule doesn't fire, and the
validator insists it be documented where a confused teammate will find it.

The file also explains *why* rules are preferred over directory files:

> **Directory-level** … Conventions narrower than the whole repo. We prefer
> `.claude/rules/` with glob `paths:` instead, so cross-cutting conventions (e.g. test
> files everywhere) work cleanly.

---

## 4. `.claude/rules/` and glob matching

### 4.1 The three rules

| File | `paths:` | Scoping strategy |
|---|---|---|
| `tests.md` | `**/*.test.tsx`, `**/*.test.ts` | by **shape** — co-located everywhere |
| `react.md` | `src/components/**/*`, `src/pages/**/*` | by **location** |
| `api.md` | `src/api/**/*` | by **location** |

### 4.2 How the validator parses them (`rules.py`)

```python
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)

def load_rule(path: Path) -> Rule:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{path}: no YAML frontmatter found (expected --- ... ---)")
    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = match.group(2)
    raw_paths = frontmatter.get("paths")
    if not isinstance(raw_paths, list) or not all(isinstance(p, str) for p in raw_paths):
        raise ValueError(f"{path}: frontmatter 'paths' must be a list of strings")
    return Rule(name=path.stem, paths=tuple(raw_paths), body=body)
```

### 4.3 Glob semantics — gitignore, not fnmatch

```python
def _matches(patterns: tuple[str, ...], file_path: str) -> bool:
    spec = PathSpec.from_lines("gitignore", patterns)
    return spec.match_file(file_path)
```

`PathSpec.from_lines("gitignore", …)` means the patterns follow **gitignore**
semantics. That's why `**/*.test.ts` matches at any depth — a detail worth remembering
when a rule doesn't fire and you're tempted to blame Claude Code rather than your glob.

`matching_rules(rules_dir, file_path)` simulates resolution for a given file, which is
how the tests assert that editing `src/api/orders.ts` activates `api.md` and not
`react.md`.

### 4.4 Body quality is checked too

```python
def body_has_concrete_convention(body: str) -> bool:
    """Heuristic: at least ~10 non-trivial lines and at least one concrete
    code construct (a backtick-quoted identifier, a path, etc.)."""
    non_trivial = [
        line for line in body.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    has_code_ref = bool(re.search(r"`[^`]+`", body))
    return len(non_trivial) >= 10 and has_code_ref
```

A heuristic, and openly labeled as one. It can't judge whether a convention is *good* —
it can catch a rule file that's all headings and no content. That's the realistic
ambition for mechanical checks on prose: catch the empty, don't grade the argument.

---

## 5. `.claude/skills/deploy-check/SKILL.md`

### 5.1 Frontmatter

```yaml
---
name: deploy-check
description: Run read-only pre-deployment validation in a forked sub-agent and report
             a single pass/fail summary back to the main session
context: fork
argument-hint: "[target-branch] (defaults to main)"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git rev-parse:*)
  - Bash(git ls-files:*)
---
```

The `description` states the contract precisely: *read-only*, *forked sub-agent*,
*single pass/fail summary back*. That last clause is the whole justification for
forking — a lot of reading in, one line out.

### 5.2 Required body sections

The validator demands five things (`_check_deploy_check_skill`):

1. **Skill-vs-`CLAUDE.md` rubric** — when does something belong in a skill rather than
   always-loaded config? (Roughly: procedures you *invoke* vs. conventions that always
   *apply*.)
2. **Main-session isolation rationale** with a **Branching Reality** reference.
3. **≥3 checks**, each with **Detect / Pass / Fail** criteria.
4. **Personal-customization note** — how to override it in user scope.
5. Correct frontmatter (`context: fork`, read-only allowlist).

Requirement 3 is the interesting one. A check without an explicit fail criterion isn't
a check; it's a suggestion. Forcing Detect/Pass/Fail turns prose into something with a
truth value.

### 5.3 Two documented foot-guns

Both from the exercise README, both worth remembering:

**The YAML colon trap.**

```yaml
argument-hint: <target: optional>     # ✗ parses as a nested mapping — file breaks
argument-hint: "[target] (defaults to main)"   # ✓ quoted
```

**LSP lag.** As of 2026-05 the skill-frontmatter LSP lists only `argument-hint`,
`compatibility`, `description`, `disable-model-invocation`, `license`, `metadata`,
`name`, `user-invokable` — so it flags `context: fork` and `allowed-tools`. The
documentation is authoritative; the LSP lags. Top-level `context: fork` is correct.
(`metadata: {context: fork}` is a workaround if the warning blocks you, but it isn't
canonical.)

---

## 6. `.claude/commands/review.md`

A **project-scoped slash command** — every teammate gets the same `/review`.

```yaml
---
description: Run the e-commerce team's PR review checklist against a pull request or local diff
argument-hint: <pr-number | "HEAD~1..HEAD" | path/to/file>
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git show:*)
---
```

Validator-required body sections (`_check_review_command`):

| Requirement | Why |
|---|---|
| Must-report vs. skip criteria | Without it, review output is unbounded nitpicking |
| ≥2 concrete I/O examples | Examples pin down format better than description |
| Interview pattern | What to do when the diff's intent is ambiguous — ask, don't guess |
| Interacting vs. independent guidance | Bundle findings that interact; separate ones that don't |
| Read-only `allowed-tools` | A reviewer must not rewrite the code under review |

Same theme as everywhere else: the *judgment* (is this a real problem?) stays with the
model; the *boundaries* (read-only, must report these categories, format like this) are
enforced.

---

## 7. `tool_allowlist.py` — the enforcement core

The most reusable module in the project.

```python
_READ_ONLY_TOOLS = frozenset({"Read", "Grep", "Glob", "WebSearch", "TodoWrite", "Task"})

_WRITE_CAPABLE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "WebFetch"})

_SAFE_BASH_PREFIXES = frozenset({
    "git diff", "git log", "git show", "git status", "git blame", "git branch",
    "git ls-files", "git rev-parse", "git rev-list", "git remote",
    "gh pr diff", "gh pr view", "gh pr list", "gh pr checks",
    "gh issue view", "gh issue list",
    "ls", "cat", "head", "tail", "wc", "find",
})

_BASH_SCOPED_RE = re.compile(r"^Bash\((.+?)(?::.*)?\)$")

def is_read_oriented(tool: str) -> bool:
    tool = tool.strip()
    if tool in _WRITE_CAPABLE_TOOLS:
        return False
    if tool in _READ_ONLY_TOOLS:
        return True
    if tool == "Bash":
        return False                    # ← bare Bash is never read-only
    match = _BASH_SCOPED_RE.match(tool)
    if match:
        prefix = match.group(1).strip()
        return any(prefix == p or prefix.startswith(p + " ") for p in _SAFE_BASH_PREFIXES)
    return False                        # ← unknown tools are write-capable
```

Four design decisions worth stealing:

1. **Default deny.** The final `return False` means an unrecognized tool is treated as
   write-capable. New tool you've never heard of? Not read-only until proven otherwise.
2. **Bare `Bash` is explicitly denied**, before the regex gets a chance.
3. **Prefix matching is anchored.** `prefix == p or prefix.startswith(p + " ")` stops
   `git logsomething` from matching `git log`. The trailing space is doing real work.
4. **`WebFetch` counts as write-capable.** It's read-shaped but produces out-of-band
   side effects (an outbound network request), which is the right way to think about
   "write" — *observable effects outside this process*, not just disk writes.

---

## 8. Validating prose: `frontmatter.py`, `command.py`, `skill.py`

These three modules are the interesting engineering problem in this project: **how do
you mechanically check a document written in natural language?** The answer here is
regex families plus a small state machine — and the honest answer is that it works for
*structure* and not at all for *quality*.

### 8.1 `frontmatter.py` — one parser, three consumers

```python
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)

def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{path}: no YAML frontmatter found (expected --- ... ---)")
    data = yaml.safe_load(match.group(1)) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: frontmatter must be a YAML mapping")
    return data, match.group(2)
```

Rules, commands, and skills all split the same way. `\A` anchors to file start — a
`---` further down (a horizontal rule in the body) can't be mistaken for frontmatter.
`or {}` handles empty frontmatter; the `isinstance(data, dict)` check rejects a
frontmatter block that parses as a list or scalar.

> This is where the **YAML colon trap** from §5.3 surfaces. `argument-hint: <target:
> optional>` parses as a nested mapping, so `data` is still a dict and the check passes
> — but the value is now `{"<target": "optional>"}` rather than a string. The parser
> can't catch it; only quoting can.

### 8.2 `command.py` — regex families per requirement

Each body requirement gets its own regex family, and a requirement passes only when
*all* its families match:

```python
_MUST_REPORT_RE = re.compile(r"\bmust[- ]report\b|\bmust\s+(flag|raise)\b", re.IGNORECASE)
_SKIP_RE        = re.compile(r"\bskip\b|\bdo\s+not\s+report\b|\bignore\b", re.IGNORECASE)

def body_has_must_report_vs_skip_criteria(body: str) -> bool:
    return bool(_MUST_REPORT_RE.search(body)) and bool(_SKIP_RE.search(body))
```

The conjunction is the design. A review command that only says what to report produces
unbounded nitpicking; one that only says what to skip says nothing. **Both halves must
be present**, so the check is on the *contrast*, not on either side.

The most demanding one requires four families at once:

```python
def body_has_interacting_vs_independent_guidance(body: str) -> bool:
    return (
        bool(_INTERACTING_RE.search(body))     # "interacting"
        and bool(_INDEPENDENT_RE.search(body)) # "independent"
        and bool(_BUNDLE_RE.search(body))      # bundle | single message/report | all together
        and bool(_SEQUENTIAL_RE.search(body))  # sequential | one at a time | separate(ly)
    )
```

Two concepts *and* both of their prescribed handlings. You can't satisfy it by naming
the distinction without saying what to do about it.

### 8.3 The I/O-example pairing — and a discrepancy worth knowing

```python
def body_has_io_examples(body: str, *, minimum: int = 2) -> bool:
    """A concrete I/O example has a labeled input and a labeled output near each other.
    We require at least `minimum` such pairs, each within a 40-line window.
    """
    input_positions  = [m.start() for m in re.finditer(r"^\s*(?:#+\s*|\*\*)?Input\b",  body, re.MULTILINE)]
    output_positions = [m.start() for m in re.finditer(r"^\s*(?:#+\s*|\*\*)?Output\b", body, re.MULTILINE)]
    pairs = 0
    for i_pos in input_positions:
        nearby = [o for o in output_positions if 0 < o - i_pos < 4000]
        if nearby:
            pairs += 1
    return pairs >= minimum
```

The `(?:#+\s*|\*\*)?` prefix accepts `### Input`, `**Input**`, or bare `Input` — the
three ways someone would plausibly label it.

Two things to notice, because they're instructive about heuristic checks generally:

1. **The docstring says "a 40-line window"; the code uses `< 4000` characters.** Those
   aren't the same unit. The check is looser or tighter than documented depending on
   line length. Not a bug that matters here, but a good reminder that a heuristic's
   *docstring* and its *behavior* drift easily.
2. **The same Output can satisfy multiple Inputs.** Two `Input` headings followed by
   one `Output` within range counts as two pairs. The check verifies "there is labeled
   I/O structure," not "there are exactly N complete examples."

Both are acceptable for the job — catch the empty document, don't grade the prose — as
long as you know that's what you're getting.

### 8.4 `skill.py` — a state machine for check blocks

The hardest requirement is "≥3 checks, each with Detect / Pass / Fail." That needs
actual structure extraction, not just a search:

```python
def _extract_check_blocks(body: str) -> list[tuple[str, list[str]]]:
    blocks, in_checks_section = [], False
    current_title, current_lines = None, []
    for raw in body.splitlines():
        line = raw.rstrip()
        h2 = re.match(r"^##\s+(.+)$", line)
        h3 = re.match(r"^###\s+(.+)$", line)
        if h2:
            if current_title is not None:
                blocks.append((current_title, current_lines))
                current_title, current_lines = None, []
            in_checks_section = "check" in h2.group(1).lower()   # ← H2 toggles the section
            continue
        if h3 and in_checks_section:
            if current_title is not None:
                blocks.append((current_title, current_lines))
            current_title, current_lines = h3.group(1).strip(), []
            continue
        if current_title is not None:
            # Strip leading list/bold markers so the marker regexes can match.
            stripped = re.sub(r"^[\s\-\*\d\.]*\*{0,2}", "", line)
            current_lines.append(stripped)
    ...
```

How it works:

- An **H2 containing "check"** turns the section on; any other H2 turns it off. That's
  what scopes extraction to the Checks section without hard-coding a heading string.
- Each **H3 inside** starts a new check block.
- Each body line is **stripped of leading list markers and bold** — `- **Detect:** …`
  becomes `Detect:` — so the marker regexes, which are anchored with `^`, can match.
  Without that normalization every bulleted criterion would be invisible.

Then each block is scored against three anchored regexes:

```python
_DETECTION_RE = re.compile(r"^\s*(detect|how\s+to\s+(check|detect)|signal)\b", re.IGNORECASE)
_PASS_RE      = re.compile(r"^\s*(pass|green|ok\b|success)\b", re.IGNORECASE)
_FAIL_RE      = re.compile(r"^\s*(fail|red|block|stop)\b", re.IGNORECASE)
```

`^`-anchoring is deliberate: the word "fail" appearing mid-sentence in prose shouldn't
count as a fail *criterion*. It has to lead a line.

### 8.5 The rubric check — three conditions for one idea

```python
def body_has_skill_vs_claude_md_rubric(body: str) -> bool:
    """Heuristic: a real decision rubric mentions both "skill" and "CLAUDE.md", and
    contrasts on-demand/forked against always-loaded/universal."""
    mentions_both = "skill" in body.lower() and "claude.md" in body.lower()
    mentions_on_demand = re.search(r"on[- ]demand|forked|task[- ]specific", body, re.IGNORECASE)
    mentions_always_loaded = re.search(
        r"always[- ]loaded|universal|every\s+session", body, re.IGNORECASE
    )
    return bool(mentions_both and mentions_on_demand and mentions_always_loaded)
```

This encodes the actual distinction it wants you to have written down: **skills are
on-demand and forked; `CLAUDE.md` is always-loaded and universal.** You can't pass by
naming both artifacts — you have to name the axis that separates them.

And `body_has_personal_customization_note` requires the literal string
`~/.claude/skills/`, which is why the personalization note has to name the real path
rather than gesture at "your own config." A path a reader can copy is worth more than a
description.

### 8.6 What this can and can't do

| Catches | Misses |
|---|---|
| Missing sections entirely | A section that's present but wrong |
| Missing frontmatter fields | Bad judgment in the prose |
| Write-capable tools in a read-only allowlist | A check whose Fail criterion is nonsense |
| Fewer than 3 checks | Three checks that don't matter |
| Absent Detect/Pass/Fail markers | Criteria that contradict each other |

That's the realistic ambition, and the modules are honest about it — three of these
functions carry a docstring that literally begins "Heuristic:". The value isn't that it
proves the config is good; it's that **the config cannot silently rot into emptiness**,
and that every teammate's contribution has to clear the same structural floor.

---

## 9. `imports.py` — dangling-reference detection

```python
_IMPORT_RE = re.compile(r"@([\w./-]+\.\w+)")

def unresolved_imports(claude_md: Path, *, repo_root: Path) -> list[str]:
    missing = []
    base = claude_md.parent
    for raw in find_imports(claude_md):
        candidate = raw[2:] if raw.startswith("./") else raw
        path = (
            (repo_root / candidate[1:]).resolve()
            if candidate.startswith("/")
            else (base / candidate).resolve()
        )
        if not path.exists():
            missing.append(raw)
    return missing
```

Handles repo-absolute (`/…`), explicit-relative (`./…`), and bare relative paths. The
failure it prevents is quiet and nasty: a typo'd `@import` means the standard silently
never loads, and nothing tells you — the config *looks* right and half of it isn't
there. This is the same class of bug as System 2's skipped tests: **absence that
presents as success.**

---

## 10. `__main__.py` — how the validator reports

```python
problems: list[str] = []
problems.extend(_check_claude_md(repo_root))
problems.extend(_check_rules(repo_root))
problems.extend(_check_review_command(repo_root))
problems.extend(_check_deploy_check_skill(repo_root))

if problems:
    print(f"FAIL ({len(problems)} problems):", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    return 1
print("OK")
return 0
```

- **Accumulates rather than short-circuits** — one run tells you everything wrong, not
  just the first thing.
- **`FAIL` to stderr, `OK` to stdout**, with exit codes. CI-shaped by construction.
- Each problem string names the file and the missing property, e.g.
  `"/deploy-check allowed-tools includes write-capable entries: ['Bash']"`.

---

## 11. `docs/plan-mode-vs-direct-execution.md`

Exercise 4's deliverable: a decision framework with four worked examples from this
repo's own scaffold.

| Mode | Use when | Worked example |
|---|---|---|
| **Plan mode** | Multi-file, design decisions to review before edits | Extract a shared `useCart` hook across three components |
| **Direct execution** | Single, well-scoped, obviously-correct change | Add `min: 0` validation to one quantity field |
| **Explore sub-agent** | Need an inventory before you can plan | Find all `processRefund` call sites (scratchpad pattern) |
| **Combined** | Investigate, then mechanically apply | Rename `ordersRepo.findById` → `getById` |

The organizing question: **how much does a wrong first move cost?** Cheap and local →
just do it. Expensive or wide → plan first. Unknown scope → explore first, *then*
decide which of the other two you're in.

Note that "Explore" is the same shape as `context: fork`: fan out, read a lot, return a
small summary. The scratchpad pattern recurs across all four systems.

---

## 12. Gotchas

- **YAML colon trap** — quote any frontmatter value containing `: `.
- **LSP false warnings** on `context: fork` / `allowed-tools`. Docs win; the LSP lags.
- **Bare `Bash` in an allowlist** silently makes a "read-only" command write-capable.
  The validator catches it; nothing else will.
- **A typo'd `@import` fails silently** in Claude Code itself — the standard just never
  loads. Run the validator, or `/memory`.
- **`_PROJECT_LEVEL_RE` in `claude_md.py` is the only scope regex without
  `re.IGNORECASE`.** It passes on the shipped `CLAUDE.md` because the prose happens to
  contain lowercase "project-level" and the string `.claude/CLAUDE.md`. Write the same
  idea as "Project-Level" in a table and nowhere else, and the check fails with a
  message that won't tell you capitalization was the problem.
- **Glob semantics are gitignore-style.** `**/*.test.ts` matches at any depth;
  `*.test.ts` does not.
- **`/memory` is the diagnostic** when a rule doesn't fire. It shows what actually
  loaded — always check that before assuming the rule body is wrong.

---

## 13. Self-check

1. A convention applies to every `*.test.ts` in a monorepo where tests are co-located.
   Path-scoped rule or directory `CLAUDE.md`? Give two reasons.
2. Why does `is_read_oriented` return `False` for bare `Bash` but `True` for
   `Bash(git diff:*)`?
3. What does `context: fork` buy beyond token savings? Describe the failure mode
   without it.
4. Why is `WebFetch` in `_WRITE_CAPABLE_TOOLS` when it doesn't write files?
5. You add `@.claude/standards/security.md` to `CLAUDE.md` but forget to create the
   file. What does Claude Code do, and what does the validator do?
6. A teammate wants their preferred commit style enforced repo-wide. Which scope, and
   what's the argument if they push back?
