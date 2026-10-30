"""Deterministic CV generation.

No AI call. The profile already contains well-written, defensible prose - the
job here is selection and ordering, not writing. Given a role, this scores
every evidence line against what the advert actually asks for, keeps the
strongest, orders the sections by relevance and renders the result.

Because it only ever re-arranges text the user wrote, it cannot invent a
claim. What it can do is tell you what it could not evidence, which is the
part that usually matters.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from .models import Application, Profile
from .taxonomy import coverage as term_coverage
from .taxonomy import (SKILL_CATEGORIES, category_of, display_terms, keywords,
                       overlap, tokens, weigh)

# Calibrated against real one-page CVs written by hand in the house style,
# which run 4,100-4,450 characters of visible text. Markdown syntax is not
# counted, since it does not appear on the page. Used to trim, never to pad.
ONE_PAGE_CHARS = 4500
DEFAULT_EVIDENCE_LINES = 9


class ScoredLine(BaseModel):
    text: str
    score: float
    matched: list[str] = Field(default_factory=list)
    source: str = ""
    origin: str = "evidence"   # "evidence" | "employment"
    owner: str = ""            # index into profile.employment, when origin is employment


class CvSection(BaseModel):
    kind: str
    heading: str
    lines: list[ScoredLine] = Field(default_factory=list)
    entries: list[dict[str, Any]] = Field(default_factory=list)


class CvDocument(BaseModel):
    name: str = ""
    headline: str = ""
    contact: list[str] = Field(default_factory=list)
    summary: str = ""
    sections: list[CvSection] = Field(default_factory=list)

    matched: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    omitted: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stretch: list[str] = Field(default_factory=list)

    markdown: str = ""
    characters: int = 0
    fits_one_page: bool = True
    tailored_fields: list[str] = Field(default_factory=list)
    positioning_used: str = ""


class Tailoring(BaseModel):
    """The small, judgement-shaped part of tailoring a CV.

    Optional. Everything below can be produced by a short AI round trip - see
    the `tailor` prompt - but the CV builds perfectly well without it. Nothing
    here can introduce a claim: `summary` is prose about the user, and the
    other fields only re-order evidence the user already wrote.
    """
    headline: str = ""
    summary: str = ""
    lead_themes: list[str] = Field(default_factory=list)
    emphasise: list[str] = Field(default_factory=list)


class CvRequest(BaseModel):
    application_id: str = ""
    advert: str = ""
    title: str = ""
    company: str = ""
    max_lines: int = DEFAULT_EVIDENCE_LINES
    include_independent: bool = True
    tailoring: Tailoring | None = None


# A requirement counts as evidenced once this much of its weighted keyword
# mass is covered. Tuned so that "Stakeholder management across teams" matches
# evidence naming stakeholders, while "Production on-call" does not match
# evidence that merely says "production".
COVERAGE_THRESHOLD = 0.30

# Concentrate the evidence rather than sprinkling it across every theme.
MAX_THEMES = 3

# One neutral heading for evidence-bank lines. The theme names are how the
# bank is organised, not how a CV reads.
ACHIEVEMENTS_HEADING = "Selected achievements"

# The independent-work heading is itself tailored by hand on a real CV -
# "Python & independent work" for a Python role, "Independent work & side
# projects" otherwise. Lead with a technology only when the advert asks for it
# *and* the chosen projects actually demonstrate it.
INDEPENDENT_HEADING = "Independent work & side projects"

# Roughly the length of a good CV profile paragraph.
SUMMARY_WORD_CAP = 110

THEME_BOOST = 6.0      # the assistant said this theme should lead
EMPHASIS_BOOST = 10.0  # the assistant named this specific line


# --------------------------------------------------------------------------
# role reading
# --------------------------------------------------------------------------
def role_text(application: Application | None, request: CvRequest) -> str:
    if application is not None:
        return " ".join(filter(None, [
            application.title, application.company,
            " ".join(application.key_requirements),
            application.summary, application.description,
        ]))
    return " ".join(filter(None, [request.title, request.company, request.advert]))


def role_requirements(application: Application | None, request: CvRequest) -> list[str]:
    if application is not None and application.key_requirements:
        return [r for r in application.key_requirements if r.strip()]
    # Fall back to lines of a pasted advert that read like requirements.
    lines = [l.strip(" -*•\t") for l in request.advert.splitlines()]
    return [l for l in lines if 12 < len(l) < 180][:12]


# --------------------------------------------------------------------------
# selection
# --------------------------------------------------------------------------
def pick_headline(profile: Profile, wanted: set[str], application: Application | None) -> str:
    """Use the advertised title when it is one the user is actually targeting."""
    advertised = (application.title if application else "").strip()
    for target in profile.core.target_roles:
        if target and target.lower() in advertised.lower():
            return target
    best, best_score = "", 0.0
    for target in profile.core.target_roles:
        score, _ = overlap(target, wanted)
        if score > best_score:
            best, best_score = target, score
    return best or (profile.core.target_roles[0] if profile.core.target_roles else "")


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def pick_summary(profile: Profile) -> str:
    """Compose the profile paragraph from the user's own sentences.

    positioning and summary are both written about the same person and
    overlap heavily, so they are merged sentence by sentence and near
    duplicates dropped - the positioning line and the first line of the summary
    are usually the same claim worded twice.

    Nothing is written here. Producing genuinely role-specific prose is the one
    part of a CV a language model is better at, which is what the optional
    Tailoring.summary replaces.
    """
    kept: list[str] = []
    kept_keywords: list[set[str]] = []
    kept_openings: list[tuple[str, ...]] = []
    words = 0

    for source in (profile.core.positioning, profile.core.summary):
        for sentence in _sentences(source):
            terms = tokens(sentence)
            opening = _opening(sentence)
            # A positioning line and the opening of a summary usually restate
            # each other word for word. Same opening, same claim - keep one,
            # even where the rest of the two sentences diverges.
            if opening and opening in kept_openings:
                continue
            if any(_overlaps(terms, seen) for seen in kept_keywords):
                continue
            length = len(sentence.split())
            if words + length > SUMMARY_WORD_CAP:
                continue
            kept.append(sentence)
            kept_keywords.append(terms)
            kept_openings.append(opening)
            words += length

    return " ".join(kept)


def _opening(sentence: str, words: int = 4) -> tuple[str, ...]:
    """The first few content words, which is where a restatement shows."""
    found = [w.lower() for w in re.findall(r"[A-Za-z][\w'-]*", sentence)
             if len(w) > 2][:words]
    return tuple(found)


def _overlaps(a: set[str], b: set[str], threshold: float = 0.55) -> bool:
    """Two sentences making substantially the same claim."""
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= threshold


def best_positioning(profile: Profile, wanted: set[str]) -> str:
    """Which role-type guidance fits this advert, if any.

    Not printed on the CV - surfaced alongside it so the user can see which of
    their own positioning notes applies.
    """
    best, best_score = "", 0.0
    for entry in profile.positioning:
        if not entry.guidance.strip():
            continue
        score, _ = overlap(entry.role_type + " " + entry.guidance, wanted)
        if score > best_score:
            best, best_score = entry.role_type, score
    return best if best_score >= 4 else ""


def _boost(line_text: str, theme: str, tailoring: Tailoring | None) -> float:
    if tailoring is None:
        return 0.0
    bonus = 0.0
    if any(t.strip() and t.strip().lower() in theme.lower() for t in tailoring.lead_themes):
        bonus += THEME_BOOST
    lowered = line_text.lower()
    for wanted_line in tailoring.emphasise:
        wanted_line = wanted_line.strip().lower()
        if not wanted_line:
            continue
        # Substring either way: the assistant usually quotes a fragment.
        if wanted_line in lowered or lowered[:60] in wanted_line:
            bonus += EMPHASIS_BOOST
            break
    return bonus


def _employer_index(profile: Profile, name: str) -> str:
    """Match a theme's employer to an employment entry, by name."""
    name = (name or "").strip().lower()
    if not name:
        return ""
    for index, job in enumerate(profile.employment):
        if job.company and (name in job.company.lower() or job.company.lower() in name):
            return str(index)
    return ""


