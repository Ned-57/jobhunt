"""Reads an assistant's reply back into tracked applications.

The hunt prompt asks for a fenced ```json block. Assistants mostly comply,
but not always cleanly, so this is deliberately forgiving about what wraps
the JSON while being strict about what it accepts as a job.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .models import Application, now_iso

FENCED = re.compile(r"```(?:json|JSON)?\s*(.+?)```", re.DOTALL)

# Field aliases, because assistants paraphrase key names under pressure.
ALIASES = {
    "job_title": "title",
    "role": "title",
    "position": "title",
    "employer": "company",
    "company_name": "company",
    "organisation": "company",
    "organization": "company",
    "link": "url",
    "job_url": "url",
    "apply_url": "url",
    "advert": "url",
    "city": "location",
    "mode": "work_mode",
    "workmode": "work_mode",
    "working_pattern": "work_mode",
    "remote": "work_mode",
    "date_posted": "posted",
    "posted_date": "posted",
    "published": "posted",
    "compensation": "salary",
    "pay": "salary",
    "description": "summary",
    "overview": "summary",
    "requirements": "key_requirements",
    "key_requirement": "key_requirements",
    "must_haves": "key_requirements",
    "match": "why_match",
    "why": "why_match",
    "fit": "why_match",
    "risks": "concerns",
    "gaps": "concerns",
    "caveats": "concerns",
}

ALLOWED = {
    "title", "company", "location", "work_mode", "url", "posted", "salary",
    "summary", "key_requirements", "why_match", "concerns", "source", "description",
}


class ImportError_(ValueError):
    """Raised when nothing usable could be found in the pasted text."""


def extract_json(text: str) -> list[dict[str, Any]]:
    """Pull the first JSON array of objects out of arbitrary reply text."""
    candidates: list[str] = []

    for block in FENCED.findall(text):
        candidates.append(block.strip())

    # Fall back to the outermost bracketed span in the raw text.
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        parsed = _try_parse(candidate)
        if parsed is not None:
            return parsed

    raise ImportError_(
        "No JSON array found. Paste the whole reply, including the ```json block."
    )


def _try_parse(candidate: str) -> list[dict[str, Any]] | None:
    try:
        data = json.loads(candidate)
    except ValueError:
        # A trailing comma is the single most common failure; worth one retry.
        cleaned = re.sub(r",(\s*[}\]])", r"\1", candidate)
        try:
            data = json.loads(cleaned)
        except ValueError:
            return None
    if isinstance(data, dict):
        for key in ("jobs", "results", "vacancies", "roles", "matches"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        return None
    rows = [row for row in data if isinstance(row, dict)]
    return rows or None


def normalise(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, value in row.items():
        key = ALIASES.get(str(raw_key).strip().lower().replace(" ", "_"),
                          str(raw_key).strip().lower().replace(" ", "_"))
        if key not in ALLOWED:
            continue
        out[key] = value

    # description doubles as summary when only one was given
    if out.get("description") and not out.get("summary"):
        out["summary"] = out["description"]

    reqs = out.get("key_requirements")
    if isinstance(reqs, str):
        out["key_requirements"] = [r.strip(" -•") for r in reqs.split("\n") if r.strip()]
    elif isinstance(reqs, list):
        out["key_requirements"] = [str(r).strip() for r in reqs if str(r).strip()]
    else:
        out["key_requirements"] = []

    mode = str(out.get("work_mode", "")).strip().lower()
    if mode in {"true", "yes"}:
        mode = "remote"
    elif mode in {"false", "no"}:
        mode = "onsite"
    for known in ("remote", "hybrid", "onsite", "on-site"):
        if known in mode:
            mode = "onsite" if known == "on-site" else known
            break
    out["work_mode"] = mode

    for key in ("title", "company", "location", "url", "posted", "salary",
                "summary", "why_match", "concerns", "source"):
        out[key] = str(out.get(key, "") or "").strip()

    return out


# Phrases lifted straight from IMPORT_SCHEMA. An assistant that echoes the
# template instead of filling it in produces rows that parse perfectly and are
# entirely meaningless, so they get dropped rather than tracked.
TEMPLATE_MARKERS = (
    "exact job title from the advert",
    "employer name",
    "direct link to the advert you actually found",
    "two sentences on what the role actually involves",
    "which of my evidence lines up",
    "the 5-8 requirements that matter most",
    "city, country - or remote",
    "remote | hybrid | onsite",
    "as advertised, otherwise",
    "yyyy-mm-dd if stated",
)


def is_template(data: dict[str, Any]) -> bool:
    blob = " ".join([
        str(data.get(k, "")) for k in ("title", "company", "url", "summary", "why_match")
    ] + [str(r) for r in data.get("key_requirements", [])]).lower()
    return any(marker in blob for marker in TEMPLATE_MARKERS)


def to_applications(text: str, existing: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse `text` and return new applications plus a report of what happened."""
    rows = extract_json(text)

    seen_urls = {str(a.get("url", "")).strip().lower() for a in existing if a.get("url")}
    seen_pairs = {
        (str(a.get("title", "")).strip().lower(), str(a.get("company", "")).strip().lower())
        for a in existing
    }

    created: list[Application] = []
    skipped: list[str] = []
    duplicates = 0
    templates = 0

    for row in rows:
        data = normalise(row)
        if not data["title"] or not data["company"]:
            skipped.append("A row was missing a title or company and was dropped.")
            continue
        if is_template(data):
            templates += 1
            continue

        url_key = data["url"].lower()
        pair_key = (data["title"].lower(), data["company"].lower())
        if (url_key and url_key in seen_urls) or pair_key in seen_pairs:
            duplicates += 1
            continue

        app = Application(
            id="",  # assigned by the API layer
            title=data["title"],
            company=data["company"],
            location=data["location"],
            work_mode=data["work_mode"],
            url=data["url"],
            source=data["source"] or "AI search",
            salary=data["salary"],
            summary=data["summary"],
            key_requirements=data["key_requirements"],
            why_match=data["why_match"],
            concerns=data["concerns"],
            posted=data["posted"],
            stage="saved",
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        created.append(app)
        if url_key:
            seen_urls.add(url_key)
        seen_pairs.add(pair_key)

    if templates:
        skipped.append(
            f"{templates} row(s) were the example template rather than real vacancies, "
            "and were dropped. Ask the assistant to fill the schema in, not echo it."
        )

    return {
        "applications": created,
        "found": len(rows),
        "imported": len(created),
        "duplicates": duplicates,
        "templates": templates,
        "skipped": skipped,
    }
