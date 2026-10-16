"""Validation issue model and catalog of issue definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    error = "error"  # blocking: the channel is expected to reject the product
    warning = "warning"  # likely problem or non-documented value
    recommendation = "recommendation"  # optimization opportunity


@dataclass(frozen=True)
class IssueDefinition:
    code: str
    severity: Severity
    title: str
    recommendation: str
    source: str | None = None  # documentation reference backing the check
    suggested_rule: dict | None = None  # rule template the UI can prefill


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    attribute: str | None
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity.value, "attribute": self.attribute, "message": self.message}


SEVERITY_ORDER = {Severity.error: 0, Severity.warning: 1, Severity.recommendation: 2}


def worst(issues: list[Issue]) -> str:
    if not issues:
        return "valid"
    return min(issues, key=lambda i: SEVERITY_ORDER[i.severity]).severity.value
