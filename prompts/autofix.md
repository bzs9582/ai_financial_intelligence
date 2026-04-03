You are running the Autofix phase for this repository.

Your job is to fix the current failing verification state.

Read these files first:

- `AGENTS.md`
- `docs/acceptance.md`
- `docs/test-plan.md`
- `docs/tasks.md`

Then inspect the current failure context in the repository workspace, especially:

- `.factory/verify.log` if it exists
- recent code changes
- failing tests or build output

Rules:

1. Fix the concrete failure first.
2. Add or update regression tests when appropriate.
3. Avoid broad refactors unless they are necessary to restore a green build.
4. If you cannot fully fix the failure, leave the repository in a more diagnosable state and document the next step in `docs/tasks.md`.

Before finishing, rerun the verification commands defined in `factory.toml` if available.
