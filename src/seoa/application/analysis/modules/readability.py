"""Content language module (belge 12 A5): readability, top terms, target keyword audit.

Pure computation over the entry page's main text (``analysis.textstats`` documents the limits:
no Turkish stemming, heuristic syllables). The numbers are descriptive; every finding here is
either a plain presence check (keyword missing in title/H1/description) or a heuristic
(``readability-hard``, ``long-sentences``, ``keyword-stuffing``).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from seoa.application.analysis.modules.textstats import (
    count_phrase,
    display_forms,
    is_very_difficult,
    parse_keywords,
    readability,
    show,
    stopwords,
    supported_language,
    tokens,
    top_terms,
)
from seoa.application.analysis.plugin import AnalysisInputs, ModuleResult, register_module
from seoa.domain import Category, Finding, NotChecked, Severity
from seoa.domain.rules.registry import CheckDef, make_finding, register, register_messages

KIND = "readability"
STUFFING_PERCENT = 3.0
LONG_SENTENCE_SHARE = 0.30
MIN_WORDS = 50  # below this a readability score says nothing

# id -> (severity, heuristic, EN finding, TR finding, EN rec, TR rec, EN fail, TR fail, EN lead, TR lead)
_SPECS: dict[str, tuple[Severity, bool, tuple[str, ...]]] = {
    "readability-hard": (
        Severity.LOW,
        True,
        (
            "The text is very difficult to read by the Flesch / Atesman score (long sentences and long words).",
            "Metin Flesch / Ateşman puanına göre okunması çok zor (uzun cümleler ve uzun kelimeler).",
            "Use shorter sentences and plainer words; split long paragraphs. Aim for the level of your audience.",
            "Daha kısa cümleler ve sade kelimeler kullanın; uzun paragrafları bölün. Hedef kitlenizin düzeyini gözetin.",
            "A fresh audit shows a readability score above the 'very difficult' range.",
            "Yeni bir denetim okunabilirlik puanını 'çok zor' aralığının üstünde gösteriyor.",
            "Time on page and scroll depth in your analytics.",
            "Analitiğinizde sayfada geçirilen süre ve kaydırma derinliği.",
        ),
    ),
    "long-sentences": (
        Severity.LOW,
        True,
        (
            "More than 30% of the sentences are longer than 25 words.",
            "Cümlelerin %30'undan fazlası 25 kelimeden uzun.",
            "Split the longest sentences; one idea per sentence reads better.",
            "En uzun cümleleri bölün; cümle başına tek fikir daha rahat okunur.",
            "A fresh audit shows fewer sentences above 25 words.",
            "Yeni bir denetim 25 kelimeyi aşan daha az cümle gösteriyor.",
            "Bounce rate and time on page of this page.",
            "Bu sayfanın hemen çıkma oranı ve sayfada geçirilen süre.",
        ),
    ),
    "keyword-missing-in-title": (
        Severity.MEDIUM,
        False,
        (
            "A target keyword you gave does not appear in the title tag.",
            "Verdiğiniz hedef anahtar kelime title etiketinde geçmiyor.",
            "Work the keyword (or a close variant that keeps its words) into the title, near the start.",
            "Anahtar kelimeyi (veya kelimelerini koruyan yakın bir biçimini) title içine, tercihen başa yakın ekleyin.",
            "A fresh audit finds the keyword in the title.",
            "Yeni bir denetim anahtar kelimeyi title içinde buluyor.",
            "Impressions and average position for the keyword in Search Console.",
            "Search Console'da kelime için gösterim ve ortalama konum.",
        ),
    ),
    "keyword-missing-in-h1": (
        Severity.MEDIUM,
        False,
        (
            "A target keyword you gave does not appear in the H1 heading.",
            "Verdiğiniz hedef anahtar kelime H1 başlığında geçmiyor.",
            "Make the H1 describe the page's topic using the keyword naturally.",
            "H1'i, anahtar kelimeyi doğal biçimde kullanarak sayfanın konusunu anlatacak şekilde yazın.",
            "A fresh audit finds the keyword in the H1.",
            "Yeni bir denetim anahtar kelimeyi H1 içinde buluyor.",
            "Impressions and average position for the keyword in Search Console.",
            "Search Console'da kelime için gösterim ve ortalama konum.",
        ),
    ),
    "keyword-missing-in-description": (
        Severity.LOW,
        False,
        (
            "A target keyword you gave does not appear in the meta description.",
            "Verdiğiniz hedef anahtar kelime meta açıklamada geçmiyor.",
            "Mention the keyword in the description; Google bolds matching words in the snippet.",
            "Anahtar kelimeyi açıklamada geçirin; Google eşleşen kelimeleri snippet'te kalın gösterir.",
            "A fresh audit finds the keyword in the meta description.",
            "Yeni bir denetim anahtar kelimeyi meta açıklamada buluyor.",
            "Click-through rate for the keyword in Search Console.",
            "Search Console'da kelime için tıklama oranı.",
        ),
    ),
    "keyword-stuffing": (
        Severity.LOW,
        True,
        (
            "A target keyword makes up more than 3% of the words. Google publishes no density rule; this is a readability warning.",
            "Hedef anahtar kelime kelimelerin %3'ünden fazlasını oluşturuyor. Google bir yoğunluk kuralı yayınlamıyor; bu bir okunabilirlik uyarısıdır.",
            "Reword the text so the keyword reads naturally; use synonyms and related terms.",
            "Metni kelime doğal okunacak şekilde yeniden yazın; eş anlamlı ve ilişkili terimler kullanın.",
            "A fresh audit shows the keyword density below 3%.",
            "Yeni bir denetim anahtar kelime yoğunluğunu %3'ün altında gösteriyor.",
            "Time on page and manual read-through.",
            "Sayfada geçirilen süre ve elle okuma.",
        ),
    ),
}

for _id, (_sev, _heur, _txt) in _SPECS.items():
    register(
        CheckDef(
            id=_id,
            category=Category.CONTENT,
            severity=_sev,
            scope="page",
            heuristic=_heur,
            effort_default="M" if _id in ("readability-hard", "long-sentences") else "S",
            impact_default="low" if _sev == Severity.LOW else "medium",
            message_key=f"finding.{_id}",
            recommendation_key=f"rec.{_id}",
            failure_check_key=f"fail.{_id}",
            leading_indicator_key=f"lead.{_id}",
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


class KeywordCheck(BaseModel):
    keyword: str
    in_title: bool
    in_h1: bool
    in_description: bool
    in_url: bool
    in_first_100_words: bool
    in_subheadings: bool
    occurrences: int
    density_percent: float


class ReadabilityData(BaseModel):
    language: str | None = None
    readability: dict[str, Any] | None = None
    terms: list[dict[str, Any]] = Field(default_factory=list)
    phrases: list[dict[str, Any]] = Field(default_factory=list)
    title_terms: list[dict[str, Any]] = Field(
        default_factory=list
    )  # top terms also in title/H1/desc
    keywords: list[KeywordCheck] = Field(default_factory=list)
    suggested_targets: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _url_tokens(url: str) -> list[str]:
    return tokens(re.sub(r"[-_/.+%]", " ", url))


def check_keyword(
    keyword: str,
    *,
    body: list[str],
    title: str,
    h1: list[str],
    description: str,
    url: str,
    subheadings: list[str],
) -> KeywordCheck:
    phrase = tokens(keyword)
    n = len(phrase)
    count = count_phrase(body, phrase)
    density = round(100 * count * n / len(body), 2) if body and n else 0.0
    return KeywordCheck(
        keyword=keyword,
        in_title=count_phrase(tokens(title), phrase) > 0,
        in_h1=any(count_phrase(tokens(h), phrase) > 0 for h in h1),
        in_description=count_phrase(tokens(description), phrase) > 0,
        in_url=count_phrase(_url_tokens(url), phrase) > 0,
        in_first_100_words=count_phrase(body[:100], phrase) > 0,
        in_subheadings=any(count_phrase(tokens(h), phrase) > 0 for h in subheadings),
        occurrences=count,
        density_percent=density,
    )


def analyze(
    *,
    text: str,
    lang: str | None,
    title: str,
    h1: list[str],
    description: str,
    outline: list[tuple[int, str]],
    url: str,
    keywords: list[str],
) -> tuple[ReadabilityData, list[Finding], list[NotChecked]]:
    data = ReadabilityData(language=lang)
    findings: list[Finding] = []
    not_checked: list[NotChecked] = []
    body = tokens(text)
    code = supported_language(lang)

    if code is None:
        not_checked.append(
            NotChecked(check_id="readability", reason_code="language-unsupported", url=url)
        )
    elif len(body) < MIN_WORDS:
        not_checked.append(
            NotChecked(check_id="readability", reason_code="too-little-text", url=url)
        )
    else:
        r = readability(text, code)
        data.readability = r
        if r:
            if is_very_difficult(r):
                findings.append(
                    make_finding(
                        "readability-hard", url=url, evidence=f"{r['formula']} {r['score']}"
                    )
                )
            if r["long_sentence_share"] > LONG_SENTENCE_SHARE:
                findings.append(
                    make_finding(
                        "long-sentences",
                        url=url,
                        evidence=f"{round(r['long_sentence_share'] * 100)}% of sentences > 25 words",
                    )
                )

    stop = stopwords(lang)
    tt = top_terms(body, stop)
    data.terms, data.phrases = tt["terms"], tt["phrases"]
    head_tokens = set(tokens(" ".join([title, *h1, description])))
    data.title_terms = [t for t in data.terms if t["term"] in head_tokens]
    forms = display_forms(text)  # matching uses folded tokens; the report shows real spellings
    for row in (*data.terms, *data.phrases):  # title_terms shares the rows of data.terms
        row["term"] = show(row["term"], forms)

    if not keywords:
        not_checked.append(
            NotChecked(check_id="keyword-targeting", reason_code="no-keywords", url=url)
        )
        data.suggested_targets = [p["term"] for p in data.phrases[:3]] or [
            t["term"] for t in data.terms[:3]
        ]
        return data, findings, not_checked

    subheadings = [t for lvl, t in outline if lvl in (2, 3)]
    for kw in keywords:
        if not tokens(kw):
            continue
        kc = check_keyword(
            kw,
            body=body,
            title=title,
            h1=h1,
            description=description,
            url=url,
            subheadings=subheadings,
        )
        data.keywords.append(kc)
        if not kc.in_title:
            findings.append(make_finding("keyword-missing-in-title", url=url, evidence=kw))
        if not kc.in_h1:
            findings.append(make_finding("keyword-missing-in-h1", url=url, evidence=kw))
        if description and not kc.in_description:
            findings.append(make_finding("keyword-missing-in-description", url=url, evidence=kw))
        if kc.density_percent > STUFFING_PERCENT:
            findings.append(
                make_finding("keyword-stuffing", url=url, evidence=f"{kw}: {kc.density_percent}%")
            )
    return data, findings, not_checked


class ReadabilityModule:
    name = "readability"
    kind = KIND
    timeout_s = 20.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        p = inp.entry_parsed
        if p is None:
            return ModuleResult(
                kind=KIND,
                not_checked=[
                    NotChecked(
                        check_id="readability", reason_code="parse-failed", url=inp.entry_url
                    )
                ],
            )
        text = p.main_text or p.visible_text or ""
        data, findings, nc = analyze(
            text=text,
            lang=inp.lang or p.lang or None,
            title=p.title,
            h1=list(p.h1),
            description=p.meta_description,
            outline=list(p.outline),
            url=inp.entry_url,
            keywords=parse_keywords(inp.options.get("keywords")),
        )
        return ModuleResult(kind=KIND, data=data, findings=findings, not_checked=nc)


register_module(ReadabilityModule())
