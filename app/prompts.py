"""Prompt construction.

The Hunt button does not call an AI provider. It builds a prompt from the
answers the user gave, hands it to whichever assistant they already pay for,
and asks for the reply in a shape this app can read back in.

Keeping this server-side means the prompts are testable, versionable, and
identical no matter what opens them.
"""
from __future__ import annotations

import textwrap
from typing import Any, Iterable

from .models import Application, Profile

PROMPT_VERSION = "1.0"

# The reply format the hunt prompt asks for. Kept in one place because both
# the prompt and the importer have to agree on it exactly.
IMPORT_SCHEMA = """[
  {
    "title": "exact job title from the advert",
    "company": "employer name",
    "location": "city, country - or Remote",
    "work_mode": "remote | hybrid | onsite",
    "url": "direct link to the advert you actually found",
    "posted": "YYYY-MM-DD if stated, otherwise \\"\\"",
    "salary": "as advertised, otherwise \\"\\"",
    "summary": "two sentences on what the role actually involves",
    "key_requirements": ["the 5-8 requirements that matter most"],
    "why_match": "which of my evidence lines up, naming it",
    "concerns": "anything that does not fit",
    "source": "where you found it, e.g. company careers page"
  }
]"""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _clean(text: str) -> str:
    return textwrap.dedent(text).strip()


def _bullets(items: Iterable[str], prefix: str = "- ") -> str:
    return "\n".join(f"{prefix}{item.strip()}" for item in items if str(item).strip())


def _join(items: Iterable[str], fallback: str = "not specified") -> str:
    values = [str(i).strip() for i in items if str(i).strip()]
    return ", ".join(values) if values else fallback


def _section(heading: str, body: str) -> str:
    body = body.strip()
    return f"## {heading}\n{body}" if body else ""


def _assemble(*blocks: str) -> str:
    return "\n\n".join(block.strip() for block in blocks if block and block.strip())


# --------------------------------------------------------------------------
# profile fragments, reused across prompt kinds
# --------------------------------------------------------------------------
def who_i_am(p: Profile) -> str:
    lines = []
    if p.core.positioning:
        lines.append(p.core.positioning.strip())
    if p.core.summary and p.core.summary.strip() != p.core.positioning.strip():
        lines.append(p.core.summary.strip())
    if p.core.years:
        lines.append(f"Years of relevant experience: {p.core.years}.")

    current = next((j for j in p.employment if j.current), None)
    if current:
        lines.append(f"Current role: {current.title} at {current.company}.")
    elif p.employment:
        latest = p.employment[0]
        lines.append(f"Most recent role: {latest.title} at {latest.company}.")

    return _section("Who I am", "\n".join(lines))


def what_i_want(p: Profile) -> str:
    prefs = p.prefs
    lines = [f"Target job titles: {_join(p.core.target_roles)}."]
    if p.core.seniority:
        lines.append(f"Level: {p.core.seniority}.")
    if prefs.work_modes:
        lines.append(f"Working pattern: {_join(prefs.work_modes)}.")
    if prefs.employment:
        lines.append(f"Contract type: {_join(prefs.employment)}.")
    if prefs.company_sizes:
        lines.append(f"Company size: {_join(prefs.company_sizes)}.")
    if prefs.salary_min or prefs.salary_max:
        low = prefs.salary_min or "open"
        high = prefs.salary_max or "open"
        lines.append(f"Salary expectation: {low} to {high} {prefs.currency}.")
    if prefs.earliest_start:
        lines.append(f"Earliest start: {prefs.earliest_start}.")
    if prefs.notice_period:
        lines.append(f"Notice period: {prefs.notice_period}.")
    return _section("What I am looking for", "\n".join(lines))


