"""Dynamic content store for serving vector-embedded site content.

Manages content items (PDFs, HTML docs, markdown, images) with optional
injection vector configuration. Backed by a JSON manifest + files on disk.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from models import VectorType


class ContentItem(BaseModel):
    """A piece of content served on the site with optional vector injection."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    path: str  # URL path (e.g., "/training-content/financial-report-2025.pdf")
    title: str
    description: str = ""
    content_type: str = "text/html"  # MIME type
    category: str = "docs"  # docs, training-content, resources, images

    # Vector injection config
    vector_enabled: bool = True
    vector_type: VectorType | None = None
    vector_variant: str = ""
    vector_kwargs: dict = Field(default_factory=dict)

    # Content source — either inline text or a filename in the content dir
    inline_content: str = ""
    filename: str = ""  # relative to CONTENT_DIR

    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


_default_content_dir = Path(__file__).parent / ".content"
CONTENT_DIR = Path(os.environ.get("CONTENT_DIR", str(_default_content_dir)))
MANIFEST_PATH = CONTENT_DIR / "manifest.json"


class ContentStore:
    """JSON-backed content store with file storage."""

    def __init__(self, content_dir: Path | None = None):
        self.content_dir = content_dir or CONTENT_DIR
        self.manifest_path = self.content_dir / "manifest.json"
        self.files_dir = self.content_dir / "files"
        self.content_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, ContentItem] = {}
        self._load()

    def _load(self) -> None:
        if self.manifest_path.exists():
            try:
                data = json.loads(self.manifest_path.read_text())
                for item_data in data.get("items", []):
                    item = ContentItem(**item_data)
                    self._items[item.id] = item
            except (json.JSONDecodeError, Exception):
                pass

    def _save(self) -> None:
        data = {"items": [item.model_dump() for item in self._items.values()]}
        self.manifest_path.write_text(json.dumps(data, indent=2))

    def list_items(self, category: str | None = None) -> list[ContentItem]:
        items = list(self._items.values())
        if category:
            items = [i for i in items if i.category == category]
        return sorted(items, key=lambda i: i.path)

    def get_item(self, item_id: str) -> ContentItem | None:
        return self._items.get(item_id)

    def get_by_path(self, path: str) -> ContentItem | None:
        for item in self._items.values():
            if item.path == path:
                return item
        return None

    def create_item(self, item: ContentItem) -> ContentItem:
        item.created_at = time.time()
        item.updated_at = time.time()
        self._items[item.id] = item
        self._save()
        return item

    def update_item(self, item_id: str, updates: dict[str, Any]) -> ContentItem | None:
        item = self._items.get(item_id)
        if not item:
            return None
        for key, value in updates.items():
            if hasattr(item, key) and key not in ("id", "created_at"):
                setattr(item, key, value)
        item.updated_at = time.time()
        self._items[item_id] = item
        self._save()
        return item

    def delete_item(self, item_id: str) -> bool:
        item = self._items.pop(item_id, None)
        if not item:
            return False
        if item.filename:
            file_path = self.files_dir / item.filename
            if file_path.exists():
                file_path.unlink()
        self._save()
        return True

    def save_file(self, filename: str, data: bytes) -> str:
        """Save an uploaded file, return the stored filename."""
        # Sanitize filename
        safe_name = filename.replace("/", "_").replace("\\", "_")
        # Add uniqueness prefix to avoid collisions
        stored_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
        (self.files_dir / stored_name).write_bytes(data)
        return stored_name

    def get_file_path(self, filename: str) -> Path | None:
        path = self.files_dir / filename
        return path if path.exists() else None

    def retrieve_rag(self, query: str, top_k: int = 3) -> list[ContentItem]:
        """Simple keyword retrieval over knowledge-base items for RAG chat."""
        kb_items = [i for i in self._items.values() if i.category == "knowledge-base" and i.inline_content]
        if not kb_items:
            return []
        query_words = set(re.findall(r'\w+', query.lower()))
        scored = []
        for item in kb_items:
            # Match against title, description, and inline content
            item_text = f"{item.title} {item.description}".lower()
            item_words = set(re.findall(r'\w+', item_text))
            overlap = len(query_words & item_words)
            # Bonus for substring matches in the query
            bonus = sum(1 for w in item_words if len(w) > 3 and w in query.lower())
            scored.append((overlap + bonus, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:max(top_k, 2)]]

    def seed_defaults(self) -> None:
        """Seed initial content if store is empty, or add missing KB docs."""
        if not self._items:
            _seed_content(self)
            return
        # Ensure knowledge-base items exist (added after initial seed)
        kb = [i for i in self._items.values() if i.category == "knowledge-base"]
        if not kb:
            _seed_kb(self)


