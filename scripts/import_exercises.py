"""Load a JSON export of the old Railway `exercises` table into the S3 archive.

    python scripts/import_exercises.py path/to/exercises.json [--dry-run]

Keeps each row's original id and created_at, so the history page shows the old
cases exactly as Railway did. Re-running is safe: it overwrites by id.
Needs AWS credentials with read/write on the archive bucket (backend/archive.py).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import archive  # noqa: E402


def main(path: str, dry_run: bool) -> None:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    print(f"{len(rows)} exercises -> s3://{archive.BUCKET}/ {'(dry run)' if dry_run else ''}")
    for r in rows:
        s = archive.summarize(r)
        print(f"  #{r['id']:>3} {s['name'] or '(unnamed)':<20} {s['created_at']}  {s['total_cases']} cases")
        if not dry_run:
            archive.put(r)
    if not dry_run:
        print(f"done: {len(archive.list_summaries())} exercises in the index")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    main(args[0], "--dry-run" in sys.argv)