def all_claims(profile: Profile, wanted: set[str],
               tailoring: Tailoring | None = None) -> list[ScoredLine]:
    """Every line the CV could draw on, scored.

    Bullets written under a job and lines written in the evidence bank are the
    same kind of thing - a claim you could defend - so they compete on merit
    for the same space. Only scoring the evidence bank meant job bullets were
    printed but never selected, never tailored and never counted towards a
    requirement, which made where you happened to type a line matter more than
    what it said.
    """
    scored: list[ScoredLine] = []

    for group in profile.evidence:
        # A CV reads with achievements under the employer, not in a section of
        # their own. Themes organise the bank; naming the employer says where
        # the work actually happened so it can be printed in the right place.
        owner = _employer_index(profile, group.employer)
        for item in group.items:
            if not item.strip():
                continue
            score, matched = overlap(item, wanted)
            score += _boost(item, group.group, tailoring)
            scored.append(ScoredLine(text=item.strip(), score=score, matched=matched,
                                     source=group.group, origin="evidence", owner=owner))

    for index, job in enumerate(profile.employment):
        label = ", ".join(filter(None, [job.title, job.company])) or f"Role {index + 1}"
        for bullet in job.bullets:
            if not bullet.strip():
                continue
            score, matched = overlap(bullet, wanted)
            score += _boost(bullet, label, tailoring)
            scored.append(ScoredLine(text=bullet.strip(), score=score, matched=matched,
                                     source=label, origin="employment", owner=str(index)))

    return scored


