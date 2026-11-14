"""Home page: the audit form, saved keywords, keyword suggestions and audit creation."""

from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)

from seoa.domain import AuditMode
from seoa.domain.i18n import norm_lang, reason_text
from seoa.domain.i18n import t as tr
from seoa.presentation.api.deps import Service, pick_lang
from seoa.presentation.api.schemas import normalize_url, parse_competitors, parse_keywords
from seoa.presentation.api.web_context import (
    GOOGLE_MESSAGES,
    app_ctx,
    google_card,
    key_flags,
    latest_per_site,
)
from seoa.presentation.web.html import render_template

router = APIRouter()


async def _index(
    request: Request,
    service: Service,
    lang: str,
    *,
    error: str | None = None,
    status: int = 200,
    form: dict[str, str] | None = None,
) -> HTMLResponse:
    msg = request.query_params.get("google")
    html = render_template(
        "index.html",
        lang,
        title="SEO Analyzer",
        page="home",
        audits=await service.list_audits(20),
        spend=await service.spend(),
        error=error,
        form_keywords=(form or {}).get("keywords"),
        form_competitors=(form or {}).get("competitors"),
        form_open=bool(error and error != "invalid_url"),
        google=await google_card(request),
        google_msg=msg if msg in GOOGLE_MESSAGES else None,
        sites=latest_per_site(await service.list_audits(60)),
        flags=key_flags(service),
        **await app_ctx(request, lang, active="home", show_side=False),
    )
    return HTMLResponse(html, status_code=status)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, service: Service, lang: str | None = None) -> HTMLResponse:
    return await _index(request, service, pick_lang(request, lang))


@router.get("/ui/profile")
async def ui_profile(service: Service, url: str = "") -> JSONResponse:
    """Saved keywords and competitors of the site in ``url`` (the form pre-fills them)."""
    p = await service.get_profile(url[:2048])
    return JSONResponse(
        {"keywords": ", ".join(p["keywords"]), "competitors": "\n".join(p["competitors"])},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/ui/suggest-keywords")
async def ui_suggest_keywords(
    service: Service, request: Request, url: str = "", lang: str | None = None
) -> JSONResponse:
    """The site's own top Search Console queries, offered as keyword suggestions."""
    lg = pick_lang(request, lang)
    try:
        site = normalize_url(url[:2048])
    except ValueError:
        return JSONResponse(
            {"status": "bad-url", "message": tr(lg, "home.suggest.need_url"), "keywords": []}
        )
    res = await service.suggest_keywords(site)
    status = res["status"]
    if status == "ok":
        message = tr(lg, "home.suggest.hint")
    elif status == "empty":
        message = tr(lg, "home.suggest.empty")
    else:
        message = reason_text(lg, f"gsc-{status}")
    return JSONResponse(
        {"status": status, "message": message, "keywords": res["keywords"]},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/ui/audits", response_model=None)
async def ui_create(request: Request, service: Service) -> Response:
    raw = (await request.body())[:8192].decode("utf-8", "replace")
    form = {k: v[0] for k, v in parse_qs(raw).items() if v}
    lang = norm_lang(form.get("lang"))
    mode = AuditMode.PAGE if form.get("mode") == "page" else AuditMode.SITE
    try:
        url = normalize_url(form.get("url", ""))
    except ValueError:
        return await _index(request, service, lang, error="invalid_url", status=422)
    try:
        keywords = parse_keywords(form.get("keywords", ""))
        competitors = parse_competitors(form.get("competitors", ""))
    except ValueError as exc:
        return await _index(request, service, lang, error=str(exc), status=422, form=form)
    audit_id = await service.create_audit(
        url,
        mode,
        enable_llm=form.get("enable_llm") == "1",
        lang=lang,
        keywords=keywords,
        competitors=competitors,
    )
    await service.save_profile(url, keywords, competitors)  # the form shows them next time
    return RedirectResponse(f"/audits/{audit_id}?lang={lang}", status_code=303)