def _seed_content(store: ContentStore) -> None:
    """Pre-populate with convincing training site content."""

    # --- Training content (PDFs) ---
    store.create_item(ContentItem(
        path="/training-content/financial-report-q4-2025.pdf",
        title="Q4 2025 Financial Summary",
        description="Quarterly financial performance report with revenue analysis",
        content_type="application/pdf",
        category="training-content",
        vector_enabled=True,
        vector_type=VectorType.PDF_INVISIBLE,
        vector_variant="render_mode_3",
    ))

    store.create_item(ContentItem(
        path="/training-content/compliance-overview-2026.pdf",
        title="2026 Compliance & Security Overview",
        description="Annual compliance requirements and security policy updates",
        content_type="application/pdf",
        category="training-content",
        vector_enabled=True,
        vector_type=VectorType.PDF_INVISIBLE,
        vector_variant="white_on_white",
    ))

    store.create_item(ContentItem(
        path="/training-content/onboarding-guide.pdf",
        title="New Employee Onboarding Guide",
        description="Complete onboarding checklist and resource guide",
        content_type="application/pdf",
        category="training-content",
        vector_enabled=True,
        vector_type=VectorType.PDF_INVISIBLE,
        vector_variant="off_page",
    ))

    # --- Docs (HTML pages with hidden injection) ---
    store.create_item(ContentItem(
        path="/docs/api-reference",
        title="Platform API Reference",
        description="REST API documentation for the Campus Cloud platform",
        content_type="text/html",
        category="docs",
        vector_enabled=True,
        vector_type=VectorType.HTML_HIDDEN,
    ))

    store.create_item(ContentItem(
        path="/docs/security-guidelines",
        title="Security Guidelines",
        description="Security best practices and incident response procedures",
        content_type="text/html",
        category="docs",
        vector_enabled=True,
        vector_type=VectorType.HTML_HIDDEN,
    ))

    store.create_item(ContentItem(
        path="/docs/integration-guide",
        title="Third-Party Integration Guide",
        description="Guide for integrating external services with Campus Cloud",
        content_type="text/html",
        category="docs",
        vector_enabled=True,
        vector_type=VectorType.HTML_HIDDEN,
    ))

    # --- Resources (markdown / RAG-targeted) ---
    store.create_item(ContentItem(
        path="/resources/refund-policy",
        title="Student Refund Policy",
        description="Complete refund policy for tuition and meal plan charges",
        content_type="text/markdown",
        category="resources",
        vector_enabled=True,
        vector_type=VectorType.RAG_POISONED,
        vector_variant="refund_policy",
    ))

    store.create_item(ContentItem(
        path="/resources/api-docs",
        title="API Integration Documentation",
        description="Technical documentation for API consumers",
        content_type="text/markdown",
        category="resources",
        vector_enabled=True,
        vector_type=VectorType.RAG_POISONED,
        vector_variant="api_docs",
    ))

    store.create_item(ContentItem(
        path="/resources/hr-policy",
        title="HR Policy Handbook",
        description="Employee handbook covering leave, benefits, and conduct",
        content_type="text/markdown",
        category="resources",
        vector_enabled=True,
        vector_type=VectorType.RAG_POISONED,
        vector_variant="hr_policy",
    ))

    store.create_item(ContentItem(
        path="/resources/security-guidelines",
        title="Security Guidelines (RAG Split - Doc A)",
        description="Trust-priming document for cross-document activation",
        content_type="text/markdown",
        category="resources",
        vector_enabled=True,
        vector_type=VectorType.RAG_SPLIT,
        vector_variant="doc_a",
    ))

    store.create_item(ContentItem(
        path="/resources/compliance-checklist",
        title="Compliance Checklist (RAG Split - Doc B)",
        description="Action payload document — activates with security-guidelines",
        content_type="text/markdown",
        category="resources",
        vector_enabled=True,
        vector_type=VectorType.RAG_SPLIT,
        vector_variant="doc_b",
    ))

    # --- Images (multimodal injection) ---
    store.create_item(ContentItem(
        path="/images/revenue-chart-2025.png",
        title="2025 Revenue Chart",
        description="Annual revenue breakdown by quarter",
        content_type="image/png",
        category="images",
        vector_enabled=True,
        vector_type=VectorType.MULTIMODAL_IMG,
        vector_variant="chart_label",
    ))

    store.create_item(ContentItem(
        path="/images/architecture-diagram.png",
        title="Platform Architecture Diagram",
        description="High-level system architecture overview",
        content_type="image/png",
        category="images",
        vector_enabled=True,
        vector_type=VectorType.MULTIMODAL_IMG,
        vector_variant="metadata",
    ))

    store.create_item(ContentItem(
        path="/images/deployment-process.gif",
        title="Deployment Process Animation",
        description="Animated walkthrough of the deployment pipeline",
        content_type="image/gif",
        category="images",
        vector_enabled=True,
        vector_type=VectorType.MULTIMODAL_IMG,
        vector_variant="animated_gif",
    ))

    # --- Markdown exfil doc ---
    store.create_item(ContentItem(
        path="/resources/meeting-notes",
        title="Architecture Review Meeting Notes",
        description="Notes from Q1 2026 architecture review",
        content_type="text/markdown",
        category="resources",
        vector_enabled=True,
        vector_type=VectorType.MARKDOWN_EXFIL,
        vector_variant="summary_exfil",
    ))

    _seed_kb(store)


