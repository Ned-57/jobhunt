"""Reading a profile out of CVs the user has already written.

Filling in ten steps from a blank page is the worst way to start. Most people
arrive with several tailored CVs already on disk, and those contain better
prose than anyone writes into a form. This pulls the reusable parts out of
them - contact details, technologies, and the bullets themselves - and offers
them for review.

Nothing here writes to a profile. Every candidate is returned for the user to
accept or reject, because only they know which claims are still true.
"""
from __future__ import annotations

import html
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Iterable

from .custard import sanitise, strip_bullet
from .taxonomy import display_terms, tokens

MAX_FILES = 10
MAX_BYTES = 5 * 1024 * 1024

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
PHONE_RE = re.compile(r"\+\d[\d ()-]{7,}\d")
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?[\w-]+\.[\w.-]+(?:/[\w./#?=&-]*)?")

# Headings tell us nothing; they are not evidence.
HEADING_RE = re.compile(
    r"^(profile|summary|core skills|key skills|skills|education|training|contact|"
    r"experience|professional experience|employment|selected|independent|projects?|"
    r"interests|references|languages|ways of working|technical)\b", re.I
)

# A skills row reads as a list: a short label then separator-heavy content.
LIST_LABEL = re.compile(r"^[A-Z][\w &/'-]{0,30}[:–—]\s")
SEPARATORS = "·•|;–—"


@dataclass
class Candidate:
    text: str
    source: str
    technologies: list[str] = field(default_factory=list)
    words: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "source": self.source,
                "technologies": self.technologies, "words": self.words}


def docx_lines(data: bytes, name: str) -> list[str]:
    """Paragraph text from a .docx. A docx is a zip of XML - no dependency."""
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
    except (zipfile.BadZipFile, KeyError, OSError, UnicodeDecodeError):
        return []
    xml = xml.replace("</w:p>", "\n").replace("<w:tab/>", "\t").replace("<w:br/>", "\n")
    text = html.unescape(re.sub(r"<[^>]+>", "", xml))
    return [sanitise(line) for line in text.split("\n") if line.strip()]


def looks_like_list(line: str) -> bool:
    if sum(line.count(c) for c in SEPARATORS) >= 3:
        return True
    if LIST_LABEL.match(line) and line.count(",") >= 3:
        return True
    return line.count(",") >= 5 and not line.rstrip().endswith(".")


def is_evidence(line: str) -> bool:
    """A sentence describing work done, not a heading or a skills row."""
    if not (45 <= len(line) <= 400):
        return False
    if HEADING_RE.match(line) or line.isupper() or looks_like_list(line):
        return False
    if "@" in line or line.count("|") >= 2 or line.startswith("http"):
        return False
    return bool(re.search(r"[a-z]{3,}\s+[a-z]{3,}", line))


def similarity(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def contact_from(lines: Iterable[str]) -> dict[str, str]:
    """Contact details, which sit in the first few lines of every CV."""
    blob = "\n".join(list(lines)[:8])
    found: dict[str, str] = {}

    email = EMAIL_RE.search(blob)
    if email:
        found["email"] = email.group(0)
    phone = PHONE_RE.search(blob)
    if phone:
        found["phone"] = re.sub(r"\s+", " ", phone.group(0)).strip()

    for url in URL_RE.findall(blob):
        low = url.lower()
        if "@" in url or low.endswith((".com", ".co.uk")) and "." not in low.split(".")[0]:
            pass
        if "linkedin." in low:
            found.setdefault("linkedin", _https(url))
        elif "github." in low:
            found.setdefault("github", _https(url))
        elif not any(d in low for d in ("gmail.", "outlook.", "hotmail.", "yahoo.")) \
                and "." in low and not low.startswith("www.w3"):
            found.setdefault("portfolio", _https(url))

    # The name is the first line of essentially every CV.
    for line in list(lines)[:3]:
        words = line.split()
        if 1 < len(words) <= 4 and not any(c in line for c in "@|:") \
                and all(w[:1].isupper() for w in words if w[:1].isalpha()):
            found["name"] = line
            break
    return found


def _https(url: str) -> str:
    return url if url.startswith("http") else "https://" + url


def mine(files: list[tuple[str, bytes]], known: Iterable[str] = (),
         threshold: float = 0.55) -> dict[str, Any]:
    """Pull candidates out of uploaded CVs.

    `known` is text already in the profile, so nothing already recorded comes
    back as a suggestion.
    """
    known_prints = [frozenset(tokens(k)) for k in known if k and k.strip()]
    seen: list[frozenset[str]] = []
    candidates: list[Candidate] = []
    contact: dict[str, str] = {}
    technologies: dict[str, int] = {}
    read, skipped = 0, []

    for name, data in files[:MAX_FILES]:
        if len(data) > MAX_BYTES:
            skipped.append(f"{name} is larger than 5 MB and was skipped.")
            continue
        lines = docx_lines(data, name)
        if not lines:
            skipped.append(f"{name} could not be read as a .docx and was skipped.")
            continue
        read += 1

        for key, value in contact_from(lines).items():
            contact.setdefault(key, value)

        for line in lines:
            for term in display_terms(line, limit=12):
                technologies[term] = technologies.get(term, 0) + 1

            if not is_evidence(line):
                continue
            text = strip_bullet(line)
            if not text:
                continue
            print_ = frozenset(tokens(text))
            if any(similarity(print_, other) >= threshold for other in seen):
                continue
            seen.append(print_)
            if any(similarity(print_, other) >= threshold for other in known_prints):
                continue
            candidates.append(Candidate(
                text=text, source=name,
                technologies=display_terms(text, limit=6),
                words=len(text.split()),
            ))

    candidates.sort(key=lambda c: (-len(c.technologies), -c.words))
    ranked_tech = [t for t, _ in sorted(technologies.items(), key=lambda kv: -kv[1])][:30]

    return {
        "files_read": read,
        "skipped": skipped,
        "contact": contact,
        "technologies": ranked_tech,
        "candidates": [c.as_dict() for c in candidates],
    }
