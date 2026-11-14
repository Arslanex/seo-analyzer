# Contributing

Thanks for contributing. These steps get your change reviewed quickly.

## Before you start

```bash
pip install -e '.[dev]'
python -m playwright install chromium
```

Before and after a change, all of these must pass:

```bash
ruff check src tests scripts && ruff format --check src tests scripts
mypy
pytest -q
```

## Where does code go?

There are four layers and dependencies only point inward: `presentation → infrastructure → application → domain`.

| You want to add | Where |
|---|---|
| A new check rule (pure, no I/O) | `domain/rules/` (rule, message and test) |
| A new analysis module | `application/analysis/modules/` (`register_module` + `plugin.MODULE_FILES`) |
| A new external service (API, database, browser) | `infrastructure/`; write its interface in `application/ports.py` if needed |
| A new page or endpoint | `presentation/api/routers/` and `presentation/web/templates/` |
| New text | `domain/i18n/` (Turkish and English keys together) |

`tests/architecture` enforces the rules: importing an outer layer fails the test. Concrete classes are wired only in `seoa/bootstrap.py`; inner layers receive their dependencies through the constructor.

## Style and tests

- Type hints are required (`mypy --strict`). Add an abstraction only when there is a real need.
- Every behaviour change comes with a test. Tests are deterministic: network, clock and randomness are injected; fakes live in `tests/support/`.
- Put a test in the layer you changed: `tests/unit/<layer>/`.
- Architecture decisions are recorded in `docs/adr/`; if you change the structure, write a new ADR.

## Pull requests

- Keep them small and single-purpose; say what changed and why.
- Add a line under *Unreleased* in `CHANGELOG.md`.
- Do not add secrets (keys, tokens, personal data); `.env` and `data/` are already in `.gitignore`.
