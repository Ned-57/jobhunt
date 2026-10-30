"""Keyword taxonomy and text matching.

Lets the app read a job advert and score a profile against it without any AI
call. Multi-word terms are matched as phrases; everything else falls back to
token overlap.
"""
from __future__ import annotations

import re
from typing import Iterable

TAXONOMY: dict[str, list[str]] = {
    "languages": ["c#", ".net", "dotnet", "asp.net", "java", "kotlin", "scala", "python",
        "go", "golang", "rust", "typescript", "javascript", "node.js", "nodejs", "node", "php", "ruby",
        "c++", "swift", "sql", "bash", "powershell", "groovy"],
    "frameworks": ["spring", "spring boot", "entity framework", "react", "angular", "vue",
        "svelte", "next.js", "express", "django", "flask", "fastapi", "rails", "blazor",
        "quarkus", "micronaut", ".net core"],
    "data": ["oracle", "postgres", "postgresql", "mysql", "sql server", "ms sql", "mongodb",
        "couchbase", "cassandra", "redis", "dynamodb", "snowflake", "databricks",
        "bigquery", "elasticsearch", "kafka", "kafka connect", "rabbitmq", "airflow",
        "etl", "data warehouse", "data modelling", "data modeling",
        "supabase", "firebase", "prisma", "sqlite", "mariadb", "neo4j", "influxdb"],
    "cloud": ["aws", "azure", "gcp", "google cloud", "kubernetes", "k8s", "docker", "helm",
        "terraform", "ansible", "openshift", "lambda", "serverless", "ec2", "s3",
        "windows server", "linux", "on-premises", "on-prem", "iis", "active directory",
        "vmware", "hyper-v"],
    "delivery": ["ci/cd", "cicd", "jenkins", "teamcity", "octopus", "github actions",
        "gitlab ci", "azure devops", "argocd", "agile", "scrum", "kanban", "tdd", "bdd",
        "code review", "release management", "change management", "trunk based"],
    "observability": ["prometheus", "grafana", "datadog", "splunk", "new relic",
        "opentelemetry", "kibana", "sre", "on-call", "incident", "observability",
        "monitoring", "alerting"],
    "integration": ["rest", "restful", "graphql", "grpc", "soap", "openapi", "swagger",
        "api gateway", "webhook", "oauth", "saml", "sso", "jwt", "rate limiting",
        "microservices", "event driven", "message queue", "middleware", "sftp", "api",
        "rbac", "role-based access", "role based access", "access control",
        "authorisation", "authorization", "authentication", "permissions",
        "active directory", "ldap", "identity"],
    "analysis": ["requirements", "user stories", "acceptance criteria", "gap analysis",
        "impact analysis", "process mapping", "data mapping", "data flow", "stakeholder",
        "business analysis", "systems analysis", "documentation", "runbook",
        "root cause", "uat", "migration", "discovery", "solution design", "traceability"],
    "clientfacing": ["customer facing", "client facing", "onboarding", "implementation",
        "solutions engineer", "presales", "pre-sales", "technical account", "escalation",
        "sla", "proof of concept", "stakeholder management", "training"],
    "soft": ["communication", "collaboration", "mentoring", "ownership", "autonomy",
        "problem solving", "cross-functional", "time zones"],
    # Adverts increasingly ask for this by name, and none of it was here, so an
    # AI-heavy role could not match AI-heavy evidence.
    "ai": ["llm", "llms", "large language model", "mcp", "model context protocol",
        "anthropic", "anthropic sdk", "openai", "claude", "gpt", "gemini",
        "lm studio", "ollama", "hugging face", "langchain", "prompt engineering",
        "prompt", "tool calling", "function calling", "ai agent", "agent framework",
        "agentic", "rag", "retrieval augmented generation", "vector database",
        "embeddings", "fine-tuning", "inference", "sse", "streaming",
        "guardrail", "grounding", "evals"],
}

ALL_TERMS: list[str] = sorted(
    {term for group in TAXONOMY.values() for term in group}, key=len, reverse=True
)

