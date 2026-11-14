"""Site-level rule definitions: transport, robots, AI crawler access, sitemap.

Severity provenance
-------------------
* transport ids and severities are taken unchanged from the upstream project
  ``scripts/transport_check.py`` (``_tls_findings``/``_header_findings``/``_redirect_findings``).
  NOTE: the source rates ``tls-handshake-failed`` and ``tls-cert-not-trusted`` **High**, not
  Critical. Belge 01 s.8.3 caps the score by *id*, so the gate does not depend on severity;
  the severities are kept as in the source.
* robots / AI / sitemap rules have no severity in the source (it reports pass/warn and
  free-text codes). Their severities here are OUR choice and conservative; they are marked
  in ``OWN_SEVERITY`` so calibration (belge 01 s.13.2) knows they are untested guesses.

Importing this module registers every rule in ``seoa.checks.registry``.
"""

from __future__ import annotations

from seoa.domain import Category, Severity
from seoa.domain.rules import messages_site  # noqa: F401  (registers messages)
from seoa.domain.rules.registry import CheckDef, register

T, A = Category.TECHNICAL, Category.AI_READINESS
C, H, M, L, INFO = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFO,
)

# (id, category, severity, heuristic, effort, impact, requires)
_SPECS: tuple[tuple[str, Category, Severity, bool, str, str, tuple[str, ...]], ...] = (
    # --- TLS (source: transport_check) -------------------------------------------------
    ("tls-handshake-failed", T, H, False, "M", "high", ()),
    ("tls-cert-expired", T, C, False, "S", "high", ()),
    ("tls-cert-not-yet-valid", T, C, False, "S", "high", ()),
    ("tls-cert-hostname-mismatch", T, C, False, "S", "high", ()),
    ("tls-cert-not-trusted", T, H, False, "S", "high", ()),
    ("tls-cert-expiring-soon", T, H, False, "S", "medium", ()),
    ("tls-old-protocol", T, M, False, "M", "medium", ()),
    ("tls-sibling-not-covered", T, M, False, "S", "medium", ()),
    # --- redirects (source) -------------------------------------------------------------
    ("http-no-https-redirect", T, H, False, "S", "high", ()),
    ("http-https-redirect-chain", T, L, False, "S", "low", ()),
    ("http-https-redirect-temporary", T, L, False, "S", "low", ()),
    ("www-not-consolidated", T, M, False, "M", "medium", ()),
    ("www-sibling-unreachable", T, INFO, False, "S", "low", ()),
    # --- security headers (source; "security matter, not a confirmed ranking signal") ----
    ("hsts-missing", T, M, True, "S", "medium", ("headers",)),
    ("hsts-disabled", T, M, True, "S", "medium", ("headers",)),
    ("hsts-weak", T, L, True, "S", "low", ("headers",)),
    ("csp-missing", T, L, True, "M", "low", ("headers",)),
    ("csp-report-only", T, L, True, "M", "low", ("headers",)),
    ("csp-weak", T, L, True, "M", "low", ("headers",)),
    ("nosniff-missing", T, L, True, "S", "low", ("headers",)),
    ("clickjacking-protection-missing", T, L, True, "S", "low", ("headers",)),
    ("referrer-policy-missing", T, INFO, True, "S", "low", ("headers",)),
    ("referrer-policy-unsafe", T, L, True, "S", "low", ("headers",)),
    ("permissions-policy-missing", T, INFO, True, "S", "low", ("headers",)),
    ("cookie-missing-secure", T, L, True, "S", "low", ("headers",)),
    ("cookie-missing-httponly", T, INFO, True, "S", "low", ("headers",)),
    ("cookie-missing-samesite", T, INFO, True, "S", "low", ("headers",)),
    # --- robots (OWN severities) ----------------------------------------------------------
    ("robots-missing", T, INFO, False, "S", "low", ("robots",)),
    ("robots-unreachable", T, H, False, "M", "high", ("robots",)),
    ("robots-blocks-site", T, H, False, "S", "high", ("robots",)),
    ("robots-disallows-entry", T, H, False, "S", "high", ("robots",)),
    # --- AI crawler access (OWN severities; category ai_readiness) -----------------------
    ("ai-search-bots-blocked", A, M, False, "S", "medium", ("robots",)),
    ("ai-training-bots-blocked", A, INFO, False, "S", "low", ("robots",)),
    ("llms-txt-missing", A, INFO, True, "S", "low", ()),
    # --- sitemap (OWN severities) ----------------------------------------------------------
    ("sitemap-missing", T, L, False, "M", "medium", ("sitemap",)),
    ("sitemap-invalid", T, M, False, "S", "medium", ("sitemap",)),
    ("sitemap-too-large", T, M, False, "M", "medium", ("sitemap",)),
    ("sitemap-nested-index", T, L, False, "S", "low", ("sitemap",)),
    ("sitemap-invalid-urls", T, L, False, "S", "low", ("sitemap",)),
    ("sitemap-cross-host-urls", T, L, False, "S", "low", ("sitemap",)),
    ("sitemap-duplicate-urls", T, L, False, "S", "low", ("sitemap",)),
    ("sitemap-lastmod-invalid", T, L, False, "S", "low", ("sitemap",)),
    ("sitemap-lastmod-uniform", T, L, True, "S", "low", ("sitemap",)),
    ("sitemap-child-unreachable", T, L, False, "S", "low", ("sitemap",)),
)

OWN_SEVERITY = frozenset(
    spec[0] for spec in _SPECS if spec[0].startswith(("robots-", "ai-", "llms-", "sitemap-"))
)

TLS_RULE_IDS = tuple(s[0] for s in _SPECS if s[0].startswith("tls-"))
REDIRECT_RULE_IDS = tuple(s[0] for s in _SPECS if s[0].startswith(("http-", "www-")))
HEADER_RULE_IDS = tuple(
    s[0]
    for s in _SPECS
    if s[0].startswith(
        ("hsts-", "csp-", "nosniff-", "clickjacking-", "referrer-", "permissions-", "cookie-")
    )
)

for _id, _cat, _sev, _heur, _effort, _impact, _req in _SPECS:
    register(
        CheckDef(
            id=_id,
            category=_cat,
            severity=_sev,
            scope="site",
            heuristic=_heur,
            effort_default=_effort,  # type: ignore[arg-type]
            impact_default=_impact,  # type: ignore[arg-type]
            message_key=f"finding.{_id}",
            recommendation_key=f"rec.{_id}",
            failure_check_key=f"fail.{_id}",
            leading_indicator_key=f"lead.{_id}",
            requires=_req,
        )
    )

SITE_RULE_IDS = tuple(s[0] for s in _SPECS)
