"""Write a CV as a .docx, with no third-party dependency.

A .docx is a zip of XML parts, so the standard library is enough. The point of
producing one rather than a PDF is that it stays editable: the last pass on a
CV is always by hand, and Word or ONLYOFFICE is where that happens.

Styling follows the house style on the profile - Calibri, a navy accent, and a
rule under each section heading. Links are real hyperlink relationships rather
than blue text, because a CV whose links do not work is worse than one without
any.
"""
from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

from .cvgen import CvDocument

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Word measures in twentieths of a point, and page width in the same units.
# A4 with 15mm side margins leaves this much text width.
TEXT_WIDTH_TWIPS = 9639

URL_RE = re.compile(r"^(https?://|www\.)", re.I)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _hex(colour: str) -> str:
    return (colour or "#1F3864").lstrip("#").upper()[:6] or "1F3864"


# --------------------------------------------------------------------------
# runs
# --------------------------------------------------------------------------
def _run(text: str, *, bold=False, size=21, colour=None, caps=False,
         italic=False, spacing=None) -> str:
    props = []
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    if colour:
        props.append(f'<w:color w:val="{_hex(colour)}"/>')
    if caps:
        props.append("<w:caps/>")
    if spacing:
        props.append(f'<w:spacing w:val="{spacing}"/>')
    props.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    return (f"<w:r><w:rPr>{''.join(props)}</w:rPr>"
            f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>')


def _rich(text: str, *, size=21, colour=None) -> str:
    """Convert **bold** markers into real bold runs."""
    out, last = [], 0
    for match in BOLD_RE.finditer(text):
        if match.start() > last:
            out.append(_run(text[last:match.start()], size=size, colour=colour))
        out.append(_run(match.group(1), bold=True, size=size, colour=colour))
        last = match.end()
    if last < len(text):
        out.append(_run(text[last:], size=size, colour=colour))
    return "".join(out) or _run(text, size=size, colour=colour)


def _para(runs: str, *, style=None, space_after=60, space_before=0,
          border=None, tabs=False, indent=None) -> str:
    props = []
    if style:
        props.append(f'<w:pStyle w:val="{style}"/>')
    if tabs:
        props.append(f'<w:tabs><w:tab w:val="right" w:pos="{TEXT_WIDTH_TWIPS}"/></w:tabs>')
    if indent:
        props.append(f'<w:ind w:left="{indent}" w:hanging="{indent}"/>')
    if border:
        props.append(
            '<w:pBdr><w:bottom w:val="single" w:sz="8" w:space="2" '
            f'w:color="{_hex(border)}"/></w:pBdr>'
        )
    props.append(f'<w:spacing w:before="{space_before}" w:after="{space_after}" '
                 f'w:line="240" w:lineRule="auto"/>')
    return f"<w:p><w:pPr>{''.join(props)}</w:pPr>{runs}</w:p>"


def _bullet(runs: str) -> str:
    return (
        "<w:p><w:pPr><w:numPr><w:ilvl w:val=\"0\"/><w:numId w:val=\"1\"/></w:numPr>"
        '<w:spacing w:before="0" w:after="40" w:line="240" w:lineRule="auto"/>'
        f"</w:pPr>{runs}</w:p>"
    )


# --------------------------------------------------------------------------
# hyperlinks
# --------------------------------------------------------------------------
class Links:
    """Collects external relationships as the document is built."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []   # (rId, target)

    def add(self, target: str) -> str:
        if EMAIL_RE.match(target):
            target = "mailto:" + target
        elif target.lower().startswith("www."):
            target = "https://" + target
        rid = f"rIdLink{len(self.items) + 1}"
        self.items.append((rid, target))
        return rid

    def link_run(self, text: str, target: str, *, size=21, colour="1F3864") -> str:
        rid = self.add(target)
        run = (f"<w:r><w:rPr><w:color w:val=\"{_hex(colour)}\"/>"
               '<w:u w:val="single"/>'
               f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>'
               f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>')
        return f'<w:hyperlink r:id="{rid}">{run}</w:hyperlink>'

    def rels_xml(self) -> str:
        entries = "".join(
            f'<Relationship Id="{rid}" '
            f'Type="{R}/hyperlink" Target="{escape(target, {chr(34): "&quot;"})}" '
            f'TargetMode="External"/>'
            for rid, target in self.items
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rIdStyles" Type="{R}/styles" Target="styles.xml"/>'
            f'<Relationship Id="rIdNum" Type="{R}/numbering" Target="numbering.xml"/>'
            f"{entries}</Relationships>"
        )


# --------------------------------------------------------------------------
# body
# --------------------------------------------------------------------------
def _contact_line(doc: CvDocument, links: Links) -> str:
    runs = []
    for index, item in enumerate(doc.contact):
        if index:
            runs.append(_run("   ·   ", size=19, colour="666666"))
        if EMAIL_RE.match(item) or URL_RE.match(item):
            # Show a readable label, link the full target - a visible URL that
            # does not match where it goes is the one thing worse than no link.
            label = re.sub(r"^https?://(www\.)?", "", item).rstrip("/")
            runs.append(links.link_run(label, item, size=19))
        else:
            runs.append(_run(item, size=19, colour="444444"))
    return _para("".join(runs), space_after=180)


def _body(doc: CvDocument, links: Links, accent: str, font_pt: int) -> str:
    size = font_pt * 2                       # half-points
    parts = [
        _para(_run(doc.name, bold=True, size=50, colour=accent), space_after=20),
    ]
    if doc.headline:
        parts.append(_para(_run(doc.headline, bold=True, size=27, colour="333333"),
                           space_after=80))
    if doc.contact:
        parts.append(_contact_line(doc, links))

    if doc.summary:
        parts.append(_heading("Profile", accent))
        parts.append(_para(_run(doc.summary, size=size), space_after=120))

    for section in doc.sections:
        parts.append(_heading(section.heading, accent))

        for line in section.lines:
            if section.kind == "skills":
                parts.append(_para(_rich(line.text, size=size), space_after=40))
            else:
                parts.append(_bullet(_rich(line.text, size=size)))

        for entry in section.entries:
            title = entry.get("title", "")
            company = entry.get("company", "")
            dates = entry.get("dates", "")

            head = [_run(title, bold=True, size=size + 1)]
            if company:
                # Independent work carries its link here rather than a company.
                if URL_RE.match(company) or EMAIL_RE.match(company):
                    head.append(_run(", ", size=size))
                    head.append(links.link_run(
                        re.sub(r"^https?://(www\.)?", "", company).rstrip("/"),
                        company, size=size))
                else:
                    head.append(_run(", " + company, size=size))
            if dates:
                head.append(_run("\t", size=size))
                if URL_RE.match(dates):
                    head.append(links.link_run(
                        re.sub(r"^https?://(www\.)?", "", dates).rstrip("/"),
                        dates, size=19))
                else:
                    head.append(_run(dates, size=19, colour="555555"))
            parts.append(_para("".join(head), tabs=True, space_after=20, space_before=80))

            if entry.get("note"):
                parts.append(_para(_run(entry["note"], size=size), space_after=40))
            for bullet in entry.get("bullets", []):
                parts.append(_bullet(_rich(bullet, size=size)))

    return "".join(parts)


def _heading(text: str, accent: str) -> str:
    return _para(
        _run(text.upper(), bold=True, size=19, colour=accent, caps=True, spacing=20),
        border=accent, space_before=200, space_after=80,
    )


# --------------------------------------------------------------------------
# package parts
# --------------------------------------------------------------------------
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
    "</Types>"
)

ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    f'<Relationship Id="rId1" Type="{R}/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)

NUMBERING = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:numbering xmlns:w="{W}">'
    '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
    '<w:lvlText w:val="•"/><w:lvlJc w:val="left"/>'
    '<w:pPr><w:ind w:left="340" w:hanging="220"/></w:pPr>'
    '<w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol" w:hint="default"/></w:rPr>'
    "</w:lvl></w:abstractNum>"
    '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
    "</w:numbering>"
)


def _styles(font: str, font_pt: int) -> str:
    size = font_pt * 2
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W}">'
        "<w:docDefaults><w:rPrDefault><w:rPr>"
        f'<w:rFonts w:ascii="{escape(font)}" w:hAnsi="{escape(font)}" w:cs="{escape(font)}"/>'
        f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
        "</w:rPr></w:rPrDefault>"
        "<w:pPrDefault><w:pPr>"
        '<w:spacing w:before="0" w:after="60" w:line="240" w:lineRule="auto"/>'
        "</w:pPr></w:pPrDefault></w:docDefaults>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style>'
        "</w:styles>"
    )


def _document(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}" xmlns:r="{R}">'
        f"<w:body>{body}"
        # A4 portrait, 14mm top/bottom and 15mm sides, matching the print CSS.
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="794" w:right="850" w:bottom="794" w:left="850" '
        'w:header="0" w:footer="0" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def build_docx(doc: CvDocument, *, font: str = "Calibri",
               accent: str = "#1F3864", font_pt: int = 10) -> bytes:
    links = Links()
    body = _body(doc, links, _hex(accent), font_pt)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("word/document.xml", _document(body))
        archive.writestr("word/_rels/document.xml.rels", links.rels_xml())
        archive.writestr("word/styles.xml", _styles(font, font_pt))
        archive.writestr("word/numbering.xml", NUMBERING)
    return buffer.getvalue()


def filename_for(doc: CvDocument, company: str = "") -> str:
    def slug(text: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", str(text or "")).strip("_")

    parts = [slug(doc.name) or "CV", "CV"]
    if company:
        parts.append(slug(company))
    if doc.headline:
        parts.append(slug(doc.headline))
    return "_".join(p for p in parts if p)[:120] + ".docx"
