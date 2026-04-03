# AGENTS.md

This repository is a Codex-driven product factory. Every run must convert documentation into small, testable improvements.

## Source of truth

Read these files before changing code:

1. `docs/idea.md`
2. `docs/prd.md`
3. `docs/acceptance.md`
4. `docs/test-plan.md`
5. `docs/tasks.md`
6. `docs/metrics.md`

If the docs and code disagree, prefer the docs and update the code toward the documented behavior.

## Working style

- Keep each run narrow and shippable.
- Prefer one task per run unless the docs show two tasks are tightly coupled.
- Do not invent major features that are not justified by the docs.
- Update `docs/tasks.md` after meaningful progress.
- Update `docs/metrics.md` when you improve performance, coverage, reliability or delivery speed.
- If a task is too large, split it into smaller checklist items in `docs/tasks.md` before implementing.

## Safety rules

- Do not delete large sections of the product unless the docs explicitly call for it.
- Do not change deployment, billing, auth or data model assumptions without documenting the reason in `docs/decision-log.md`.
- Keep dependencies minimal.
- Prefer draft PR quality over speed.

## Expected loop behavior

### Bootstrap

- Read all docs.
- Choose the smallest reasonable stack that satisfies the docs.
- Create the first MVP slice.
- Add missing tasks to `docs/tasks.md`.

### Deliver

- Pick the highest-priority unchecked task from `docs/tasks.md`.
- Implement only that slice.
- Run verification commands from `factory.toml`.

### Autofix

- Read the failing logs.
- Fix only the concrete failure first.
- Avoid broad refactors unless they are required to make tests pass.

### Optimize

- Stay within current product scope.
- Prefer improvements to testing, performance, observability, developer experience and UX polish.
- Record measurable gains in `docs/metrics.md` when possible.

## Done criteria

A run is done only if:

- the code change matches the docs,
- verification commands pass,
- the backlog file reflects the new state,
- and the final summary is accurate about what was or was not completed.