# Groups that name actual technologies. "training", "ownership" and
# "communication" are useful for matching an advert but are not skills, and
# listing them on a CV reads as padding.
SKILL_GROUPS = ("languages", "frameworks", "data", "cloud", "delivery",
                "observability", "integration", "ai")

# How a skills block is laid out on a CV. Grouping by what a thing *is* reads
# far better than one undifferentiated list, and matches how people actually
# write CVs. Order is the order they appear.
# Terms worth matching in an advert but not worth listing as a skill. "API"
# beside "REST" is noise, "observability" is a category not a tool, and nobody
# writes "grounding" under Key Skills.
NOT_A_SKILL = {
    "api", "rate limiting", "webhook", "middleware",
    "observability", "monitoring", "alerting", "incident", "on-call", "sre",
    "sse", "streaming", "grounding", "guardrail", "guardrails", "prompt",
    "inference", "agentic", "evals",
    "llm", "llms", "large language model", "ai agent", "agent framework",
    "etl", "data warehouse", "data modelling", "data modeling",
}

SKILL_CATEGORIES = [
    ("Languages",             ("languages",)),
    ("Frameworks",            ("frameworks",)),
    ("APIs and integrations", ("integration",)),
    ("Data and messaging",    ("data",)),
    ("Platform and delivery", ("cloud", "delivery", "observability")),
    ("AI and LLM tooling",    ("ai",)),
]

_CATEGORY_OF = {
    term: label
    for label, groups in SKILL_CATEGORIES
    for g in groups
    for term in TAXONOMY[g]
}


def category_of(term: str) -> str:
    """Which CV skills heading a term belongs under, or "" if it is not a skill.

    Plural-tolerant, because display_terms returns the surface form as the
    author wrote it - "API gateways" - while the taxonomy holds the singular.
    """
    key = term.strip().lower()
    if key in _CATEGORY_OF:
        return _CATEGORY_OF[key]
    if len(key) > 3 and key.endswith("s") and not key.endswith("ss"):
        return _CATEGORY_OF.get(key[:-1], "")
    return ""
SKILL_TERMS: list[str] = sorted(
    {t for g in SKILL_GROUPS for t in TAXONOMY[g]}, key=len, reverse=True
)

# Words that carry no signal when scoring an advert against evidence.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "for", "from",
    "had", "has", "have", "in", "into", "is", "it", "its", "of", "on", "or", "our", "so",
    "than", "that", "the", "their", "them", "then", "there", "these", "they", "this",
    "to", "up", "was", "we", "were", "what", "when", "which", "who", "will", "with",
    "you", "your", "role", "team", "work", "working", "experience", "years", "strong",
    "good", "excellent", "ability", "able", "including", "etc", "well", "across", "using",
    "use", "used", "new", "you'll", "we're", "help", "join", "looking", "must", "should",
    "would", "also", "within", "other", "some", "more", "most", "all", "any", "one",
}

TOKEN_RE = re.compile(r"[a-z0-9#+./]+")


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower())


def tokens(text: str) -> set[str]:
    """Content words, stopwords and one-character noise removed.

    Singular forms are added alongside plurals so that an advert asking for
    "REST API design" still matches evidence that says "REST APIs". Naive, but
    the failure mode of a stemmer here is worse than the failure mode of this.
    """
    out: set[str] = set()
    for raw in TOKEN_RE.findall(normalise(text)):
        word = raw.strip(".")
        if len(word) <= 2 or word in STOPWORDS:
            continue
        out.add(word)
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            out.add(word[:-1])
    return out


TERM_SET = set(ALL_TERMS)


def _term_pattern(term: str) -> str:
    """Match a term, tolerating a trailing plural s.

    "data flow" has to match "data flows", or an advert asking for data-flow
    analysis is reported as a gap against evidence that literally says it.
    """
    return r"(?<![a-z0-9])" + re.escape(term) + r"s?(?![a-z0-9])"