def hard_constraints(p: Profile) -> str:
    """Where I will work, and dealbreakers.

    This block exists because these are the constraints that quietly waste
    the most time when an assistant ignores them.
    """
    lines = []
    if p.prefs.locations:
        lines.append(f"I want to work in: {_join(p.prefs.locations)}.")
    if p.prefs.avoid_sectors:
        lines.append(f"Do not suggest roles in: {_join(p.prefs.avoid_sectors)}.")
    if p.prefs.dealbreakers:
        lines.append("Dealbreakers:")
        lines.append(_bullets(p.prefs.dealbreakers))
    return _section("Hard constraints", "\n".join(lines))


def evidence_bank(p: Profile, compact: bool = False) -> str:
    """The defensible-claims bank, grouped by theme."""
    chunks = []
    for group in p.evidence:
        items = [i for i in group.items if i.strip()]
        if not items:
            continue
        if compact:
            items = items[:4]
        chunks.append(f"**{group.group}**\n{_bullets(items)}")
    if not chunks:
        return ""
    return _section("My evidence bank", "\n\n".join(chunks))


def history(p: Profile) -> str:
    lines = []
    for job in p.employment:
        span = f"{job.start} to {'present' if job.current else (job.end or 'unknown')}"
        header = f"**{job.title}**, {job.company} ({span})"
        if job.location:
            header += f" - {job.location}"
        lines.append(header)
        if job.note:
            lines.append(job.note.strip())
        if job.bullets:
            lines.append(_bullets(job.bullets))
        lines.append("")
    for study in p.education:
        span = f"{study.start} to {study.end}" if study.start or study.end else ""
        bits = [b for b in [study.qualification, study.field, study.school, span] if b]
        lines.append("- " + ", ".join(bits))
    return _section("Employment and education", "\n".join(lines))


def independent_work(p: Profile) -> str:
    chunks = []
    for item in p.independent:
        head = f"**{item.name}**"
        if item.url:
            head += f" ({item.url})"
        body = [head]
        if item.description:
            body.append(item.description.strip())
        if item.bullets:
            body.append(_bullets(item.bullets))
        if item.tech:
            body.append(f"Built with: {_join(item.tech)}.")
        chunks.append("\n".join(body))
    if not chunks:
        return ""
    return _section("Independent and client work", "\n\n".join(chunks))


def technology_profile(p: Profile) -> str:
    """Grouped by how strong the claim actually is.

    An assistant given a flat skills list will happily describe a bootcamp
    module as commercial experience. Splitting the list stops that.
    """
    buckets: dict[str, list[str]] = {"production": [], "project": [], "training": [], "exposure": [], "never": []}
    for area in p.tech:
        if area.level in buckets and area.area.strip():
            label = area.area.strip()
            if area.description:
                label += f" - {area.description.strip()}"
            buckets[area.level].append(label)

    parts = []
    if buckets["production"]:
        parts.append(
            "**Commercial production experience** (safe to lead with):\n"
            + _bullets(buckets["production"])
        )
    if buckets["project"]:
        parts.append(
            "**Hands-on project experience** (real, but describe it as project work, "
            "not production experience):\n" + _bullets(buckets["project"])
        )
    if buckets["training"]:
        parts.append(
            "**Training or coursework only** (mention only if the role needs it, and "
            "say what it is):\n" + _bullets(buckets["training"])
        )
    if buckets["exposure"]:
        parts.append("**Exposure only** (usually leave out):\n" + _bullets(buckets["exposure"]))
    if buckets["never"]:
        parts.append("**Never claim these:**\n" + _bullets(buckets["never"]))

    if not parts:
        return ""
    return _section("Technology profile, by strength of claim", "\n\n".join(parts))


def accuracy_boundaries(p: Profile) -> str:
    rules = [b for b in p.boundaries if b.strip()]
    never = [t.area for t in p.tech if t.level == "never" and t.area.strip()]
    if never:
        rules.append(f"Do not claim experience with: {_join(never)}.")
    if not rules:
        return ""
    return _section(
        "Accuracy boundaries - these are absolute",
        "Every claim must be specific enough for me to defend in an interview.\n"
        + _bullets(rules)
        + "\n\nIf something would be useful but is not supported by the evidence above, "
        "leave it out and tell me what is missing. Do not fill the gap.",
    )


