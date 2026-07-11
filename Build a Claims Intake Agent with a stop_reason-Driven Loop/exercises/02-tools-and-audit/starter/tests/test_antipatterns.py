"""Anti-pattern audit.

Verifies, by static AST analysis, that the agentic loop does NOT:
- use string-membership tests against text content to drive control flow
- use an integer-literal iteration cap as its primary stopping mechanism
- omit reference to `stop_reason` as the loop-breaking signal

And that the package broadly does not branch on `claim_type` equality
outside of the tool-schema definitions and the cost-estimate module.

Each test parses the relevant file with `ast` and walks the tree. There are
no runtime imports of claims_intake here — the audit is static, so it works
even if loop.py / tools.py do not run end-to-end.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "claims_intake"
LOOP_PY = PKG / "loop.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# ---------------------------------------------------------------------------
# Anti-pattern 1 — no string-membership tests against assistant text in the loop
# ---------------------------------------------------------------------------
def test_no_string_membership_against_text_in_loop() -> None:
    """No `"some_token" in <something>` expressions in loop.py.

    Heuristic: any `ast.Compare` node using `ast.In` whose `left` operand is a
    string `ast.Constant` is flagged. The loop has no legitimate reason to test
    for the presence of a magic string inside the model's output — that would be
    natural-language-driven control flow.
    """
    # `ast.parse` turns source TEXT into a tree of node objects (no code runs —
    # this is static analysis). `ast.walk` yields every node in the tree; we
    # filter with isinstance to the construct we care about.
    #
    # A comparison like `"done" in text` parses to one ast.Compare with fields:
    #   left        = Constant(value="done")   # left-hand operand
    #   ops         = [In()]                    # a LIST: Python allows `a < b < c`
    #   comparators = [Name(id="text")]         # right-hand operand(s)
    # So: is any operator an `In`, AND is `left` a string literal? Both => flag.
    # `ast.unparse` turns a node back into source text, purely for the message.
    tree = _parse(LOOP_PY)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        uses_in = any(isinstance(op, ast.In) for op in node.ops)
        left_is_str_literal = isinstance(node.left, ast.Constant) and isinstance(
            node.left.value, str
        )
        if uses_in and left_is_str_literal:
            offenders.append(ast.unparse(node))

    assert not offenders, (
        "loop.py drives control flow with string-membership tests against literals "
        "(natural-language-driven control flow). Use stop_reason instead. Offenders:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Anti-pattern 2 — no integer-literal iteration cap as the primary stop mechanism
# ---------------------------------------------------------------------------
def test_no_integer_literal_iteration_cap_in_loop() -> None:
    """No `for _ in range(<int literal>)` and no `while <var> < <int literal>` in loop.py.

    Token/wall-clock/config-sourced budgets are explicitly allowed because they
    read their cap from a `Budget` instance (an attribute access or a function
    arg), not from a literal. If you need a cap, pass it in.
    """
    # Each node type has its OWN fields — mixing them up is the #1 ast mistake:
    #   ast.For   -> target (loop var), iter (what you loop over), body
    #   ast.While -> test (the condition), body
    #   ast.Call  -> func (what's called), args (argument nodes)
    # `for _ in range(10)`  => For.iter is a Call whose func is Name("range").
    # `while turn < 10`     => While.test is a Compare with 10 in .comparators.
    # When unsure of a node's fields, run in a REPL:
    #   ast.dump(ast.parse("for _ in range(10): pass"))
    tree = _parse(LOOP_PY)
    offenders: list[str] = []

    def _is_int_literal(node: ast.AST) -> bool:
        # bool is a subclass of int; `while True:` is the legitimate idiom here
        # (the loop exits on stop_reason, not a counter), so exclude bools.
        return (
            isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)
        )

    for node in ast.walk(tree):
        # for _ in range(<int literal>, ...)
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Call):
            func = node.iter.func
            if isinstance(func, ast.Name) and func.id == "range":
                if any(_is_int_literal(arg) for arg in node.iter.args):
                    offenders.append(ast.unparse(node.iter))
        # while <something> < <int literal>  (`while True:` has a bare Constant
        # test, not a Compare, so it never even reaches this branch)
        if isinstance(node, ast.While) and isinstance(node.test, ast.Compare):
            if any(_is_int_literal(comp) for comp in node.test.comparators):
                offenders.append(ast.unparse(node.test))

    assert not offenders, (
        "loop.py uses an integer-literal iteration cap as a stop mechanism. "
        "Use a Budget (token / wall-clock, sourced from config) instead. Offenders:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Positive evidence — stop_reason is the value that breaks the while loop
# ---------------------------------------------------------------------------
def test_stop_reason_is_loop_control() -> None:
    """loop.py references `stop_reason` AND a `while` loop exits via return/raise on it."""
    # Unlike the other tests, this one confirms the RIGHT pattern is present.
    tree = _parse(LOOP_PY)

    # Part 1: some reference to stop_reason. `response.stop_reason` is an
    # ast.Attribute (fields: .value=response, .attr="stop_reason"); a bare local
    # would be an ast.Name (.id="stop_reason"). Accept either form.
    references_stop_reason = any(
        (isinstance(node, ast.Attribute) and node.attr == "stop_reason")
        or (isinstance(node, ast.Name) and node.id == "stop_reason")
        for node in ast.walk(tree)
    )
    assert references_stop_reason, "loop.py never references `stop_reason` at all."

    # Part 2: a while loop whose body ties stop_reason to an exit. Intentionally a
    # LOOSE heuristic (the README's TODO specifies exactly this): unparse the
    # body back to text and check both ingredients co-occur. NB: the substring
    # test below is itself a `"..." in ...` membership check — that's fine because
    # this audit parses loop.py, never its own file.
    while_exits_on_stop_reason = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.While):
            continue
        body_src = "\n".join(ast.unparse(stmt) for stmt in node.body)
        if "stop_reason" in body_src and ("return" in body_src or "raise" in body_src):
            while_exits_on_stop_reason = True
            break

    assert while_exits_on_stop_reason, (
        "No `while` loop in loop.py exits via return/raise driven by `stop_reason`. "
        "The loop's termination must be the model's stop_reason, not anything else."
    )


# ---------------------------------------------------------------------------
# Decision-tree-in-Python — no `if claim_type == "..."` branches in the package
# ---------------------------------------------------------------------------
def test_no_claim_type_equality_branching_in_package() -> None:
    """Decision logic about claim type lives in the model, not in Python.

    tools.py is exempt (it defines the enum in input_schema).
    pricing.py is exempt (it may map claim_type to per-queue cost weights).
    """
    # Same ast.Compare inspection as test 1, but over EVERY .py file in the
    # package (PKG.rglob("*.py")), skipping the exempt ones. We look for the `==`
    # operator (ast.Eq) with `claim_type` on the left as either a Name
    # (`claim_type == "auto"`) or an Attribute (`session.claim_type == "auto"`),
    # compared to a string. node.lineno gives the source line for the report.
    exempt = {"tools.py", "pricing.py", "__init__.py"}
    offenders: list[str] = []

    for path in sorted(PKG.rglob("*.py")):
        if path.name in exempt:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, ast.Eq) for op in node.ops):
                continue
            left = node.left
            left_is_claim_type = (
                isinstance(left, ast.Name) and left.id == "claim_type"
            ) or (isinstance(left, ast.Attribute) and left.attr == "claim_type")
            if not left_is_claim_type:
                continue
            compares_to_str = any(
                isinstance(comp, ast.Constant) and isinstance(comp.value, str)
                for comp in node.comparators
            )
            if compares_to_str:
                offenders.append(f"{path.name}:{node.lineno}: {ast.unparse(node)}")

    assert not offenders, (
        "Decision logic about claim_type belongs in the model via tool calls, not in "
        "Python `==` branches. Move the decision into the model. Offenders:\n  "
        + "\n  ".join(offenders)
    )