def pick_evidence(profile: Profile, wanted: set[str], limit: int,
                  tailoring: Tailoring | None = None
                  ) -> tuple[list[CvSection], dict[str, list[ScoredLine]], list[ScoredLine]]:
    """Select the strongest claims and split them by where they belong.

    Returns (themed sections, bullets keyed by employment index, dropped).
    """
    scored = all_claims(profile, wanted, tailoring)
    scored.sort(key=lambda l: (-l.score, l.text))

    # Depth beats breadth. One bullet under each of five headings reads as a
    # stub; three under each of two or three headings reads as a CV. Rank the
    # themes, then fill from the strongest ones first.
    best_of_theme: dict[str, float] = {}
    for line in scored:
        best_of_theme[line.source] = max(best_of_theme.get(line.source, 0.0), line.score)
    ranked = [t for t, _ in sorted(best_of_theme.items(), key=lambda kv: -kv[1])]
    priority = {theme: i for i, theme in enumerate(ranked[:MAX_THEMES])}

    front = [l for l in scored if l.source in priority]
    front.sort(key=lambda l: (priority[l.source], -l.score, l.text))
    rest = [l for l in scored if l.source not in priority]

    kept = [l for l in (front + rest)[:limit] if l.score > 0]
    # If the advert is vague and nothing scores, fall back to the first lines
    # rather than producing an empty CV.
    if not kept:
        kept = (front + rest)[:limit]
    dropped = [l for l in scored if l not in kept]

    # Job bullets go under their job; evidence-bank lines get themed sections.
    by_job: dict[str, list[ScoredLine]] = {}
    by_theme: dict[str, list[ScoredLine]] = {}
    for line in kept:
        if line.owner:
            by_job.setdefault(line.owner, []).append(line)
        else:
            by_theme.setdefault(line.source, []).append(line)

    # Theme names organise the evidence bank; they are not CV headings. Nobody
    # puts "Ownership end to end" on a CV as a heading. The
    # selected lines collapse into one section, ordered by theme strength, and
    # each line keeps its source for the panel beside the document.
    ordered = sorted(by_theme.items(),
                     key=lambda kv: -max(l.score for l in kv[1]))
    lines = [line for _theme, group in ordered for line in group]
    sections = ([CvSection(kind="evidence", heading=ACHIEVEMENTS_HEADING, lines=lines)]
                if lines else [])
    return sections, by_job, dropped