def style_rules(p: Profile) -> str:
    lines = []
    if p.style.english:
        lines.append(f"Use {p.style.english} English.")
    if p.style.tone:
        lines.append(p.style.tone.strip())
    lines.extend(r.strip() for r in p.style.rules if r.strip())
    if not lines:
        return ""
    return _section("How to write", _bullets(lines))


def document_rules(p: Profile) -> str:
    d = p.doc_prefs
    lines = [f"Keep the CV to {d.max_pages} page{'s' if d.max_pages != 1 else ''} unless the vacancy genuinely needs more."]
    if d.font:
        lines.append(f"House font is {d.font}.")
    if d.accent:
        lines.append(f"Accent colour is {d.accent}.")
    lines.append("Keep working links for email, portfolio and any relevant projects.")
    if d.notes:
        lines.append(d.notes.strip())
    return _section("Document rules", _bullets(lines))


# --------------------------------------------------------------------------
# advert block
# --------------------------------------------------------------------------
def advert_block(advert: str, application: Application | None) -> str:
    if application is not None:
        parts = [f"**{application.title}** at **{application.company}**"]
        if application.location:
            parts.append(f"Location: {application.location}")
        if application.work_mode:
            parts.append(f"Working pattern: {application.work_mode}")
        if application.salary:
            parts.append(f"Salary: {application.salary}")
        if application.url:
            parts.append(f"Advert: {application.url}")
        if application.key_requirements:
            parts.append("Key requirements:\n" + _bullets(application.key_requirements))
        body = application.description or application.summary
        if body:
            parts.append("\n" + body.strip())
        return _section("The vacancy", "\n".join(parts))
    if advert.strip():
        return _section("The vacancy", advert.strip())
    return ""


# --------------------------------------------------------------------------
# prompt kinds
# --------------------------------------------------------------------------
def build_hunt(p: Profile, brief: str, max_results: int) -> str:
    task = _clean(
        f"""
        ## Your task
        Search for **live, currently open vacancies** that fit the profile above, and
        return the {max_results} strongest matches.

        Work through it like this:
        1. Search job boards and, where you can, the employers' own careers pages.
        2. Discard anything that fails a hard constraint.
        3. For each remaining role, check what it actually asks for against my evidence.
        4. Rank by genuine fit, not by how well the advert is written.

        Rules:
        - Only include roles you have actually found. Do not invent a plausible vacancy,
          and do not pad the list to reach {max_results}.
        - Give the real advert URL. If you cannot produce a link you are confident in,
          say so in `concerns` rather than guessing at one.
        - If you cannot confirm a role is still open, say that in `concerns`.
        - `why_match` must name specific evidence from my bank, not restate the advert.
        - Be honest in `concerns`. A role I should skip is more useful than a role that
          wastes an afternoon.
        """
    )

    # Dedent first, then drop the schema in. Interpolating a column-0 block
    # into an indented template makes textwrap.dedent a no-op.
    output = _clean(
        """
        ## How to reply
        First, a short paragraph on what you searched and anything that surprised you.

        Then a single fenced ```json block containing an array in exactly this shape,
        and nothing else inside the fence:

        ```json
        __SCHEMA__
        ```

        I paste that block straight back into my tracker, so the keys must match
        exactly and the JSON must parse. Use "" for anything you do not know.
        """
    ).replace("__SCHEMA__", IMPORT_SCHEMA)

    return _assemble(
        "You are helping me find work. Be blunt about fit; I would rather lose a "
        "suggestion than chase a bad one.",
        who_i_am(p),
        what_i_want(p),
        hard_constraints(p),
        evidence_bank(p, compact=True),
        technology_profile(p),
        accuracy_boundaries(p),
        _section("Extra steer for this search", brief.strip()) if brief.strip() else "",
        task,
        output,
    )


