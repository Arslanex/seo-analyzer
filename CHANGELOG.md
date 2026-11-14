# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-14

First public release.

### Added

- **Safe fetching:** user-supplied addresses go through a single SSRF-safe client. Private, loopback and metadata addresses are rejected; every redirect hop and DNS resolution is validated separately.
- **Deterministic checks:** page checks, TLS and header checks, robots.txt (RFC 9309), AI crawler access, sitemap discovery, schema, JavaScript render gap.
- **Site analysis:** link graph (broken, redirecting and orphan links, click depth), lab performance (LCP, CLS, FCP, weight, compression, caching, third parties, mobile), image analysis, indexability table, duplicate content.
- **Score v2:** a category score is the severity-weighted share of applicable checks that passed. Gates (noindex, TLS, 4xx), coverage, confidence and a "what this score does not measure" box.
- **Analysis modules:** technology detection, site setup, search and social previews, screenshots, readability and keyword audit (Turkish and English), hreflang, schema suggestions, agent readiness, competitor comparison, local SEO, sitemap suggestion, domain authority.
- **Google connections:** read-only Search Console (indexing, queries, rankings, sitemaps), CrUX field data, PageSpeed Insights. Keyword suggestions from a site's own Search Console queries.
- **AI layer (never scored):** E-E-A-T signals with verified quotes, AI-readiness commentary, summary and advice, Q&A that cites its sources. A persistent spending ledger and cap.
- **History and comparison:** the difference between audits of the same site. Keywords and competitors saved per site.
- **Interface:** an app with a left menu (Overview, Chat, Analysis tabs, Search, Competitors, Action plan, History, Settings), a progress screen that counts up and lists the steps, a mobile bottom bar, dark theme, Turkish and English. Live tests of each key in Settings.
- **Architecture:** a four-layer layout (`domain`, `application`, `infrastructure`, `presentation`), a composition root (`seoa.bootstrap`) and tests that enforce the layer directions (`tests/architecture`).
- **Repository:** `LICENSE`, `NOTICE`, `CONTRIBUTING.md`, `SECURITY.md` and architecture decision records (`docs/adr`).

### Known limits

- Designed for a single user, without authentication, on `localhost` only.
- OpenPageRank moved to Keywords Everywhere; keys from the old service no longer work and a new key is needed.
- While the Search Console OAuth app is in "Testing" mode, the connection expires after 7 days.
- There is no backlink data (no reliable free source).

[Unreleased]: https://github.com/Arslanex/seo-analyzer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Arslanex/seo-analyzer/releases/tag/v0.1.0
