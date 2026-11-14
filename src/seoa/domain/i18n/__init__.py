"""Localized texts (TR + EN): ``t(lang, key)``, language normalisation and reason sentences."""

from seoa.domain.i18n.catalog import CATALOG, missing_keys, norm_lang, reason_text, t

__all__ = ["CATALOG", "missing_keys", "norm_lang", "reason_text", "t"]
