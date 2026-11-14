# Development and architecture

**English** · [Türkçe](development.tr.md)

## Architecture

The code has four layers. **Dependencies only point inward**: an inner layer never knows an outer one.

```
presentation  ─▶  infrastructure  ─▶  application  ─▶  domain
 (HTTP, HTML)     (SQLite, HTTP,      (use cases,       (pure rules,
                   browser, LLM,       ports)            models)
                   Google)
```

```
src/seoa/
├── config.py            settings (.env)
├── bootstrap.py         composition root: wires the concrete classes here
├── domain/              pure business rules, no I/O
│   ├── models.py        entities and value objects
│   ├── rules/           rule catalogue and pure page/schema checks
│   ├── scoring/         score computation
│   ├── parsing/         HTML -> ParsedPage
│   ├── i18n/            Turkish and English texts
│   └── urls.py, url_safety.py, text.py, ...
├── application/         use cases
│   ├── ports.py         what the application expects from the outside (Protocols)
│   ├── audit/           pipeline (orchestrator), service, DTOs
│   ├── analysis/        links/, performance/, search_console/, modules/
│   ├── crawl/           discovery, sampling, sitemap
│   ├── site/            robots.txt and AI crawler access
│   └── reporting/       AuditRecord -> AuditReport
├── infrastructure/      the outside world
│   ├── http/            SSRF-safe client, DNS resolver, TLS/header probes
│   ├── persistence/     SQLite
│   ├── llm/             client, budget ledger, agents, prompts
│   ├── integrations/    Google, CrUX, PSI, OpenPageRank, RDAP, Wayback ...
│   ├── rendering/       headless browser
│   └── adapters.py      the single surface the pipeline uses to look outward
└── presentation/
    ├── api/             FastAPI: routers/ (audits, reports, meta, home, audit_pages, settings)
    └── web/             Jinja templates, styles, a small script
```

The rules are checked automatically by `tests/architecture`: layer direction, no import cycles, and `domain` knowing no outer layer. The reasoning is in [`docs/adr/0001-layered-architecture.md`](adr/0001-layered-architecture.md). The product design documents (in Turkish) are in [`docs/architecture/`](architecture/README.md).

**Adding an analysis module:** put a file under `application/analysis/modules/`, register it with `register_module(...)` and add its name to `MODULE_FILES` in `plugin.py`. The report section is read in `application/reporting/`.

## Develop

```bash
pytest -q                    # all tests (no network, no AI needed)
pytest tests/architecture    # layer rules
ruff check src tests scripts && ruff format --check src tests scripts
mypy                         # strict
```

Tests mirror the layers: `tests/unit/{domain,application,infrastructure,presentation}`, end to end in `tests/e2e`.

To exercise the AI agents one by one against the real API (about 0.006 dollars): `python scripts/test_agents.py --agent all --budget 1`.