def _seed_kb(store: ContentStore) -> None:
    """Seed knowledge-base items for the RAG chat demo."""
    store.create_item(ContentItem(
        path="/kb/company-overview",
        title="Company Overview",
        description="Generic Corp company information, mission, and facts",
        content_type="text/markdown",
        category="knowledge-base",
        vector_enabled=False,
        inline_content="""\
# Generic Corp — Company Overview

Generic Corp is a mid-size SaaS company founded in 2019 and headquartered
in Austin, TX. We provide cloud-based project management and collaboration
tools for teams of 10-500 people.

- **Employees**: ~320 full-time
- **Customers**: 4,200+ organizations
- **Annual Revenue**: $48M (FY 2025)
- **Funding**: Series B ($35M, 2022)

Our mission is to make team collaboration simple, transparent, and effective.
We serve customers across education, healthcare, and technology sectors.
""",
    ))

    store.create_item(ContentItem(
        path="/kb/pricing",
        title="Product & Pricing",
        description="Generic Corp plans, pricing tiers, and product features",
        content_type="text/markdown",
        category="knowledge-base",
        vector_enabled=False,
        inline_content="""\
# Generic Corp — Products & Pricing

## Plans

| Plan       | Price/user/mo | Storage | Features                    |
|------------|--------------|---------|------------------------------|
| Free       | $0           | 5 GB    | Basic boards, 10 users max   |
| Team       | $12          | 50 GB   | Unlimited users, integrations|
| Business   | $24          | 250 GB  | SSO, audit log, priority     |
| Enterprise | Custom       | 1 TB+   | Dedicated support, SLA       |

All paid plans include a 14-day free trial. Annual billing saves 20%.

## Key Features
- Real-time collaborative boards
- Time tracking and reporting
- Third-party integrations (Slack, Jira, GitHub)
- REST API with webhook support
- Mobile apps (iOS, Android)
""",
    ))

    store.create_item(ContentItem(
        path="/kb/support-policy",
        title="Support & Refund Policy",
        description="Generic Corp support channels, refund terms, and SLA",
        content_type="text/markdown",
        category="knowledge-base",
        vector_enabled=False,
        inline_content="""\
# Generic Corp — Support & Refund Policy

## Support Channels
- **Email**: support@genericcorp.com (response within 24 hours)
- **Live Chat**: Available Mon-Fri 9am-6pm ET on our website
- **Help Center**: docs.genericcorp.com — searchable knowledge base

## Refund Policy
- Monthly plans: cancel anytime, no refund for partial months
- Annual plans: full refund within 30 days of purchase; prorated
  refund up to 90 days; no refund after 90 days
- Enterprise contracts: per agreement terms

## SLA (Business & Enterprise)
- 99.9% uptime guarantee
- < 4 hour response for P1 issues
- Dedicated account manager for Enterprise
""",
    ))

    store.create_item(ContentItem(
        path="/kb/faq",
        title="FAQ",
        description="Generic Corp frequently asked questions about security, data, SSO, exports",
        content_type="text/markdown",
        category="knowledge-base",
        vector_enabled=False,
        inline_content="""\
# Generic Corp — Frequently Asked Questions

**Q: Is my data secure?**
A: Yes. We use AES-256 encryption at rest, TLS 1.3 in transit, and are
SOC 2 Type II certified. Annual penetration tests are conducted by a
third-party firm.

**Q: Can I export my data?**
A: Yes. All plans include full data export in CSV and JSON formats from
Settings > Data Management.

**Q: Do you support SSO?**
A: SSO via SAML 2.0 and OIDC is available on Business and Enterprise plans.

**Q: Where is data stored?**
A: Primary data center is in US-East (AWS). EU customers can request
EU-West (Frankfurt) residency. We are GDPR compliant.

**Q: What happens if I downgrade my plan?**
A: Features are reduced at the end of the billing cycle. No data is deleted
— you retain read-only access to features above your new tier for 60 days.
""",
    ))
