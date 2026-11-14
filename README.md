# seoa: SEO analyzer

**English** · [Türkçe](README.tr.md)

Enter a website address, get a **scored, evidence-backed** SEO report, then ask an AI anything about it.

Deterministic checks decide the score. The AI only adds commentary, advice and Q&A; it never changes the score. The report states what it measured and what it did not, with the reason.

- **Technical and on-page checks:** title, description, canonical, schema, robots.txt, sitemap, TLS and security headers, JavaScript render gap, AI crawler access.
- **Site analysis:** broken and redirecting links, orphan pages, lab speed (LCP, CLS, FCP), images, indexability, duplicate content.
- **Google data (optional):** Search Console (indexing, queries, rankings), CrUX field data, PageSpeed.
- **Chat:** the AI answers only from this audit's data and cites its sources.
- **History:** compares audits of the same site. Keywords and competitors are saved per site.

> Designed for a single user on `localhost`. There is no authentication; do not expose it to the internet.

## Screenshots

Real output for an audit of `example.org` (site mode, light theme). Speed numbers are lab data from the machine that ran the audit.

**Home**: type an address, pick whole site or a single page.

![Home](docs/screenshots/01-home.png)

**Progress**: the counter and ring follow the real pipeline stages; the line at the top says what is being done right now.

![Progress](docs/screenshots/02-progress.png)

**Overview**: the score, what to look at first, and the eight categories.

![Overview](docs/screenshots/03-overview.png)

**Analysis**: one tab per category, with evidence and how to fix each finding.

![Analysis](docs/screenshots/04-analysis.png)

**Chat**: answers come only from this audit's data, and the chips link to the cited sections.

![Chat](docs/screenshots/05-chat.png)

**Mobile**: the menu moves to a bottom bar and the chat box stays within reach.

<img src="docs/screenshots/06-mobile-overview.png" alt="Mobile overview" width="320">

## Install

Requires **Python 3.11 or newer** and Git.

```bash
git clone https://github.com/Arslanex/seo-analyzer.git
cd seo-analyzer

python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
python -m playwright install chromium  # for JavaScript rendering and screenshots (once)

cp .env.example .env                   # then fill in .env (see below)
```

## Configure (`.env`)

Nothing is required. When something is missing, only the matching section says "not measured" and explains why. The **Settings › Connections** page shows what is ready and lets you test each key with a **Test** button.

| Variable | What it enables | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Summary, advice, E-E-A-T commentary and **Chat** | [console.anthropic.com](https://console.anthropic.com/) |
| `SEOA_GOOGLE_API_KEY` | Real-user speed data (CrUX) and PageSpeed | Google Cloud › Credentials › API key (see below) |
| `SEOA_OPENPAGERANK_KEY` | Domain authority estimate | [keywordseverywhere.com/account/openpagerank](https://keywordseverywhere.com/account/openpagerank) (a free key is tied to one IP address) |
| `SEOA_LLM_MODEL` | Model to use (default `claude-haiku-5-5`) | |
| `SEOA_LLM_BUDGET_USD` | Hard cap on all AI spending of this installation (default 8) | |
| `SEOA_MAX_PAGES` | Sample size of a site audit (default 25) | |
| `SEOA_RENDER` | Set `0` to turn headless rendering off | |
| `SEOA_DATA_DIR` | Where the database and files live (default `./data`) | |

`.env` and the `data/` folder are in `.gitignore`: your keys and Google tokens never enter the repository.

### Google connection

There are two separate things:

1. **A single API key** (for CrUX and PageSpeed; no site ownership needed). In Google Cloud, create a project, enable the *Chrome UX Report API* and the *PageSpeed Insights API*, create a key under **Credentials › Create credentials › API key**, restrict it to those two APIs and put it in `.env` as `SEOA_GOOGLE_API_KEY`.
2. **Search Console** (indexing, queries and rankings of your own sites), connected with read-only OAuth:
   1. Enable the *Google Search Console API* in the same project.
   2. Set up the OAuth consent screen as **External / Testing** and add your own e-mail under *Test users*.
   3. Create an OAuth client of type **Desktop app** and save its JSON as `data/google_client.json`.
   4. Start the app and press **Settings › Connections › Connect with Google**.
   5. The site must have a verified Search Console property in your account (a *Domain* property is easiest).

Details and common errors: [`docs/google-setup.md`](docs/google-setup.md). To see the status from the command line: `python scripts/google_setup_check.py`.

## Use

```bash
python scripts/run_server.py          # http://127.0.0.1:8000
```

Type an address in the browser, pick **Whole site** or **Single page** and press **Analyze**. Progress streams live; when it finishes, the app opens with a left menu:

| Page | What it shows |
|---|---|
| Overview | Score, what to look at first, 8 categories, AI summary |
| Chat | Ask about the report; answers cite their sources |
| Analysis | Category tabs, findings, evidence and how to fix them |
| Search | Search Console, rankings, indexability, visibility signals |
| Competitors | Competitor comparison, domain authority, local SEO |
| Action plan | Fixes grouped into phases, and quick wins |
| History | Difference from the previous audit |
| Settings | Status and tests of each connection |

A printable single-page report: `/audits/<id>/report`.

### Command line and API

```bash
python scripts/run_audit.py https://example.com --mode page --html report.html

curl -s -X POST localhost:8000/v1/audits -H 'content-type: application/json' \
     -d '{"url": "example.com", "mode": "page"}'          # 202 + {"id": ...}
curl -s localhost:8000/v1/audits/<id>/report              # audit.json
curl -s localhost:8000/v1/spend                           # AI spending
```

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

The rules are checked automatically by `tests/architecture`: layer direction, no import cycles, and `domain` knowing no outer layer. The reasoning is in [`docs/adr/0001-layered-architecture.md`](docs/adr/0001-layered-architecture.md). The product design documents (in Turkish) are in [`docs/architecture/`](docs/architecture/README.md).

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

## Security and privacy

- User-supplied addresses go through a single client: private IPs, loopback and metadata addresses are rejected; every redirect and render request is validated.
- Keys live only in `.env`; they are never written to logs, reports or error messages. The Settings page never shows a key back, only whether it is set.
- To report a vulnerability, see [`SECURITY.md`](SECURITY.md).

## Limits

Single user, no authentication, in-process queue and SQLite. Speed is **lab** data (measured from this machine); real-user data needs a CrUX key, and Google has no data for new or low-traffic sites. There is no backlink data. The full list of known limits is in [`CHANGELOG.md`](CHANGELOG.md).

## Contributing and license

See [`CONTRIBUTING.md`](CONTRIBUTING.md). License: [MIT](LICENSE). Some parts are derived from the MIT-licensed [claude-seo](https://github.com/AgriciDaniel/claude-seo); the attribution is in [`NOTICE`](NOTICE).
