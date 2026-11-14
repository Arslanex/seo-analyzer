"""Regression: a quote is verified against exactly the text the model was shown."""

from __future__ import annotations

from seoa.infrastructure.llm.input import build_content_input
from seoa.infrastructure.llm.validators import verify_quote

HTML = '<html lang="tr"><body><main><p>Merhaba</p></main><footer><a href="/gizlilik">Gizlilik Politikası</a></footer></body></html>'


def test_envelope_line_quotes_verify_for_turkish_dotless_i() -> None:
    ci = build_content_input(HTML, "https://k.test/", {}, lang="tr", facts={})
    shown = ci.envelope()
    assert "[footer] Gizlilik Politikası -> /gizlilik" in shown
    for quote in (
        "[footer] Gizlilik Politikası -> /gizlilik",
        "Gizlilik Politikası",
        "GİZLİLİK POLİTİKASI",
    ):
        assert verify_quote(quote, ci.field_text("chrome_link")), quote
    assert not verify_quote("Gizlilik Sözleşmesi", ci.field_text("chrome_link"))