def phrases(text: str) -> set[str]:
    """Known multi-word and symbol-bearing terms present in the text.

    Token splitting destroys "c#", "ci/cd" and "spring boot", which are exactly
    the terms that matter most, so those are matched against the raw string.
    """
    haystack = normalise(text)
    found = set()
    for term in ALL_TERMS:
        # Cheap containment check first; the regex is the expensive part.
        if term in haystack and re.search(_term_pattern(term), haystack):
            found.add(term)
    return found


def weigh(term: str) -> float:
    """How much a matched term is worth.

    A named technology or a multi-word phrase is strong evidence of a real
    match. A bare English word like "production" is not - it appears in almost
    every advert and almost every CV.
    """
    if " " in term or any(c in term for c in "#/.+-"):
        return 2.0
    return 2.0 if term in TERM_SET else 1.0


# A requirement written as a sentence carries a lot of filler. Judging
# coverage against every word in it means a long requirement can never be
# met, however well it is evidenced, so only the most specific terms count.
COVERAGE_TERMS = 6


def core_terms(wanted: Iterable[str]) -> set[str]:
    """The most specific terms in `wanted` - what the requirement really asks.

    tokens() adds singular forms alongside plurals, which is right for matching
    but wrong for weighing: counting "framework" and "frameworks" separately
    made one idea worth twice its share of the requirement.
    """
    unique: dict[str, str] = {}
    for term in sorted(set(wanted), key=lambda w: (-weigh(w), -len(w), w)):
        stem = term[:-1] if len(term) > 3 and term.endswith("s") and not term.endswith("ss") else term
        unique.setdefault(stem, term)
    ranked = sorted(unique.values(), key=lambda w: (-weigh(w), -len(w), w))
    return set(ranked[:COVERAGE_TERMS])


def coverage(candidate: str, wanted: Iterable[str]) -> float:
    """Weighted fraction of the requirement's core terms that `candidate` covers."""
    core = core_terms(wanted)
    if not core:
        return 0.0
    total = sum(weigh(w) for w in core)
    present = keywords(candidate)
    got = sum(weigh(w) for w in core & present)
    return got / total if total else 0.0


def keywords(text: str) -> set[str]:
    return tokens(text) | phrases(text)


def display_terms(text: str, limit: int = 8, skills_only: bool = True) -> list[str]:
    """Known technologies in `text`, in the author's own capitalisation.

    A technology profile groups things under headings like "Cloud and
    delivery", which is useful for judging the strength of a claim but reads
    as filler on a CV. The real skills live in the description, so pull them
    out and keep the case the user wrote them in.
    """
    haystack = normalise(text)
    found: list[tuple[int, str]] = []
    for term in (SKILL_TERMS if skills_only else ALL_TERMS):
        if skills_only and term in NOT_A_SKILL:
            continue
        # Same plural tolerance as matching uses. Without it "API gateways"
        # never matched "api gateway", so the row came out near-empty.
        match = re.search(_term_pattern(term), haystack)
        if not match:
            continue
        start, end = match.span()
        # Slice the original string so "AWS" does not come back as "aws".
        found.append((start, text[start:end]))
    found.sort()

    # Drop terms wholly contained in another match, so "SQL", "MS SQL" and
    # "SQL Server" do not all appear side by side.
    picked: list[str] = []
    for _, term in found:
        low = term.lower()
        if any(low in p.lower() for p in picked):
            continue
        picked = [p for p in picked if p.lower() not in low]
        picked.append(term)
    return picked[:limit]


def overlap(candidate: str, wanted: Iterable[str]) -> tuple[float, list[str]]:
    """Score `candidate` against `wanted`; returns (score, matched terms).

    Multi-word terms are worth more than bare tokens because they are far less
    likely to match by accident.
    """
    wanted = set(wanted)
    if not wanted:
        return 0.0, []
    present = keywords(candidate)
    hits = sorted(wanted & present)
    return sum(weigh(h) for h in hits), hits