def pick_skills(profile: Profile, wanted: set[str]) -> tuple[list[str], list[str], list[str]]:
    """Returns (lines for the CV, stretch warnings, never-claim warnings)."""
    production, project = [], []
    stretch, never = [], []
    order: dict[str, int] = {}     # the user's own ordering, as a tie-break

    for tech in profile.tech:
        if not tech.area.strip():
            continue
        score, _ = overlap(tech.area + " " + tech.description, wanted)
        wanted_here = score > 0

        if tech.level == "never":
            if wanted_here:
                never.append(
                    f"The advert mentions {tech.area}, which you have marked do-not-claim. "
                    f"It has been left off the CV."
                )
            continue
        if tech.level in {"training", "exposure"}:
            if wanted_here:
                stretch.append(
                    f"{tech.area} is asked for but you have it as "
                    f"{'coursework' if tech.level == 'training' else 'exposure only'}. "
                    f"Left off - mention it in the letter if you want to, honestly framed."
                )
            continue

        # "Cloud and delivery" is a heading, not a skill, and "C#/.NET" is two
        # skills in one string. Pull real terms out of the area *and* the
        # description; only fall back to the raw area when neither yields any.
        named = display_terms(tech.area, limit=4) + display_terms(tech.description, limit=6)
        seen, labels = set(), []
        for label in named:
            if label.lower() not in seen:
                seen.add(label.lower())
                labels.append(label)
        if not labels:
            labels = [tech.area.strip()]
        (production if tech.level == "production" else project).extend(
            (score, label) for label in labels
        )
        order[tech.area] = len(order)

    # Group by what a thing is, the way a CV actually reads, rather than one
    # long undifferentiated list. Honesty is preserved by what got excluded
    # above, not by labelling half the list as second class.
    # Rank production claims above project ones, so a skills line opens with
    # what the person actually did for a living rather than with whatever the
    # advert happened to mention.
    ranked = [(2.0, s, l) for s, l in production] + [(1.0, s, l) for s, l in project]

    buckets: dict[str, list[tuple[float, float, str]]] = {}
    leftovers: list[tuple[float, float, str]] = []
    for tier, score, label in ranked:
        category = category_of(label)
        (buckets.setdefault(category, []) if category else leftovers).append((tier, score, label))

    def flatten(pairs, cap: int) -> list[str]:
        pairs.sort(key=lambda p: (-p[0], -p[1]))
        seen, out = set(), []
        for _tier, _score, label in pairs:
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(label)
            if len(out) >= cap:
                break
        return out

    lines = []
    for label, _groups in SKILL_CATEGORIES:
        terms = flatten(buckets.get(label, []), 10)
        if terms:
            lines.append(f"**{label}:** " + ", ".join(terms))
    # No catch-all row: "Also: Supabase" reads as something the categoriser
    # gave up on. Anything genuinely uncategorised is better left off than
    # dumped under a heading that means nothing.
    _ = leftovers
    return lines, stretch, never


def heading_for_independent(wanted: set[str], chosen: list[Any]) -> str:
    """Name the section after what it is proving, when there is a clear answer."""
    blob = " ".join(
        " ".join([i.name, i.description, " ".join(i.bullets), " ".join(i.tech)])
        for i in chosen
    )
    present = keywords(blob)

    # "API & independent work" is not a heading anyone writes. Lead only with
    # something concrete - a language, a tool, an AI capability.
    HEADLINE_CATEGORIES = {"Languages", "AI and LLM tooling", "Data and messaging"}
    GENERIC = {"api", "rest", "sql", "streaming", "prompt", "inference"}

    best, best_weight = "", 0.0
    for term in wanted & present:
        if category_of(term) not in HEADLINE_CATEGORIES or term in GENERIC:
            continue
        weight = weigh(term) + (2.0 if term in keywords(blob) else 0.0)
        if weight > best_weight:
            best, best_weight = term, weight

    if not best:
        return INDEPENDENT_HEADING
    # Keep the author's capitalisation - "LLM", not "Llm". Match the term where
    # it appears in the text, allowing the plural, and slice the original.
    match = re.search(r"(?<![A-Za-z0-9])" + re.escape(best) + r"s?(?![A-Za-z0-9])",
                      blob, re.IGNORECASE)
    label = match.group(0) if match else best.title()
    return f"{label} & independent work"


