"""Plain dataclasses used across the app (no heavy dependencies)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Issue:
    severity: str  # critical | high | medium | low
    code: str
    url: str
    message: str
    fix: str = ""


@dataclass
class PageAudit:
    url: str
    status: int = 200
    title: str = ""
    meta_description: str = ""
    h1: list[str] = field(default_factory=list)
    h2_count: int = 0
    canonical: str = ""
    lang: str = ""
    viewport: bool = False
    images_total: int = 0
    images_missing_alt: int = 0
    word_count: int = 0
    jsonld_types: list[str] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    anchor_links: int = 0
    og_tags: bool = False
    typos: list[str] = field(default_factory=list)
    copyright_year: int = 0
    has_tel: bool = False
    has_whatsapp: bool = False
    max_form_fields: int = 0


@dataclass
class AuditReport:
    site_url: str
    generated_at: str
    pages: list[PageAudit] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    site_checks: dict[str, Any] = field(default_factory=dict)
    pagespeed: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AuditReport":
        return cls(
            site_url=d["site_url"],
            generated_at=d["generated_at"],
            pages=[PageAudit(**p) for p in d.get("pages", [])],
            issues=[Issue(**i) for i in d.get("issues", [])],
            site_checks=d.get("site_checks", {}),
            pagespeed=d.get("pagespeed"),
        )


@dataclass
class PageSpec:
    slug: str  # e.g. "uae/solar-installation-dubai/"
    market: str  # UAE | PK | GLOBAL
    service: str
    primary_keyword: str
    secondary_keywords: list[str] = field(default_factory=list)
    title: str = ""
    meta_description: str = ""
    h1: str = ""
    parent: str = ""  # hub slug for breadcrumbs
    enabled: bool = True


@dataclass
class PageDraft:
    slug: str
    market: str
    service: str
    title: str
    meta_description: str
    h1: str
    intro: str = ""
    sections: list[dict] = field(default_factory=list)  # [{"h2":..., "body":...}]
    faq: list[dict] = field(default_factory=list)  # [{"q":..., "a":...}]
    cta_text: str = "Request a quote"
    parent: str = ""
    source: str = "offline"  # ai | offline
    approved: bool = False


@dataclass
class QAIssue:
    level: str  # error | warn
    code: str
    page: str
    message: str


@dataclass
class QAReport:
    issues: list[QAIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[QAIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[QAIssue]:
        return [i for i in self.issues if i.level == "warn"]

    @property
    def passed(self) -> bool:
        return not self.errors


@dataclass
class Change:
    path: str
    kind: str
    risk: str  # low | high
    description: str


@dataclass
class PatchResult:
    files: dict[str, str] = field(default_factory=dict)  # path -> new content (changed/new only)
    originals: dict[str, str] = field(default_factory=dict)
    changes: list[Change] = field(default_factory=list)
    qa: QAReport = field(default_factory=QAReport)
    diffs: dict[str, str] = field(default_factory=dict)
    low_risk_only: bool = False

    def summary(self) -> dict:
        return {
            "files_changed": len(self.files),
            "changes": len(self.changes),
            "high_risk_changes": sum(1 for c in self.changes if c.risk == "high"),
            "qa_errors": len(self.qa.errors),
            "qa_warnings": len(self.qa.warnings),
        }
