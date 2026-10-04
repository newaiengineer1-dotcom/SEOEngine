from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import storage  # noqa: E402
from src.facts import load_facts  # noqa: E402
from src.keywords import default_page_plan  # noqa: E402
from src.models import PageDraft  # noqa: E402


# Keep ALL test state (logs, control flags) out of the real data/state folder.
storage.STATE_DIR = Path(tempfile.mkdtemp(prefix="kg-test-state-"))


def fixture(name: str) -> str:
    return (ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8")


def facts() -> dict:
    return load_facts()


def spec(slug: str):
    return next(s for s in default_page_plan() if s.slug == slug)


TEXTS = {
    "uae/solar-installation-dubai/": (
        "Homeowners and businesses in Dubai often start by asking what size of solar array fits their roof and their electricity use.\n\n"
        "A site survey looks at roof space, shading, structure and the electrical room before any design work begins.",
        [
            {"h2": "What a rooftop solar project involves", "body": "Engineers survey the building, prepare a design, procure equipment, install the panels and inverter, and commission the system with the utility where required."},
            {"h2": "Questions to ask before you buy", "body": "Ask for a clear scope, the equipment list, the maintenance plan and who handles approvals so that nothing surprises you later."},
        ],
    ),
    "pakistan/solar-installation-lahore/": (
        "Households and factories around Lahore look at solar to manage rising electricity costs and unreliable supply.\n\n"
        "Good planning starts with a load review, a roof inspection and a realistic discussion of what the customer needs from the system.",
        [
            {"h2": "From enquiry to commissioning", "body": "A typical job moves from a visit and load review to design, material supply, installation, testing and a handover walk-through with the owner."},
            {"h2": "Choosing between system types", "body": "Grid-tied, hybrid and battery-backed designs suit different needs, and the right choice depends on the site and the daily usage pattern."},
        ],
    ),
}


def filled_draft(slug: str) -> PageDraft:
    s = spec(slug)
    intro, sections = TEXTS[slug]
    return PageDraft(
        slug=s.slug, market=s.market, service=s.service, title=s.title, meta_description=s.meta_description, h1=s.h1,
        intro=intro, sections=sections,
        faq=[{"q": f"How do I request a quote for {s.service.lower()}?", "a": "Use the quote form on our website or call the number in the footer and tell us about your site."}],
        parent=s.parent, source="ai",
    )


class TempState:
    """Redirect state/log files into a temp dir for the duration of a test."""

    def __enter__(self):
        self._old = storage.STATE_DIR
        self._tmp = tempfile.TemporaryDirectory()
        storage.STATE_DIR = Path(self._tmp.name)
        return Path(self._tmp.name)

    def __exit__(self, *a):
        storage.STATE_DIR = self._old
        self._tmp.cleanup()
