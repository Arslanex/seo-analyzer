from __future__ import annotations

from seoa.infrastructure.llm.known_facts import load_prompt, scan_known_wrong
from seoa.infrastructure.llm.validators import norm, unknown_numbers, verify_quote

TEXT = "Ben bu yöntemi 12 yıldır İstanbul'da uyguluyorum. Müşterilerimizin %40'ı geri döndü."


def test_quote_bounds() -> None:
    assert verify_quote("bu yöntemi 12 yıldır", TEXT)
    assert not verify_quote("kısa", "kısa")  # < 12 chars
    assert not verify_quote("x" * 201, "x" * 300)  # > 200 chars
    assert not verify_quote(None, TEXT) and not verify_quote("", TEXT)


def test_quote_must_exist_verbatim() -> None:
    assert not verify_quote("bu yöntemi 15 yıldır", TEXT)  # one number changed
    assert not verify_quote("tamamen uydurulmuş bir cümle burada", TEXT)


def test_turkish_dotted_dotless_i() -> None:
    assert verify_quote("ISTANBUL'DA UYGULUYORUM", TEXT)  # model upper-cased, I vs İ
    assert verify_quote("İstanbul'da uyguluyorum", TEXT.replace("İ", "I"))
    assert norm("İI ıi") == norm("ii ii")


def test_whitespace_and_quote_style_tolerated() -> None:
    assert verify_quote("müşterilerimizin   %40'ı geri döndü", TEXT)
    assert verify_quote("Müşterilerimizin %40’ı geri döndü", TEXT)


def test_unknown_numbers_warning() -> None:
    assert unknown_numbers("Score 72 of 100 and 3 issues", "score 72 3 issues") == ["100"]


def test_known_wrong_scan() -> None:
    assert [h.id for h in scan_known_wrong("Improve FID by deferring scripts")] == ["fid-current"]
    assert scan_known_wrong("You should add HowTo schema to this page")[0].id == "howto-recommend"
    assert scan_known_wrong("GPTBot blocked means ChatGPT Search will not cite you")
    assert not scan_known_wrong(
        "INP is the interactivity metric. HowTo rich results were deprecated."
    )


def test_prompt_compiles_with_shared_blocks_and_version() -> None:
    p = load_prompt(
        "eeat",
        page_type="article",
        lang="en",
        facts_json="{}",
        signal_catalog="E1 ...",
        output_language="tr",
    )
    assert (
        "untrusted_page_content" in p.text
        and "Write all free-text fields" in p.text
        and "in tr" in p.text
    )
    assert "{{" not in p.text and "{output_language}" not in p.text
    assert p.version.startswith("eeat-") and p.version == load_prompt("eeat").version
