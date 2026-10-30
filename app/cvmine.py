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

import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Iterable
from xml.etree import ElementTree

from .custard import sanitise, strip_bullet
from .taxonomy import display_terms, tokens

MAX_FILES = 10
MAX_BYTES = 5 * 1024 * 1024

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
# International, or a UK number written the way people actually write one.
PHONE_RE = re.compile(r"\+\d[\d ()-]{7,}\d|\b0\d{2,4}[ -]?\d{3,4}[ -]?\d{3,4}\b")
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?[\w-]+\.[\w.-]+(?:/[\w./#?=&-]*)?")
# Text is shaped like an address more often than it is one: "Node.js", "ASP.NET".
SITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?!js$|py$)[a-z]{2,}(?:/\S*)?"
)
LINKEDIN_RE = re.compile(r"linkedin\.com/(?:in|pub)/[\w%-]+", re.I)
GITHUB_RE = re.compile(r"github\.com/([\w-]+)(/[\w.-]+)?", re.I)
NOT_A_PORTFOLIO = ("linkedin.", "github.", "gmail.", "outlook.", "hotmail.", "yahoo.", "www.w3")

WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
RELS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
DRAWING = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
COMPAT = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"

# Formatting holds tab stops that look like tabs, and a Fallback repeats the
# text box beside it for older readers.
SKIPPED = {WORD + "pPr", WORD + "rPr", COMPAT + "Fallback"}
EXTRA_PART = re.compile(r"word/(header|footer)\d*\.xml")
FIELD_LINK = re.compile(r'HYPERLINK\s+"([^"]+)"')

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


@dataclass
class Paragraph:
    text: str = ""
    links: list[str] = field(default_factory=list)


def _paragraphs(root: ElementTree.Element, targets: dict[str, str]) -> list[Paragraph]:
    """Every paragraph in one XML part, in reading order.

    Walking the XML rather than stripping its tags is the point. A drawing
    anchored to a paragraph stores its position as element text, so stripping
    tags turns <wp:align>right</wp:align> into "right" on the end of whatever
    shares that paragraph - usually the name. Links are resolved because a CV
    tends to show the word "LinkedIn", not the address behind it.
    """
    found: list[Paragraph] = []

    def read(node: ElementTree.Element, para: Paragraph | None) -> None:
        for child in node:
            tag = child.tag
            if tag in SKIPPED:
                continue
            if tag == WORD + "p":
                # Text boxes nest paragraphs inside paragraphs. Taking the slot
                # first keeps the outer one ahead of what it contains.
                inner = Paragraph()
                found.append(inner)
                read(child, inner)
            elif para is None:
                read(child, None)
            elif tag == WORD + "t":
                para.text += child.text or ""
            elif tag == WORD + "tab":
                para.text += "\t"
            elif tag in (WORD + "br", WORD + "cr"):
                para.text += "\n"
            elif tag == WORD + "instrText":
                para.links.extend(FIELD_LINK.findall(child.text or ""))
            else:
                if tag in (WORD + "hyperlink", DRAWING + "hlinkClick"):
                    target = targets.get(child.get(RELS + "id", ""))
                    if target:
                        para.links.append(target)
                read(child, para)

    read(root, None)
    return found


def _link_targets(archive: zipfile.ZipFile, part: str) -> dict[str, str]:
    """Where each link in a part points, keyed by its relationship id."""
    folder, _, name = part.rpartition("/")
    try:
        root = ElementTree.fromstring(archive.read(f"{folder}/_rels/{name}.rels"))
    except KeyError:
        return {}
    return {rel.get("Id", ""): rel.get("Target", "")
            for rel in root.iter(PACKAGE_REL)
            if rel.get("Type", "").endswith("/hyperlink")}


def read_docx(data: bytes) -> list[Paragraph]:
    """Paragraphs of a .docx, one per line. A docx is a zip of XML - no dependency.

    Headers come first because contact details often live there.
    """
    raw: list[Paragraph] = []
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            extras = sorted(n for n in archive.namelist() if EXTRA_PART.fullmatch(n))
            parts = ([n for n in extras if "header" in n] + ["word/document.xml"]
                     + [n for n in extras if "footer" in n])
            for part in parts:
                root = ElementTree.fromstring(archive.read(part))
                raw.extend(_paragraphs(root, _link_targets(archive, part)))
    except (zipfile.BadZipFile, KeyError, OSError, ElementTree.ParseError):
        return []

    tidy: list[Paragraph] = []
    for para in raw:
        lines = [line for line in map(sanitise, para.text.split("\n")) if line]
        # A linked icon has no text, but its link still counts.
        if not lines and para.links:
            tidy.append(Paragraph(links=para.links))
        for index, line in enumerate(lines):
            tidy.append(Paragraph(line, para.links if index == 0 else []))
    return tidy


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


def _urls(paragraphs: list[Paragraph]) -> list[str]:
    """Real links first, then anything typed out as an address."""
    links = [link for para in paragraphs for link in para.links
             if link.lower().startswith("http")]
    text = EMAIL_RE.sub(" ", "\n".join(para.text for para in paragraphs))
    return links + URL_RE.findall(text)


def _github(urls: list[str]) -> str:
    """A profile link if there is one, otherwise the owner of the first repo."""
    matches = [m for m in map(GITHUB_RE.search, urls) if m]
    for match in matches:
        if not match.group(2):
            return "https://github.com/" + match.group(1)
    return "https://github.com/" + matches[0].group(1) if matches else ""


def _portfolio(paragraphs: list[Paragraph]) -> str:
    """The first ordinary website, ignoring profiles and webmail."""
    real = {link for para in paragraphs for link in para.links}
    for url in _urls(paragraphs):
        low = url.lower()
        if any(skip in low for skip in NOT_A_PORTFOLIO):
            continue
        if url in real or SITE_RE.fullmatch(url):
            return _https(url)
    return ""


def contact_from(paragraphs: list[Paragraph]) -> dict[str, str]:
    """Contact details. These sit at the top of a CV, though a profile link may not."""
    top = paragraphs[:8]
    blob = "\n".join(para.text for para in top)
    found: dict[str, str] = {}

    addresses = [link.split(":", 1)[1].split("?")[0] for para in top for link in para.links
                 if link.lower().startswith("mailto:")]
    email = EMAIL_RE.search(blob) or EMAIL_RE.search(" ".join(addresses))
    if email:
        found["email"] = email.group(0)
    phone = PHONE_RE.search(blob)
    if phone:
        found["phone"] = re.sub(r"\s+", " ", phone.group(0)).strip()

    # The whole document for these: a project link further down can still be
    # the only place a CV gives the address.
    urls = _urls(paragraphs)
    linkedin = next((url for url in urls if LINKEDIN_RE.search(url)), "")
    if linkedin:
        found["linkedin"] = _https(linkedin.split("?")[0].rstrip("/"))
    github = _github(urls)
    if github:
        found["github"] = github
    # Only near the top. Further down, a link is a project rather than a portfolio.
    portfolio = _portfolio(top)
    if portfolio:
        found["portfolio"] = portfolio

    # The name is the first line of essentially every CV.
    for line in [para.text for para in paragraphs if para.text][:3]:
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
        paragraphs = read_docx(data)
        lines = [para.text for para in paragraphs if para.text]
        if not lines:
            skipped.append(f"{name} could not be read as a .docx and was skipped.")
            continue
        read += 1

        for key, value in contact_from(paragraphs).items():
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