def match_requirements(requirements: list[str], evidence: list[ScoredLine],
                       profile: Profile) -> tuple[list[dict[str, Any]], list[str]]:
    """Pair each requirement with the best piece of evidence, or record a gap.

    A requirement naming something on the do-not-claim list is a gap however
    well the rest of it scores. Otherwise "Azure AD and SSO" matches a line
    about Google SSO on a side project, and the document reports the
    requirement as covered while separately warning that Azure AD must not be
    claimed - two answers to the same question, one of them false.
    """
    off_limits = {t.area.strip().lower() for t in profile.tech
                  if t.level == "never" and t.area.strip()}
    pool = list(evidence)
    seen = {l.text for l in pool}

    def offer(text: str, source: str, origin: str) -> None:
        text = text.strip()
        if text and text not in seen:
            seen.add(text)
            pool.append(ScoredLine(text=text, score=0, source=source, origin=origin))

    for group in profile.evidence:
        for item in group.items:
            offer(item, group.group, "evidence")
    # Job bullets are evidence too, whether or not they made it onto the CV.
    for job in profile.employment:
        label = ", ".join(filter(None, [job.title, job.company]))
        for bullet in job.bullets:
            offer(bullet, label, "employment")
    # So is independent work. Leaving it out meant a project that plainly
    # evidenced a requirement was still reported as a gap.
    for item in profile.independent:
        offer(item.description, item.name, "independent")
        for bullet in item.bullets:
            offer(bullet, item.name, "independent")

    matched, gaps = [], []
    for requirement in requirements:
        wanted = keywords(requirement)
        if not wanted:
            continue
        lowered = requirement.lower()
        if any(term in lowered for term in off_limits):
            gaps.append(requirement)
            continue
        best, best_score, best_cover = None, 0.0, 0.0
        for line in pool:
            score, _ = overlap(line.text, wanted)
            if score > best_score:
                best, best_score = line, score
                best_cover = term_coverage(line.text, wanted)

        # Judge by how much of the requirement is actually covered, weighted so
        # that a named technology counts for more than a word like
        # "production" that appears in every advert ever written.
        coverage = best_cover if best else 0.0
        if best and (coverage >= COVERAGE_THRESHOLD or best_score >= 6):
            matched.append({
                "requirement": requirement, "evidence": best.text,
                "score": round(best_score, 1), "coverage": round(coverage, 2),
                "on_cv": any(l.text == best.text for l in evidence),
            })
        else:
            gaps.append(requirement)
    return matched, gaps


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def render_markdown(doc: CvDocument) -> str:
    out = [f"# {doc.name}"]
    if doc.headline:
        out.append(f"**{doc.headline}**")
    if doc.contact:
        out.append(" · ".join(doc.contact))
    if doc.summary:
        out += ["", "## Profile", "", doc.summary]

    for section in doc.sections:
        out += ["", f"## {section.heading}", ""]
        for line in section.lines:
            out.append(f"- {line.text}")
        for entry in section.entries:
            head = f"**{entry.get('title', '')}**"
            if entry.get("company"):
                head += f", {entry['company']}"
            if entry.get("dates"):
                head += f"  ·  {entry['dates']}"
            out.append(head)
            if entry.get("note"):
                out.append(entry["note"])
            for bullet in entry.get("bullets", []):
                out.append(f"- {bullet}")
            out.append("")
    return "\n".join(out).strip() + "\n"


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def month(value: str) -> str:
    """YYYY-MM to "Mon YYYY". Anything else is passed through untouched."""
    parts = str(value or "").split("-")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        index = int(parts[1]) - 1
        if 0 <= index < 12:
            return f"{MONTHS[index]} {parts[0]}"
    return str(value or "")


MARKUP = re.compile(r"^\s*(#{1,6}\s*|[-*]\s+)|\*\*|__|`")


def visible_length(markdown: str) -> int:
    """Characters a reader actually sees - markdown syntax is not on the page."""
    return sum(len(MARKUP.sub("", line).strip()) + 1
               for line in markdown.splitlines() if line.strip())


