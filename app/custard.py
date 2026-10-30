"""Cleaning text that came from somewhere else.

People fill this app in by pasting: out of Word, out of a PDF job advert, out
of Notepad, out of another CV. That text arrives carrying smart quotes,
non-breaking spaces, zero-width joiners, CRLF line endings and bullet glyphs,
none of which should reach the model - or a CV.

Two separate jobs, deliberately kept apart:

* `sanitise` normalises characters and whitespace. It never changes the shape
  of the data, so it is safe to run over every string in a payload.
* `SmartBulletList` turns a pasted block of bullet lines into a real list. It
  is applied only to fields that are declared as lists, because guessing at
  that from the text alone would split a perfectly good paragraph in half.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Any

from pydantic import BeforeValidator

# Characters that look like punctuation but are not the ASCII ones. Word and
# most PDF viewers substitute these silently.
REPLACEMENTS = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",   # single quotes
    "“": '"', "”": '"', "„": '"', "‟": '"',   # double quotes
    " ": " ", " ": " ", " ": " ", " ": " ",   # odd spaces
    "　": " ", " ": " ", " ": " ", " ": " ",
    "–": "-", "—": "-", "‒": "-", "―": "-",   # dashes
    "…": "...",                                              # ellipsis
    "´": "'", "ʼ": "'", "`": "'",
    "ﬁ": "fi", "ﬂ": "fl",                               # PDF ligatures
}

# Invisible characters that survive a copy and break string comparison later.
INVISIBLE = dict.fromkeys(map(ord, (
    "​‌‍⁠﻿­᠎"
)))

# Leading glyphs used as bullets in every editor there has ever been.
BULLET_GLYPHS = "*-•▪●◦○■‣⁃›·∙+–—※▸►→"
BULLET_PREFIX = re.compile(
    r"^\s*(?:[" + re.escape(BULLET_GLYPHS) + r"]+|\d{1,2}[.)])\s+"
)

CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitise(value: str) -> str:
    """Normalise pasted text without changing what it says.

    Safe to run over any string: it fixes characters and whitespace only.
    """
    if not isinstance(value, str) or not value:
        return value

    # NFKC folds full-width and compatibility forms back to plain ASCII where
    # an equivalent exists, which catches a lot of PDF output.
    text = unicodedata.normalize("NFKC", value)
    text = text.translate(INVISIBLE)
    for bad, good in REPLACEMENTS.items():
        text = text.replace(bad, good)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = CONTROL.sub("", text)
    text = text.replace("\t", " ")

    # Collapse runs of spaces, but keep line structure intact.
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_bullet(line: str) -> str:
    """Remove a leading bullet glyph or "1." style marker."""
    return BULLET_PREFIX.sub("", line).strip()


def split_bullets(value: Any) -> list[str]:
    """Turn pasted text into a list of lines, keeping real lists intact."""
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str):
                cleaned = strip_bullet(sanitise(item))
                if cleaned:
                    out.append(cleaned)
            elif item is not None:
                out.append(item)
        return out

    if not isinstance(value, str):
        return [] if value is None else value

    text = sanitise(value)
    if not text:
        return []

    # A single line holding several glyph-separated bullets is common when
    # copying out of a rendered document rather than a source file.
    if "\n" not in text and text.count("•") == 0:
        parts = [text]
    else:
        parts = re.split(r"\n|(?<=\S)\s*•\s*", text)

    return [cleaned for cleaned in (strip_bullet(p) for p in parts) if cleaned]


def sanitise_deep(data: Any) -> Any:
    """Recursively sanitise every string in a raw payload.

    Shape-preserving on purpose - lists stay lists, strings stay strings.
    Splitting is left to the fields that declare themselves as lists.
    """
    if isinstance(data, dict):
        return {k: sanitise_deep(v) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitise_deep(v) for v in data]
    if isinstance(data, str):
        return sanitise(data)
    return data


# Declare a field as this instead of list[str] and a pasted block becomes a
# proper list on the way in.
SmartBulletList = Annotated[list[str], BeforeValidator(split_bullets)]
