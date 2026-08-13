# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A personal coding-interview and system-design study repo. It is **not** an application —
there is no package manifest, build system, test runner, linter, or CI. It's a growing
collection of standalone scripts and study notes used to practice for technical interviews.

## Running code

There is no project-wide entry point or dependency list. Every script is self-contained
(standard library only) and is run directly:

```bash
python3 day23.py
python3 DynamicProgramming/dp2.py
python3 TopologicalSorting/solutions/CourseSchedule.py
```

There are no automated tests. "Verification" is done by eyeballing a script's own
`print(...)` output against the expected result written in a trailing comment (see
Conventions below) — there is no assertion-based harness to run.

Two caveats when executing existing files, both pre-existing quirks rather than bugs to
"fix" unless the user asks:

- **Python 2-era syntax in some `dayN.py` files** — bare `print x` statements and `is`
  used for value comparison instead of `==`. These will raise `SyntaxError`/behave
  incorrectly under the Python 3.11 interpreter available in this environment. Check a
  file's syntax before assuming it runs as-is.
- **LeetCode-style solutions under `TopologicalSorting/solutions/`** are pasted in the
  form LeetCode provides them, which assumes `List`, etc. are already imported. Most of
  these files do not include `from typing import List` themselves, so they aren't
  standalone-executable without adding that import first.

## Repository structure

- **`dayN.py`** (root, `day1.py`–`day48.py`) — a chronological log of daily interview
  problems (originally from a "Daily Interview Pro" email series). Each file follows a
  fixed shape (see Conventions).
- **`DynamicProgramming/`** — flat collection of standalone DP problem scripts
  (`dp1.py`, `dp2.py`, ...), same self-contained/comment-header style as the root
  `dayN.py` files but scoped to one topic.
- **`TopologicalSorting/`** — a self-contained **study kit**, and the reference pattern
  to imitate if asked to build a similar kit for another topic:
  - `README.md` — index and suggested read order.
  - `Guide.md` — full concept writeup with algorithms and code.
  - `Cheatsheet.md` — condensed quick-reference.
  - `Practice_Problems.md` — tiered LeetCode problem list with a checklist.
  - `solutions/` — one file per solved problem, named after the problem
    (e.g. `CourseSchedule.py`), containing the problem statement/examples as a comment
    header followed by the `class Solution:` implementation.
- **`SystemDesign/`** — numbered curriculum of standalone markdown notes, one concept per
  file, grouped into numbered topic folders read in order:
  `01-fundamentals/` → `02-core-components/` → `03-databases/` →
  `04-distributed-systems/` → `05-architecture-patterns/` →
  `06-reliability-and-resilience/`. Files within a folder are numbered in intended
  reading order (`01-...md`, `02-...md`, ...).
- **`50-Coding-Interview-Questions.pdf`**, **`Algorithms.docx`** — static reference
  material, not generated or consumed by any script.

## Conventions

When adding a new interview-problem script (root `dayN.py` / `DynamicProgramming/dpN.py`
style), match the existing shape:

1. A comment header with the problem statement/source (for `dayN.py` files this includes
   the original email metadata: Subject, From, Sent date, Asked by; a worked
   Input/Output/Explanation example; and a source link).
2. The implementation.
3. Inline calls that exercise the implementation with `print(...)`, followed by a comment
   showing the expected output right after each print — this comment is the only
   correctness check, so keep it accurate.

When adding a solved problem to `TopologicalSorting/solutions/` (or a similarly
structured future kit), follow that folder's existing format: a comment header with the
problem name/difficulty/pattern, a link, a few worked Input/Output examples, then the
`class Solution:` body — and check off the corresponding entry in that kit's
`Practice_Problems.md`.

When adding a new `SystemDesign/` note, match the existing files: a single focused
concept per file, numbered to fit its place in the folder's reading order.