def dates(start: str, end: str, current: bool) -> str:
    if not start and not end:
        return ""
    finish = "present" if current else (month(end) or "present")
    return f"{month(start)} – {finish}"


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def build(profile: Profile, request: CvRequest,
          application: Application | None = None) -> CvDocument:
    text = role_text(application, request)
    wanted = keywords(text)
    requirements = role_requirements(application, request)

    tailoring = request.tailoring
    doc = CvDocument(
        name=profile.identity.name or "Unnamed",
        headline=pick_headline(profile, wanted, application),
        summary=pick_summary(profile),
    )

    # An optional short AI round trip can supply a role-specific headline and
    # opening paragraph. Everything else stays deterministic.
    if tailoring:
        if tailoring.headline.strip():
            doc.headline = tailoring.headline.strip()
            doc.tailored_fields.append("headline")
        if tailoring.summary.strip():
            doc.summary = tailoring.summary.strip()
            doc.tailored_fields.append("summary")
        if tailoring.lead_themes:
            doc.tailored_fields.append("theme order")
        if tailoring.emphasise:
            doc.tailored_fields.append("evidence emphasis")

    doc.contact = [c for c in [
        profile.identity.email, profile.identity.phone,
        profile.identity.portfolio, profile.identity.linkedin, profile.identity.github,
    ] if c]

    # ---- skills
    skill_lines, stretch, never = pick_skills(profile, wanted)
    if skill_lines:
        doc.sections.append(CvSection(
            kind="skills", heading="Key skills",
            lines=[ScoredLine(text=l, score=0) for l in skill_lines]))

    # ---- evidence, the substance of the CV
    evidence_sections, job_bullets, dropped = pick_evidence(
        profile, wanted, request.max_lines, tailoring)
    doc.sections.extend(evidence_sections)
    on_cv = ([l for s in evidence_sections for l in s.lines]
             + [l for lines in job_bullets.values() for l in lines])

    # ---- employment
    jobs = []
    for index, job in enumerate(profile.employment):
        picked = [l.text for l in job_bullets.get(str(index), [])]
        # Drop the note when a bullet already makes the same point - a short
        # role's note and its bullet are often the same sentence written twice.
        note = job.note
        if note and any(_overlaps(tokens(note), tokens(b)) for b in picked):
            note = ""
        entry = {"title": job.title, "company": job.company,
                 "dates": dates(job.start, job.end, job.current), "note": note,
                 "bullets": picked}
        jobs.append(entry)
    if jobs:
        doc.sections.append(CvSection(kind="experience", heading="Experience", entries=jobs))

    # ---- independent work, only when it speaks to this role
    if request.include_independent:
        relevant = []
        for item in profile.independent:
            blob = " ".join([item.name, item.description, " ".join(item.bullets),
                             " ".join(item.tech)])
            score, _ = overlap(blob, wanted)
            if score > 0:
                relevant.append((score, item))
        relevant.sort(key=lambda p: -p[0])
        if relevant:
            chosen = [item for _, item in relevant[:3]]
            doc.sections.append(CvSection(
                kind="independent",
                heading=heading_for_independent(wanted, chosen),
                entries=[{"title": i.name,
                          "company": ", ".join(i.tech[:3]),
                          "dates": i.url,
                          "note": i.description,
                          "bullets": [b for b in i.bullets if b.strip()][:2]}
                         for _, i in relevant[:3]]))

    # ---- education
    if profile.education:
        doc.sections.append(CvSection(
            kind="education", heading="Education",
            entries=[{"title": " ".join(filter(None, [e.qualification, e.field])),
                      "company": e.school, "dates": dates(e.start, e.end, False),
                      "note": e.note, "bullets": []}
                     for e in profile.education]))

    # ---- honesty reporting
    doc.matched, doc.gaps = match_requirements(requirements, on_cv, profile)
    doc.omitted = [l.text for l in dropped[:8]]
    doc.stretch = stretch
    doc.warnings = never + [
        b for b in profile.boundaries
        if any(k in keywords(b) for k in wanted)
    ][:4]

    doc.positioning_used = best_positioning(profile, wanted)
    budget = ONE_PAGE_CHARS * max(1, profile.doc_prefs.max_pages)
    trim_to_fit(doc, budget)

    doc.markdown = render_markdown(doc)
    doc.characters = visible_length(doc.markdown)
    doc.fits_one_page = doc.characters <= budget
    return doc


def rerender(doc: CvDocument, max_pages: int = 1) -> CvDocument:
    """Re-render a document after it has been edited by hand.

    The markdown, character count and page verdict are derived, so they go
    stale the moment a line is deleted in the browser. Recomputing them here
    keeps one renderer rather than a second copy in JavaScript. No trimming -
    an edited document is the author's business.
    """
    doc.markdown = render_markdown(doc)
    doc.characters = visible_length(doc.markdown)
    doc.fits_one_page = doc.characters <= ONE_PAGE_CHARS * max(1, max_pages)
    return doc


def trim_to_fit(doc: CvDocument, budget: int) -> None:
    """Drop the weakest content until the document fits the page budget.

    Trims from the bottom up - the last bullet of the last project first, then
    the weakest job bullets - and never strips a section down to nothing, so a
    long CV gets shorter rather than gutted.
    """
    def size() -> int:
        return visible_length(render_markdown(doc))

    def shrink_entries(kind: str, floor: int) -> bool:
        for section in reversed(doc.sections):
            if section.kind != kind:
                continue
            for entry in reversed(section.entries):
                if len(entry.get("bullets", [])) > floor:
                    entry["bullets"].pop()
                    return True
        return False

    guard = 0
    while size() > budget and guard < 60:
        guard += 1
        if shrink_entries("independent", 1):
            continue
        if shrink_entries("experience", 2):
            continue
        # Last resort: the lowest-scoring line in the achievements section.
        weakest = [s for s in doc.sections if s.kind == "evidence" and len(s.lines) > 1]
        if weakest:
            section = weakest[-1]
            section.lines.remove(min(section.lines, key=lambda l: l.score))
            continue
        # Then whole trailing projects, keeping at least one.
        projects = [s for s in doc.sections if s.kind == "independent"]
        if projects and len(projects[-1].entries) > 1:
            projects[-1].entries.pop()
            continue
        break
