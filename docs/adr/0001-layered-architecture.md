# ADR 0001: Four-layer layout and dependency direction

- **Status:** Accepted (2026-11-14)
- **Supersedes:** none. The earlier layout existed only as a plan in `docs/architecture/08-file-structure.md`; the structure below is what was implemented.

## 1. Architecture analysis (previous state)

`src/seoa` had 15 packages side by side (`analysis` with 32 files, `report`, `checks`, `llm`, `db`, ...). It worked and was well tested, but the structure was hard to read:

| Problem | Evidence |
|---|---|
| No layers: pure rules, use cases and the outside world sat at the same level | `checks` held both the pure rules and the TLS socket code |
| Circular dependencies | `checks ↔ analysis`, `safefetch ↔ crawl`, `db → service`, `llm → service`, `report/deep ↔ history` |
| The rule registry was not a leaf | `checks/__init__` imported `analysis`, `integrations` and `pipeline` modules |
| No composition root | `LocalAuditService` created its own `Repo`, `Fetcher`, `Renderer` and `LLMProvider` |
| One large, multi-purpose file | `api/routes.py` had 1391 lines: JSON API, pages, settings and helpers together |
| Flat test folder | 68 files in `tests/unit`, no grouping by subject |

Strengths (kept): pure, testable check functions, small contracts such as `FetcherLike`, a single SSRF-safe client, a persistent budget ledger, broad tests.

## 2. Decision

The code is split into four layers. **Source dependencies only point inward.**

```
presentation  →  infrastructure  →  application  →  domain
```

| Layer | Responsibility | What it may know |
|---|---|---|
| `domain` | Pure business rules: models, rule catalogue and pure checks, scoring, HTML parsing, URL and SSRF policy, translation catalogs | No outer layer |
| `application` | Use cases: the audit pipeline, analysis modules, discovery, report building, and the **ports** (`ports.py`) | `domain` |
| `infrastructure` | The outside world: SQLite, the SSRF-safe HTTP client, the headless browser, the LLM, Google and third-party APIs. Implements the ports | `domain`, `application` |
| `presentation` | FastAPI routers and Jinja pages | Everything below |

`seoa.config` (settings) and `seoa.bootstrap` (composition root) sit outside the layers. Concrete classes are wired only in `bootstrap`; layers receive their dependencies through constructors.

### Old → new mapping

| Old | New |
|---|---|
| `checks.registry`, `checks.rules_*`, `checks.messages_*`, `checks.page_checks`, `checks.schema_checks` | `domain/rules/` |
| `checks.robots` | `application/site/robots.py` |
| `checks.transport` | `infrastructure/http/transport.py` (opens sockets, does TLS) |
| `checks.__init__.load_all_rules` | `application/rules_loader.py` |
| `scoring`, `parse` | `domain/scoring`, `domain/parsing` |
| `crawl.normalize` | `domain/urls.py`; the rest of `crawl` → `application/crawl` |
| `safefetch.policy` | `domain/url_safety.py`; `fetcher`, `resolver` → `infrastructure/http` |
| `report.i18n*`, `report.textutil` | `domain/i18n/`, `domain/text.py` |
| `report.*` (builders) | `application/reporting/`; `report.html`, templates, static → `presentation/web/` |
| `analysis.*` | `application/analysis/{links,performance,search_console,modules}/` (by feature) |
| `pipeline.orchestrator`, `service.*` | `application/audit/` |
| `pipeline.adapters` | `infrastructure/adapters.py` |
| `db`, `llm`, `integrations`, `render` | `infrastructure/{persistence,llm,integrations,rendering}/` |
| `api` (`routes.py`) | `presentation/api/routers/` (6 modules) + `schemas.py`, `support.py`, `web_context.py` |

## 3. Design pattern decisions

| Pattern | Where | Problem it solves | Class |
|---|---|---|---|
| Dependency Injection (constructor) | `LocalAuditService`, `AuditRunner` | A service creating its own infrastructure; hard to substitute fakes in tests | **Required** (applied) |
| Composition Root | `seoa/bootstrap.py` | Wiring concrete dependencies in one place | **Required** (applied) |
| Port / Adapter | `application/ports.py` (`FetcherLike`, `SearchConsolePort`) and `infrastructure/*` | The application not depending on I/O | **Required** (applied) |
| Repository | `infrastructure/persistence/Repo` | Separating data access from business logic | Applied (concrete class); splitting into small Protocols is **Conditional** |
| Strategy / Registry | `register_module`, the rule registry | Adding a module or rule without touching the core | Applied |
| Facade | `infrastructure/adapters.py` | The one surface the pipeline uses to look outward; a module API change is fixed in one place | Applied |
| Unit of Work, CQRS, Outbox/Saga, event bus | none | One process, one SQLite file, one writer: no need | **Optional** (deliberately not added) |

## 4. Consequences and remaining debt

**Gain:** the location of every file follows from its name; `domain` and `application` can be tested without infrastructure; a new external service goes into `infrastructure`, a new rule into `domain/rules`, a new page into `presentation`.

**Deliberate trade-offs and remaining debt:**

1. `AuditRunner` and `LocalAuditService` take `ops` (the module of pipeline helpers) from the constructor, and its type is `Any`. Writing a small `Protocol` for it is **Conditional**: do it if a function signature changes often.
2. `Repo` is imported only under `if TYPE_CHECKING` (no runtime dependency); a formal `AuditStore` Protocol is **Conditional**.
3. `AuditService` covers only the single-process application (`LocalAuditService`). If the queue or database changes (PostgreSQL, Redis), a separate implementation is added; no port change is needed.
4. The translation catalogs live in `domain/i18n` (treated as part of the report content; no I/O).
5. The older design documents (`docs/architecture/00-12`, in Turkish) mention the previous file names; they describe the product design, not the file paths.

## 5. Risk analysis

| Risk | Impact | Mitigation |
|---|---|---|
| A developer or agent breaks the layer direction | The structure gets tangled again over time | `tests/architecture` is part of the test suite; a violation fails the test |
| A function of the `ops` module disappears | `AttributeError` at runtime | e2e and unit tests use the `ops` functions; the Protocol debt (item 1) |
| Path-dependent resources (templates, prompts, `data/rules`) break when moved | File errors at runtime | Tests read every resource; package data is declared in `pyproject` |
| Concurrency: one SQLite connection, an in-process queue | A bottleneck with many users | The single-user assumption is documented; if it scales, the queue and database change (item 3) |

## 6. Verification criteria

These checks prove the decision is applied:

- `pytest tests/architecture`: layer direction, `domain` independence, no `infrastructure → presentation` import, only entry points using the composition root, **no import cycles between modules**, every layer documented. `KNOWN_DEBT` is empty and can only shrink.
- `ruff check` and `ruff format --check`, `mypy --strict`.
- `pytest`: unit and end-to-end tests.

## 7. Rules for AI coding agents

- New code is placed first by the layer it belongs to (the table in `CONTRIBUTING.md`).
- A change that breaks the layer direction is not made without a reason; if needed, a port is defined first.
- Any work that changes the architecture comes with a new ADR.
- Tasks are kept small and verifiable; the acceptance criterion of each is the three commands above.