def build_assess(p: Profile, advert: str, application: Application | None) -> str:
    task = _clean(
        """
        ## Your task
        Assess honestly whether this vacancy is worth my time.

        1. Pull out the five to eight requirements that actually matter, in the
           employer's own words where you can.
        2. For each one, say what evidence I have - quoting the relevant line from my
           bank - or say plainly that I have none.
        3. Flag anything the advert asks for that my accuracy boundaries prevent me
           from claiming.
        4. Check location and salary against my constraints.
        5. Finish with a verdict: apply, apply with caveats, or skip - and one sentence
           on why.

        Do not talk me into it. If the gaps are real, say so.
        """
    )
    return _assemble(
        "You are reviewing a job advert for me. Be direct and evidence-led.",
        who_i_am(p),
        hard_constraints(p),
        evidence_bank(p),
        technology_profile(p),
        accuracy_boundaries(p),
        advert_block(advert, application),
        task,
    )


def build_cv(p: Profile, advert: str, application: Application | None) -> str:
    task = _clean(
        """
        ## Your task
        Draft a CV for this specific vacancy.

        1. Identify the five to eight requirements that matter most.
        2. Choose only the evidence that speaks to them. Leave the rest out - this is a
           selection exercise, not a summary of everything I have done.
        3. Order sections and bullets so the strongest relevant evidence appears first.
        4. Rewrite the opening profile for this role.
        5. Where my background differs from the advert - a different stack, a different
           title - the CV states what I have done and lets it stand. Do not overstate
           it, and do not editorialise about the difference either. A CV is not the
           place to name what I lack; that belongs in the gaps list below, where I can
           decide what to do about it. Never write a sentence whose effect is to talk
           me out of the role.

        Then, separately from the CV, list:
        - which requirements you could not evidence, and
        - any claim you were tempted to make but left out because of my boundaries.
        """
    )
    output = _clean(
        """
        ## How to reply
        Give the CV as clean markdown I can paste into a document: name and contact
        details, a short profile, then sections in the order you have chosen. Use plain
        bullets. No tables, no columns, no ASCII art.

        Put the gaps list after the CV under a heading of its own.
        """
    )
    return _assemble(
        "You are drafting a tailored CV. Accuracy matters more than polish.",
        who_i_am(p),
        history(p),
        evidence_bank(p),
        independent_work(p),
        technology_profile(p),
        accuracy_boundaries(p),
        style_rules(p),
        document_rules(p),
        advert_block(advert, application),
        task,
        output,
    )


def build_letter(p: Profile, advert: str, application: Application | None) -> str:
    task = _clean(
        """
        ## Your task
        Draft a cover letter for this vacancy.

        Keep it short - three or four paragraphs. Open with why this role, not with a
        summary of my CV. Use two or three concrete examples from my evidence bank and
        say what came of them. If there is an obvious mismatch, address it in one
        sentence and move on.

        Express interest in the work itself. Do not invent enthusiasm for the company
        or the sector unless I have given you a reason for it above.

        Use the recipient's full name if the advert gives one, and the matching formal
        sign-off. If there is no name, say which greeting you have used and why.
        """
    )
    return _assemble(
        "You are drafting a cover letter.",
        who_i_am(p),
        evidence_bank(p),
        independent_work(p),
        accuracy_boundaries(p),
        style_rules(p),
        advert_block(advert, application),
        task,
    )


def build_interview(p: Profile, advert: str, application: Application | None) -> str:
    task = _clean(
        """
        ## Your task
        Prepare me for the interview.

        1. Ten likely questions for this specific role, technical and behavioural, in
           the order they are likely to come up.
        2. For each, the evidence from my bank I should reach for - named, not
           paraphrased - and the shape of a good answer in two or three lines.
        3. The three questions I am most likely to struggle with, given the gaps
           between the advert and my evidence, and how to answer each honestly
           without either bluffing or apologising.
        4. Five questions worth asking them, based on what the advert does not say.
        """
    )
    return _assemble(
        "You are preparing me for a job interview.",
        who_i_am(p),
        evidence_bank(p),
        technology_profile(p),
        accuracy_boundaries(p),
        advert_block(advert, application),
        task,
    )


