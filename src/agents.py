"""CrewAI agent definitions + thin helpers. crewai is imported lazily so the rest of the app works without it."""
from __future__ import annotations

from .config import get_settings
from .llm import LLMError, get_crewai_llm

COMMON_RULES = (
    "Hard rules: use ONLY facts supplied to you; never invent statistics, prices, certifications, awards, "
    "testimonials, regulations or project names; if a needed fact is missing write [NEEDS CLIENT FACT: what is missing]; "
    "write naturally for humans (no keyword stuffing); no black-hat tactics; never copy competitor text."
)

AGENT_SPECS: dict[str, dict[str, str]] = {
    "auditor": {
        "role": "Technical SEO Auditor",
        "goal": "Turn raw crawl findings into a prioritized, plain-English fix plan for a solar/energy company's website.",
        "backstory": "Senior technical SEO who has audited hundreds of service-business sites. You prioritize by lead impact. " + COMMON_RULES,
    },
    "strategist": {
        "role": "Keyword & Intent Strategist",
        "goal": "Map one primary keyword to one page, separately for UAE and Pakistan, by search intent.",
        "backstory": "Local-SEO strategist for the GCC and South Asia who knows how homeowners and facility managers search for solar, BESS and EV charging. " + COMMON_RULES,
    },
    "competitor": {
        "role": "Competitor Analyst",
        "goal": "Find content, proof and offer gaps versus competitor pages supplied by the user.",
        "backstory": "Analyst who compares page structure, proof and offers, and reports gaps without copying text. " + COMMON_RULES,
    },
    "writer": {
        "role": "Senior SEO Content Writer",
        "goal": "Write helpful, accurate, unique service-page copy that converts visitors into quote requests.",
        "backstory": "Energy-sector copywriter. You write clear, trustworthy copy in plain English for buyers of solar, EV charging and electrical services. " + COMMON_RULES,
    },
    "reviewer": {
        "role": "Fact-Checking Editor & Compliance Reviewer",
        "goal": "Remove unsupported claims, fix keyword stuffing and return clean JSON in the exact schema.",
        "backstory": "Strict editor who deletes any claim not present in the supplied facts and follows Google's spam policies. " + COMMON_RULES,
    },
    "cro": {
        "role": "Conversion (CRO) & Lead-Gen Specialist",
        "goal": "Recommend concrete changes that raise quote requests: form, CTAs, trust blocks, mobile contact options.",
        "backstory": "CRO specialist for high-ticket B2C/B2B services where trust and speed-to-contact decide the sale. " + COMMON_RULES,
    },
    "local": {
        "role": "Local SEO & Authority Builder",
        "goal": "Draft Google Business Profile content, review requests and outreach emails (drafts only; a human sends).",
        "backstory": "Local-SEO specialist for service businesses in Dubai and Lahore. You write honest, non-spammy outreach. " + COMMON_RULES,
    },
    "designer": {
        "role": "Premium Web Designer (CSS)",
        "goal": "Make a service-business website look premium, trustworthy and fast using small, safe, scoped CSS.",
        "backstory": "Front-end designer who ships restrained, high-contrast, mobile-first CSS for B2B/B2C energy and construction brands. You never add external dependencies. " + COMMON_RULES,
    },
    "reporter": {
        "role": "SEO Performance Reporter",
        "goal": "Explain Search Console data and recommend the next three actions.",
        "backstory": "Analyst who turns clicks, impressions, CTR and position into clear next steps for a business owner. " + COMMON_RULES,
    },
}


def _crewai():
    try:
        from crewai import Agent, Crew, Process, Task
    except ImportError as exc:
        raise LLMError("crewai is not installed (pip install crewai).") from exc
    return Agent, Crew, Process, Task


def build_agent(key: str, llm):
    Agent, *_ = _crewai()
    spec = AGENT_SPECS[key]
    return Agent(role=spec["role"], goal=spec["goal"], backstory=spec["backstory"], llm=llm, allow_delegation=False, verbose=False)


def _raw(out) -> str:
    return getattr(out, "raw", None) or str(out)


def run_single(key: str, description: str, expected_output: str, fast: bool = False) -> str:
    """One agent, one task."""
    _, Crew, Process, Task = _crewai()
    llm = get_crewai_llm(fast=fast)
    agent = build_agent(key, llm)
    task = Task(description=description, expected_output=expected_output, agent=agent)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, max_rpm=get_settings().max_rpm, verbose=False)
    return _raw(crew.kickoff())


def run_writer_reviewer(write_prompt: str, review_prompt: str, expected: str) -> tuple[str, str]:
    """Two agents in sequence: Writer drafts, Reviewer (with the writer's output as context) corrects."""
    _, Crew, Process, Task = _crewai()
    llm = get_crewai_llm()
    writer, reviewer = build_agent("writer", llm), build_agent("reviewer", llm)
    t1 = Task(description=write_prompt, expected_output=expected, agent=writer)
    t2 = Task(description=review_prompt, expected_output=expected, agent=reviewer, context=[t1])
    crew = Crew(agents=[writer, reviewer], tasks=[t1, t2], process=Process.sequential, max_rpm=get_settings().max_rpm, verbose=False)
    out = crew.kickoff()
    outputs = getattr(out, "tasks_output", None) or []
    if len(outputs) >= 2:
        return _raw(outputs[0]), _raw(outputs[1])
    return "", _raw(out)
