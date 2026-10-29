# Agent rules for this repository

- Small, reviewable commits; one logical change each (Conventional Commits).
- Tests with every behaviour change: `make test` and `make lint` must pass before committing.
- No secrets, `.env`, databases or uploaded files in git.
- Authorization is enforced server-side; never trust model output, document text or tool output.
- All connectors are mock/local. No real external actions without explicit approval.
- Report only what was actually run and observed.