TAILOR_SCHEMA = """{
  "headline": "the job title I should put under my name",
  "summary": "2-3 sentences opening my CV, written for this role",
  "lead_themes": ["exact names of the evidence themes that should come first"],
  "emphasise": ["exact opening words of the evidence lines that matter most here"]
}"""


def build_tailor(p: Profile, advert: str, application: Application | None) -> str:
    """Short round trip: only the judgement, not the document.

    The CV itself is assembled locally from the evidence bank. This asks only
    for the parts a language model is genuinely better at - a role-specific
    opening paragraph, and which evidence should lead.
    """
    themes = [g.group for g in p.evidence if any(i.strip() for i in g.items)]

    task = _clean(
        """
        ## Your task
        I build the CV myself from the evidence bank above. I only need the
        judgement calls:

        1. Which of my evidence themes should lead for this role, in order.
        2. Which specific evidence lines matter most here.
        3. A two or three sentence opening paragraph written for this vacancy.
        4. The job title to put under my name.

        The opening paragraph is the only prose you write. It must not contain
        a claim that is not supported above, and it must respect my accuracy
        boundaries. Do not write the CV, and do not rewrite my evidence lines -
        I need them quoted well enough to match, not improved.
        """
    )

    output = _clean(
        """
        ## How to reply
        A single fenced ```json block, nothing else inside the fence:

        ```json
        __SCHEMA__
        ```

        Use the exact theme names and the exact opening words of my evidence
        lines, so my CV builder can match them. Then, outside the fence, tell me
        in one or two lines what the advert asks for that I cannot evidence.
        """
    ).replace("__SCHEMA__", TAILOR_SCHEMA)

    return _assemble(
        "You are helping me tailor a CV that I assemble myself.",
        who_i_am(p),
        _section("My evidence themes", _bullets(themes)),
        evidence_bank(p),
        technology_profile(p),
        accuracy_boundaries(p),
        style_rules(p),
        advert_block(advert, application),
        task,
        output,
    )


BUILDERS = {
    "hunt": lambda p, req, app: build_hunt(p, req.brief, req.max_results),
    "assess": lambda p, req, app: build_assess(p, req.advert, app),
    "cv": lambda p, req, app: build_cv(p, req.advert, app),
    "letter": lambda p, req, app: build_letter(p, req.advert, app),
    "interview": lambda p, req, app: build_interview(p, req.advert, app),
    "tailor": lambda p, req, app: build_tailor(p, req.advert, app),
}


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def build(profile: Profile, request: Any, application: Application | None = None) -> dict[str, Any]:
    builder = BUILDERS.get(request.kind)
    if builder is None:
        raise ValueError(f"Unknown prompt kind: {request.kind}")

    prompt = builder(profile, request, application)

    if request.include_boundaries and "Accuracy boundaries" not in prompt:
        extra = accuracy_boundaries(profile)
        if extra:
            prompt = _assemble(prompt, extra)

    return {
        "kind": request.kind,
        "prompt": prompt,
        "characters": len(prompt),
        "warnings": _warnings(profile, request),
    }


def _warnings(p: Profile, request: Any) -> list[str]:
    out: list[str] = []
    state = p.completeness()
    if state["percent"] < 60:
        out.append(
            f"Profile is {state['percent']}% complete. Missing: "
            + ", ".join(state["missing"][:4])
            + ". The prompt will be thin until those are filled in."
        )
    if not p.boundaries:
        out.append(
            "No accuracy boundaries set. Nothing is stopping a draft from overclaiming."
        )
    if request.kind == "hunt" and not p.core.target_roles:
        out.append("No target job titles set, so the search has nothing specific to look for.")
    if request.kind in {"assess", "cv", "letter", "interview"} and not (
        request.advert.strip() or request.application_id
    ):
        out.append("No job advert supplied, so this prompt is generic.")
    return out
