"""The "what this score does not measure" box: only items this audit really left unmeasured."""

from __future__ import annotations

from seoa.application.reporting import schema as s
from seoa.domain import AuditRecord
from seoa.domain.i18n import t


def _measured_scope_items(rec: AuditRecord) -> set[int]:
    """Scope items 2 (rankings), 4 (keyword targeting) and 6 (rivals), when their data exists."""
    from seoa.application.analysis.modules.readability import ReadabilityData
    from seoa.application.reporting.history import competitors_section
    from seoa.application.reporting.rankings import rankings_section
    from seoa.application.reporting.suite import _load

    done: set[int] = set()
    if rankings_section(rec, "en").status == "measured":
        done.add(2)
    readability = _load(rec, "readability", ReadabilityData)
    if not isinstance(readability, str) and readability.keywords:
        done.add(4)
    if competitors_section(rec, "en").status == "measured":
        done.add(6)
    return done


def scope_note(lang: str, rec: AuditRecord | None = None) -> s.ScopeNote:
    """Items that the audit *did* measure (indexing, rankings, keywords, field data, rivals) go."""
    gsc_ok = rec is not None and rec.gsc is not None and rec.gsc.status == "ok"
    field_ok = rec is not None and rec.field is not None and bool(rec.field.metrics)
    skip = ({1} if gsc_ok else set()) | ({5} if field_ok else set())
    if rec is not None:
        skip |= _measured_scope_items(rec)
    return s.ScopeNote(
        title=t(lang, "scope.title"),
        intro=t(lang, "scope.intro"),
        items=[t(lang, f"scope.i{i}") for i in range(1, 7) if i not in skip],
        next_step=t(lang, "scope.next.connected" if gsc_ok else "scope.next"),
        model_note=t(lang, "scope.model"),
    )
