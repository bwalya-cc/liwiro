# Skill: Versa Syntax Validation

## Purpose
Produce and repair valid Versa source for VI so generated drafts respect the current language syntax and runtime conventions.

## Best-Suited Agent
Kalulu

## Inputs
- requested script behavior
- existing Versa source
- VI Portal context
- runtime or parser errors
- module/import requirements

## Procedure
1. Keep the file extension as .versa.
2. Use `#` for single-line comments; never use `//`.
3. Assign a meaningful saveable path such as `scratch/<slug>.versa` when the request does not provide one.
4. Keep imports and module usage aligned with current Verun module names and behavior.
5. Treat `verun/vi/versa-wiki/versa-reference.json` as the canonical syntax reference and `verun/vi/versa-wiki/index.html` as the human-friendly companion.
6. Before writing or repairing a script, read the canonical reference sections for every construct used in the full script: comments, strings/interpolation, declarations, collections, ranges/comprehensions, control flow, functions/lambdas/classes, imports/modules, builtins, and runtime globals.
7. Respect the semicolon expectations, interpolation rules, control-flow syntax, import forms, runtime surfaces, and mistakes catalog from that canonical reference before consulting older Markdown notes.
8. Prefer runnable examples over pseudo-code.
9. During validate-fix loops, do not only chase the reported line. Re-check the whole script against the canonical JSON on every pass.
10. If the canonical reference does not document a needed construct, module, or pattern, say that explicitly to the user instead of inventing syntax.
11. Use the strict VI parser gate before presenting a draft as ready whenever the platform makes it available.
12. Point the user to the Versa reference or VI Portal manual when that helps them follow the rule.

## Output Format
- concise implementation summary
- validated Versa source draft
- note about what was fixed when repairing invalid syntax
- explicit note when the canonical docs did not cover part of the requested construct set

## Failure Conditions
- invalid comment syntax
- unsupported module names
- missing runnable source
- raw pseudo-code presented as real Versa
- guessed syntax that is not grounded in the canonical Versa reference

## Quality Bar
Drafts must be VI-ready, syntactically current, and specific enough that a user can load or run them without obvious parser errors.
