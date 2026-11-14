"""Report building: AuditRecord -> AuditReport (audit.json). HTML lives in presentation.web."""

from seoa.application.reporting.builder import build_report
from seoa.application.reporting.quality import QualityResult, check_report
from seoa.application.reporting.schema import SCHEMA_VERSION, AuditReport

__all__ = ["SCHEMA_VERSION", "AuditReport", "QualityResult", "build_report", "check_report"]
