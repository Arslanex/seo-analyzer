"""Server-side HTML (Jinja2, autoescape ON, no ``|safe`` on page-derived data).

The severity map is the single source of truth for colour, shape and label (belge 06 s.9.2): five
distinct tones, five distinct shapes, plus a text label, light and dark.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined, pass_context, select_autoescape
from markupsafe import Markup

from seoa.application.reporting.schema import AuditReport
from seoa.domain import SEVERITY_ORDER
from seoa.domain.i18n import norm_lang, t
from seoa.domain.palette import BAND_STYLES, SEVERITY_STYLES

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def severity_css() -> str:
    def block(mode: str) -> str:
        return "".join(
            f"--sev-{sev.value.lower()}-fg:{SEVERITY_STYLES[sev][mode][0]};"
            f"--sev-{sev.value.lower()}-bg:{SEVERITY_STYLES[sev][mode][1]};"
            for sev in SEVERITY_ORDER
        )

    return (
        f":root{{{block('light')}--band-good:{BAND_STYLES['good']};--band-attention:{BAND_STYLES['attention']};"
        f"--band-poor:{BAND_STYLES['poor']}}}"
        f"@media (prefers-color-scheme: dark){{:root{{{block('dark')}}}}}"
    )


def _fmt_dt(value: datetime | None, lang: str) -> str:
    if value is None:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M") if lang == "tr" else value.strftime("%Y-%m-%d %H:%M")


def _num(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}"


def _ms(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value / 1000:.1f} s" if value >= 1000 else f"{value:.0f} ms"


def _cls(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}".rstrip("0").rstrip(".") or "0"


_TR_MONTHS = ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara")
_EN_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _fmt_dt_long(value: datetime | None, lang: str, *, time: bool = True) -> str:
    """13 Kas 2026 20:56 (tr) / Nov 13, 2026 20:56 (en)."""
    if value is None:
        return "—"
    clock = value.strftime(" %H:%M") if time else ""
    if lang == "tr":
        return f"{value.day} {_TR_MONTHS[value.month - 1]} {value.year}{clock}"
    return f"{_EN_MONTHS[value.month - 1]} {value.day}, {value.year}{clock}"


def _host_of(url: str) -> str:
    return urlparse(url).hostname or url


@pass_context
def _nl(ctx: Any, value: float | None) -> str:
    """Like ``num`` but with the decimal comma Turkish readers expect."""
    text = _num(value)
    return text.replace(".", ",") if ctx.get("lang") == "tr" else text


def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "htm"], default=False, default_for_string=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["num"] = _num
    env.filters["nl"] = _nl
    env.filters["ms"] = _ms
    env.filters["clsfmt"] = _cls
    return env


_ENV = make_env()


def base_context(lang: str, *, title: str, page: str) -> dict[str, Any]:
    lang = norm_lang(lang)
    other = "en" if lang == "tr" else "tr"
    return {
        "lang": lang,
        "other_lang": other,
        "t": lambda key, **p: t(lang, key, **p),
        "title": title,
        "page": page,
        "severity_css": Markup(severity_css()),  # generated from constants above: trusted
        "severity_order": [s.value for s in SEVERITY_ORDER],
        "severity_shape": {s.value: SEVERITY_STYLES[s]["shape"] for s in SEVERITY_ORDER},
        "fmt_dt": lambda v: _fmt_dt(v, lang),
        "fmt_date": lambda v, time=True: _fmt_dt_long(v, lang, time=time),
        "host_of": _host_of,
        # app-shell defaults, so any page renders on its own; routes override them
        "show_side": False,
        "nav_active": "",
        "nav_audit": None,
        "google_connected": None,
        "lang_url": "/",
    }


def render_template(name: str, lang: str, *, title: str, page: str, **ctx: Any) -> str:
    context = base_context(lang, title=title, page=page)
    context.update(ctx)
    return _ENV.get_template(name).render(**context)


def filter_findings(report: AuditReport, severity: str | None, category: str | None) -> list[Any]:
    out = report.findings
    if severity:
        out = [f for f in out if f.severity.value == severity]
    if category:
        out = [f for f in out if f.category.value == category]
    return out


def render_report_html(
    report: AuditReport,
    lang: str | None = None,
    *,
    severity: str | None = None,
    category: str | None = None,
    interactive: bool = True,
) -> str:
    lang = norm_lang(lang or report.audit.locale)
    rec_by_id = {r.id: r for r in report.recommendations}
    shown = filter_findings(report, severity, category)
    title_key = "report.title.page" if report.audit.mode.value == "page" else "report.title.site"
    return render_template(
        "report.html",
        lang,
        title=f"{t(lang, title_key)} · {report.audit.requested_url}",
        page="report",
        report=report,
        findings=shown,
        rec_by_id=rec_by_id,
        sel_severity=severity,
        sel_category=category,
        categories_in_use=sorted({f.category.value for f in report.findings}),
        interactive=interactive,
        only=None,
        is_final=report.audit.status.value in ("completed", "partial", "failed", "canceled"),
        max_urls=10,
    )
