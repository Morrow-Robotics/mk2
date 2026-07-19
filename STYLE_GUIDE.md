# Style Guide

This repo borrows its taste from three codebases: **PyTorch**, **openpilot**, and
**tinygrad**. Each contributes one core idea. When they conflict, the order of
precedence is: **correct → simple → small → fast**.

- **tinygrad** — *radical smallness*. Every line is a liability. The best diff is
  a deletion. Abstractions must pay rent.
- **openpilot** — *pragmatic robustness*. Code runs in the real world. Prefer the
  boring, obvious thing that works over the clever thing that impresses.
- **PyTorch** — *a humane API*. The surface a person touches should be obvious,
  documented, and hard to misuse, even if the internals are gnarly.

---

## 1. Smallness is a feature (tinygrad)

- **Delete before you add.** The first question for any change is "can this be
  done by removing code instead?" A PR that removes lines and keeps behavior is
  always welcome.
- **No speculative abstraction.** Do not add a base class, a config flag, a
  plugin hook, or a layer of indirection for a use case that does not exist yet.
  Write the concrete thing. Abstract on the *third* copy, not the first.
- **Line count is a proxy for complexity.** If a function is getting long, the
  problem is usually the design, not the formatting. Fewer, denser, well-named
  lines beat many shallow ones — but never at the cost of readability (see §3).
- **Kill dead code on sight.** Commented-out blocks, unused params, "might need
  this later" helpers — delete them. Git remembers.
- **Every dependency is a debt.** Adding a third-party package needs a reason you
  could defend out loud. The stdlib is usually enough.

## 2. Make it work in the real world (openpilot)

- **Boring beats clever.** The reader should never have to decode a trick. If
  there is a straightforward way and a slick way that are equally correct, ship
  the straightforward one.
- **Fail loud, fail early.** Validate inputs at the boundary and assert your
  assumptions. A crash with a clear message beats silent corruption downstream.
- **No magic.** Avoid metaclass tricks, monkeypatching, deep decorators, and
  action-at-a-distance. Behavior should be traceable by reading top to bottom.
- **Real inputs, real tests.** Test against data shaped like production, not
  toy fixtures that dodge the hard cases. If a bug happened once, it gets a test.
- **Determinism where it matters.** Seed randomness, pin versions, avoid
  wall-clock and global mutable state in anything that needs to reproduce.
- **Measure before optimizing.** No performance change without a number that
  proves it helped.

## 3. The API is the product (PyTorch)

- **Design the call site first.** Write the code that *uses* the thing before you
  write the thing. If the call site is ugly, the design is wrong.
- **Obvious over configurable.** Sensible defaults so the common path is one line.
  Push knobs to keyword arguments, not required parameters.
- **Hard to misuse.** Make illegal states unrepresentable. Prefer explicit types
  and clear errors over docstrings that beg the user to be careful.
- **Document the public surface.** Anything exported gets a docstring: what it
  does, its args, its shapes/units, and one example. Internals can be terse.
- **Names carry weight.** A good name removes the need for a comment. Say what a
  thing *is* or *does*, not how it is implemented.

---

## Concrete conventions

These are the defaults. Deviate only with a reason worth a comment.

**Layout**
- Public API lives at the package top level and is explicit in `__init__.py`.
  Internals live in submodules and are not re-exported.
- One concept per file. If a file needs section-header comments to navigate, it
  is probably two files.

**Functions & types**
- Functions do one thing. If you need "and" to describe it, split it.
- Type-annotate public signatures. Annotate internals when the type isn't obvious.
- Return early. Prefer flat guard clauses over nested `if`/`else` pyramids.
- No mutable default arguments. No hidden global state.

**Comments**
- Comment *why*, not *what*. The code says what. If a line needs a "what"
  comment, rename things until it doesn't.
- A comment that explains a non-obvious constraint, unit, or gotcha is gold.
  A comment that restates the code is noise — delete it.

**Errors**
- Raise specific exceptions with messages that say what was expected and what
  was received. No bare `except:`. No swallowing errors to keep going.

**Tests**
- Every bug fix ships with a test that fails without the fix.
- Tests are readable top-to-bottom: arrange, act, assert. No cleverness in tests.

**Style mechanics**
- Formatting is not a matter of opinion — it is delegated to the formatter/linter
  and never argued about in review. Run it before you commit.
- Imports: stdlib, third-party, local — three groups, alphabetized within each.

---

## The review test

Before opening a PR, ask:

1. **Could this be smaller?** (tinygrad) — Did I add abstraction I don't need yet?
2. **Will this survive contact with reality?** (openpilot) — Bad input, edge
   cases, reproducibility?
3. **Is the call site something I'd be happy to hand a stranger?** (PyTorch)

If all three are yes, ship it.
