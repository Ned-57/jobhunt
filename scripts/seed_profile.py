"""Seed a profile from a local seed file.

YAML by default. It handles multi-line prose without escaping, which is what a
CV is mostly made of - a JSON seed turned every bullet into one long line with
\\n in it and broke the moment a quote appeared.

The seed file holds real personal details - name, phone, email, employment
history - so it is gitignored and never committed. Copy the example and edit:

    copy scripts\\seed_data.example.yaml scripts\\seed_data.yaml

Usage:

    python -m scripts.seed_profile --email you@example.com
    python -m scripts.seed_profile --email you@example.com --dry-run
    python -m scripts.seed_profile --email you@example.com --force
    python -m scripts.seed_profile --email you@example.com --file other.yaml

An export from the app's Account page (JSON) works as a seed file too.
Create the account in the app first; this only fills in the profile, and never
creates users or touches passwords.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.models import Profile
from app.storage import get_store

HERE = Path(__file__).resolve().parent
EXAMPLE_SEED = HERE / "seed_data.example.yaml"

# Whichever exists, preferring YAML. The JSON form is still accepted so an
# Account-page export can be dropped straight in.
SEED_CANDIDATES = [HERE / "seed_data.yaml", HERE / "seed_data.yml", HERE / "seed_data.json"]

TODO = [
    "Salary expectation and earliest start - worth checking per application rather "
    "than assuming. Profile > What you will take.",
    "Dealbreakers - what rules a role out regardless of how good it looks. "
    "Profile > What you will take.",
]


def default_seed() -> Path:
    for path in SEED_CANDIDATES:
        if path.exists():
            return path
    return SEED_CANDIDATES[0]


def parse(path: Path) -> Any:
    """Read YAML or JSON, reporting where the problem is rather than raising."""
    try:
        # utf-8-sig strips the BOM Notepad adds when it saves as UTF-8.
        raw_text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise SystemExit(
            f"No seed file at {path}.\n"
            f"Copy {EXAMPLE_SEED.name} to {path.name} and fill it in, or export your "
            f"profile from the app's Account page."
        )
    except UnicodeDecodeError:
        raise SystemExit(
            f"{path.name} is not valid UTF-8.\n"
            f"Open it in your editor, Save As, and choose UTF-8 encoding."
        )

    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            return yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
            raise SystemExit(f"{path.name} is not valid YAML{where}.\n{exc}")

    try:
        return json.loads(raw_text, strict=False)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{path.name} is broken at line {exc.lineno}, column {exc.colno}.\n{exc.msg}"
        )


def load_profile(path: Path) -> Profile:
    raw = parse(path)
    if raw is None:
        raise SystemExit(f"{path.name} is empty.")

    # An Account-page export wraps the profile; a hand-written seed does not.
    if isinstance(raw, dict) and "profile" in raw:
        raw = raw["profile"]
    if not isinstance(raw, dict):
        raise SystemExit(f"{path.name} should contain a mapping of profile fields.")

    try:
        return Profile.model_validate(raw)
    except ValidationError as exc:
        print(f"\n{path.name} does not match the profile schema "
              f"({exc.error_count()} problem(s)):\n", file=sys.stderr)
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            print(f"  {field}", file=sys.stderr)
            print(f"    {error.get('msg', 'unknown error')}", file=sys.stderr)
            print(f"    got: {error.get('input', '<missing>')!r}\n", file=sys.stderr)
        raise SystemExit(1)


def summarise(profile: Profile) -> None:
    lines = sum(len(g.items) for g in profile.evidence)
    never = sum(1 for t in profile.tech if t.level == "never")
    print(f"  {len(profile.evidence)} evidence themes, {lines} evidence lines")
    print(f"  {len(profile.tech)} technology entries ({never} marked do-not-claim)")
    print(f"  {len(profile.boundaries)} accuracy boundaries")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--email", required=True,
                        help="Email of an account you already created")
    parser.add_argument("--file", type=Path, default=None,
                        help=f"Seed file to read (default: {default_seed().name})")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite a profile that already has answers in it")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and print the profile, write nothing")
    args = parser.parse_args(argv)

    path = args.file or default_seed()
    profile = load_profile(path)

    if args.dry_run:
        print(yaml.safe_dump(profile.model_dump(), sort_keys=False, allow_unicode=True))
        return 0

    store = get_store()
    user = store.get_user_by_email(args.email)
    if not user:
        print(f"No account found for {args.email}.", file=sys.stderr)
        print("Create it in the app first, then re-run this.", file=sys.stderr)
        return 1

    existing = store.get_profile(user["id"]) or {}
    if (existing.get("identity") or {}).get("name") and not args.force:
        print(f"{args.email} already has a filled-in profile.", file=sys.stderr)
        print("Re-run with --force to overwrite it.", file=sys.stderr)
        return 1

    store.save_profile(user["id"], profile.model_dump())

    state = profile.completeness()
    print(f"Seeded {args.email} from {path.name} - {state['percent']}% complete "
          f"({state['done']} of {state['total']} sections).")
    summarise(profile)
    print("\nStill needs you:")
    for item in TODO:
        print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
