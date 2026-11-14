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

## Install

Requires **Python 3.11 or newer** and Git.

```bash
git clone https://github.com/Arslanex/seo-analyzer.git
cd seo-analyzer

python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
python -m playwright install chromium  # for JavaScript rendering and screenshots (once)

cp .env.example .env                   # optional: add keys (see docs/configuration.md)
```

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

## More documentation

- [Configuration](docs/configuration.md): all settings and the Google connection
- [Google setup](docs/google-setup.md): Search Console step by step
- [Development and architecture](docs/development.md): code layout, tests, how to extend
- [Security and limits](docs/security-and-limits.md): what is protected, what is not
- [Decisions](docs/adr/README.md): architecture decision records

[Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [Security policy](SECURITY.md) · License: [MIT](LICENSE) (see [NOTICE](NOTICE) for attribution)

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
