"""Mine bullets out of CVs you have already written, from the command line.

The same extraction the app runs at Profile > "Start from a CV you already
have". This is the batch version, for when you have a folder of them rather
than a handful to upload.

    python -m scripts.mine_cvs --dir "C:/path/to/your/CVs"
    python -m scripts.mine_cvs --dir ... --email you@example.com
    python -m scripts.mine_cvs --dir ... --json candidates.json

Nothing is written to your profile. The output is a review list - only you
know which of those claims are still true.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.cvmine import mine
from app.models import Profile
from app.storage import get_store


def known_lines(email: str) -> list[str]:
    """Text already in the profile, so it is not offered again as a suggestion."""
    store = get_store()
    user = store.get_user_by_email(email)
    if not user:
        raise SystemExit(f"No account for {email}")

    profile = Profile(**(store.get_profile(user["id"]) or {}))
    known = list(profile.boundaries)
    for group in profile.evidence:
        known.extend(group.items)
    for job in profile.employment:
        known.extend(job.bullets)
    for item in profile.independent:
        known.extend(item.bullets)
    return known


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mine bullets out of existing CVs.")
    parser.add_argument("--dir", required=True, type=Path, help="Folder of .docx CVs")
    parser.add_argument("--email", default="",
                        help="Compare against this account's profile")
    parser.add_argument("--json", type=Path, default=None,
                        help="Also write the full result to a JSON file")
    args = parser.parse_args(argv)

    paths = [p for p in sorted(args.dir.glob("*.docx")) if not p.name.startswith("~$")]
    if not paths:
        print(f"No .docx files in {args.dir}", file=sys.stderr)
        return 1

    known = known_lines(args.email) if args.email else []
    result = mine([(p.name, p.read_bytes()) for p in paths], known=known)

    print(f"Read {result['files_read']} of {len(paths)} CV(s) from {args.dir}")
    for note in result["skipped"]:
        print(f"  ! {note}")
    if args.email:
        print(f"Compared against {len(known)} lines already in the profile")

    if result["contact"]:
        print("\nContact details found:")
        for key, value in result["contact"].items():
            print(f"  {key:10s} {value}")

    if result["technologies"]:
        print("\nTechnologies mentioned:")
        print("  " + ", ".join(result["technologies"][:20]))

    print(f"\n{len(result['candidates'])} line(s) not already in the profile:\n")
    for c in result["candidates"]:
        print("  [" + (", ".join(c["technologies"]) or "-") + f"]  {c['source']}")
        print(f"    {c['text']}\n")

    if args.json:
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        print(f"Written to {args.json}")

    print("Nothing was written to your profile. Paste what you want to keep into "
          "Profile > Evidence bank, or upload the same files in the app to pick "
          "them from a list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
