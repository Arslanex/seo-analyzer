"""Screenshots module (belge 12 A4): desktop and mobile "above the fold" pictures plus a DOM check.

The page is loaded in a guarded browser context (``Renderer.open_page``: every request is judged
by the SSRF policy, same guard as ``render.perf``), once per device (two loads). The picture is the
viewport only (1366x768 desktop, 390x844 at device pixel ratio 2 mobile), saved as JPEG (quality
lowered until it fits ``MAX_BYTES``) with ``inp.save_file``.

Above-the-fold DOM facts are heuristics: "main action" is a button or a link that looks like a
button (class contains btn/button/cta, or role=button), the overlay test looks at fixed/sticky
elements that cover more than 30% of the viewport. Pages that load such layers late (after our
~1 s wait) are not seen. This is a lab view from this machine, not what every visitor sees.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, Field

from seoa.application.analysis.plugin import AnalysisInputs, ModuleResult, register_module
from seoa.application.ports import RenderUnavailable
from seoa.domain import Category, Finding, NotChecked, Severity
from seoa.domain.devices import DESKTOP_VIEWPORT, MOBILE_UA, MOBILE_VIEWPORT
from seoa.domain.rules.registry import CheckDef, make_finding, register, register_messages
from seoa.domain.url_safety import URLSafetyError

KIND = "screenshots"
MOBILE_DPR = 2.0
MAX_BYTES = 400 * 1024
QUALITIES = (70, 55, 40, 28)
OVERLAY_SHARE = 0.30
NAV_TIMEOUT_MS = 20000

Device = Literal["desktop", "mobile"]

_SPECS: dict[str, tuple[Severity, tuple[str, ...]]] = {
    "above-fold-no-h1": (
        Severity.LOW,
        (
            "The H1 heading is not visible in the first screen (above the fold) on desktop or mobile.",
            "H1 başlığı ilk ekranda (ekran üstünde) masaüstünde veya mobilde görünmüyor.",
            "Show the main heading near the top of the page so visitors see at once what the page is about.",
            "Ana başlığı sayfanın üstüne yakın gösterin; ziyaretçi sayfanın ne hakkında olduğunu hemen görsün.",
            "A fresh audit finds the H1 inside the first screen on both devices.",
            "Yeni bir denetim H1'i her iki cihazda da ilk ekranın içinde buluyor.",
            "Bounce rate on mobile and desktop in your analytics.",
            "Analitiğinizde mobil ve masaüstü hemen çıkma oranı.",
        ),
    ),
    "intrusive-interstitial": (
        Severity.MEDIUM,
        (
            "A fixed layer (cookie banner, dialog or pop-up) covers more than 30% of the first screen.",
            "Sabit bir katman (çerez bandı, diyalog veya açılır pencere) ilk ekranın %30'undan fazlasını kaplıyor.",
            "Shrink the banner or turn it into a dismissible bar at the edge; Google may demote pages whose content is hidden by intrusive pop-ups on mobile.",
            "Bandı küçültün veya kenarda kapatılabilir bir çubuğa çevirin; mobilde içeriği kapatan müdahaleci pencereler Google'da sıralamayı düşürebilir.",
            "A fresh audit finds no fixed layer covering more than 30% of the first screen.",
            "Yeni bir denetim ilk ekranın %30'undan fazlasını kaplayan sabit katman bulmuyor.",
            "Mobile usability and page experience reports in Search Console.",
            "Search Console'da mobil kullanılabilirlik ve sayfa deneyimi raporları.",
        ),
    ),
}

for _id, (_sev, _txt) in _SPECS.items():
    register(
        CheckDef(
            id=_id,
            category=Category.TECHNICAL,
            severity=_sev,
            scope="page",
            heuristic=True,
            effort_default="S",
            impact_default="low" if _sev == Severity.LOW else "medium",
            message_key=f"finding.{_id}",
            recommendation_key=f"rec.{_id}",
            failure_check_key=f"fail.{_id}",
            leading_indicator_key=f"lead.{_id}",
            requires=("rendered",),
        )
    )
    register_messages(
        {
            f"finding.{_id}": {"en": _txt[0], "tr": _txt[1]},
            f"rec.{_id}": {"en": _txt[2], "tr": _txt[3]},
            f"fail.{_id}": {"en": _txt[4], "tr": _txt[5]},
            f"lead.{_id}": {"en": _txt[6], "tr": _txt[7]},
        }
    )


class ScreenshotFile(BaseModel):
    device: str
    name: str
    width: int
    height: int
    bytes: int


class AboveFold(BaseModel):
    h1_present: bool = False
    h1_visible: bool = False
    cta_visible: bool = False
    text_chars: int = 0
    horizontal_overflow: bool = False
    overlay_share: float = 0.0
    overlay_label: str = ""


class Screenshots(BaseModel):
    files: list[ScreenshotFile] = Field(default_factory=list)
    above_fold: dict[str, AboveFold] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)


ABOVE_FOLD_JS = """
() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const root = document.documentElement;
  const shown = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'
           && cs.opacity !== '0'; };
  const inView = el => { const r = el.getBoundingClientRect();
    return r.top < vh && r.bottom > 0 && r.left < vw && r.right > 0; };
  const h1s = Array.from(document.querySelectorAll('h1'));
  const h1_visible = h1s.some(h => shown(h) && inView(h));
  const ctaSel = 'button, input[type=submit], input[type=button], [role=button], a[class*=btn], a[class*=button], a[class*=cta]';
  const cta_visible = Array.from(document.querySelectorAll(ctaSel)).slice(0, 500)
    .some(e => shown(e) && inView(e) && (e.textContent || e.value || '').trim().length > 0);
  let chars = 0, nodes = 0;
  const walker = document.createTreeWalker(document.body || root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode() && nodes < 4000) {
    nodes++;
    const t = walker.currentNode.nodeValue.trim(); const el = walker.currentNode.parentElement;
    if (!t || !el || ['SCRIPT','STYLE','NOSCRIPT'].includes(el.tagName)) continue;
    if (shown(el) && inView(el)) chars += t.length;
  }
  let best = 0, label = '';
  for (const el of Array.from(document.querySelectorAll('body *')).slice(0, 4000)) {
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed' && cs.position !== 'sticky') continue;
    if (!shown(el)) continue;
    const r = el.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
    const share = (w * h) / (vw * vh);
    if (share > best) { best = share; label = (el.id || el.getAttribute('role') || el.className || el.tagName).toString().slice(0, 60); }
  }
  return {h1_present: h1s.length > 0, h1_visible, cta_visible, text_chars: chars,
          horizontal_overflow: root.scrollWidth > root.clientWidth + 1,
          overlay_share: Math.round(best * 100) / 100, overlay_label: label};
}
"""


async def _shoot(page: Any) -> bytes:
    data = b""
    for q in QUALITIES:
        data = await page.screenshot(type="jpeg", quality=q, full_page=False)
        if len(data) <= MAX_BYTES:
            break
    return bytes(data)


async def _capture(
    inp: AnalysisInputs, url: str, device: Device
) -> tuple[ScreenshotFile, AboveFold]:
    mobile = device == "mobile"
    viewport = MOBILE_VIEWPORT if mobile else DESKTOP_VIEWPORT
    dpr = MOBILE_DPR if mobile else 1.0
    async with inp.renderer.open_page(
        viewport=viewport,
        mobile=mobile,
        device_scale_factor=dpr,
        user_agent=MOBILE_UA if mobile else None,
        blocked_types=(),
        max_requests=300,
        max_bytes=30 * 1024 * 1024,
    ) as sess:
        page = sess.page
        await page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
        await page.wait_for_timeout(800)
        fold = AboveFold(**await page.evaluate(ABOVE_FOLD_JS))
        data = await _shoot(page)
    name = await inp.save_file(f"{device}.jpg", data)
    return (
        ScreenshotFile(
            device=device,
            name=name,
            width=int(viewport["width"] * dpr),
            height=int(viewport["height"] * dpr),
            bytes=len(data),
        ),
        fold,
    )


def fold_findings(folds: dict[str, AboveFold], url: str) -> list[Finding]:
    out: list[Finding] = []
    no_h1 = [d for d, f in folds.items() if f.h1_present and not f.h1_visible]
    if no_h1:
        out.append(make_finding("above-fold-no-h1", url=url, evidence=", ".join(no_h1)))
    covered = [
        f"{d} {round(f.overlay_share * 100)}% ({f.overlay_label})"
        for d, f in folds.items()
        if f.overlay_share > OVERLAY_SHARE
    ]
    if covered:
        out.append(make_finding("intrusive-interstitial", url=url, evidence="; ".join(covered)))
    return out


class ScreenshotsModule:
    name = "screenshots"
    kind = KIND
    timeout_s = 60.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        url = inp.entry_fetch.final_url or inp.entry_url
        if inp.renderer is None:
            return ModuleResult(
                kind=KIND,
                not_checked=[
                    NotChecked(check_id="screenshots", reason_code="render-unavailable", url=url)
                ],
            )
        try:
            await inp.renderer.judge(url)
        except URLSafetyError:
            return ModuleResult(
                kind=KIND,
                not_checked=[
                    NotChecked(check_id="screenshots", reason_code="target-rejected", url=url)
                ],
            )
        data = Screenshots()
        not_checked: list[NotChecked] = []
        for device in ("desktop", "mobile"):
            try:
                f, fold = await asyncio.wait_for(
                    _capture(inp, url, device),
                    timeout=NAV_TIMEOUT_MS / 1000 + 15,
                )
            except (RenderUnavailable, PlaywrightError, TimeoutError, OSError) as exc:
                data.errors[device] = f"render-failed: {type(exc).__name__}"
                not_checked.append(
                    NotChecked(
                        check_id=f"screenshot-{device}", reason_code="render-failed", url=url
                    )
                )
                continue
            data.files.append(f)
            data.above_fold[device] = fold
        if not data.files:
            return ModuleResult(kind=KIND, data=data, not_checked=not_checked)
        return ModuleResult(
            kind=KIND,
            data=data,
            findings=fold_findings(data.above_fold, url),
            not_checked=not_checked,
        )


register_module(ScreenshotsModule())
