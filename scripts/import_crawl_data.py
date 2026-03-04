"""
Import Google Scholar crawl data from gs-crawl/crawl_data/ into the Alpaca DB.

Usage (from the Alpaca project root):
    uv run python scripts/import_crawl_data.py

For each date directory it processes:
  profile_stats_<name>.json  → scholar_author_snapshots
  publication_stats_<name>.json → scholar_paper_snapshots
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
CRAWL_DIR = ROOT.parent / "gs-crawl" / "crawl_data"

# ── DB connection (sync pymysql driver) ──────────────────────────────────────
sys.path.insert(0, str(ROOT))
from app.config import settings

sync_url = settings.DATABASE_URL.replace("mysql+aiomysql", "mysql+pymysql")
engine = create_engine(sync_url, echo=False)

from app.models.author import Author
from app.models.scholar import ScholarAuthorSnapshot, ScholarPaperSnapshot
from app.models.paper import PaperProject


# ── Helpers ──────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    clean = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", clean).strip()


def safe_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def build_author_map(session: Session) -> dict[str, int]:
    """
    Build {stem: author_id} where stem is derived the same way as crawl filenames.
    Tries two forms per author:
      1. {given}_{last}        e.g. "carolin_benjamins"
      2. {given[0]}._{last}   e.g. "c._benjamins"
    All lowercased, spaces replaced by underscores.
    """
    authors = session.execute(select(Author)).scalars().all()
    mapping: dict[str, int] = {}
    for a in authors:
        given = (a.given_name or "").lower().replace(" ", "_")
        last = (a.last_name or "").lower().replace(" ", "_")
        full = f"{given}_{last}"
        mapping[full] = a.id
        if given:
            abbrev = f"{given[0]}._{ last}"
            mapping[abbrev] = a.id
    return mapping


def build_paper_map(session: Session) -> dict[str, int]:
    """Build {gs_paper_id: paper_project_id} for papers that have a GS ID set."""
    papers = session.execute(
        select(PaperProject).where(PaperProject.google_scholar_paper_id.isnot(None))
    ).scalars().all()
    return {p.google_scholar_paper_id: p.id for p in papers}


def existing_author_snapshot_keys(session: Session) -> set[tuple[int, date]]:
    rows = session.execute(
        text("SELECT author_id, date FROM scholar_author_snapshots")
    ).fetchall()
    return {(r[0], r[1]) for r in rows}


def existing_paper_snapshot_keys(session: Session) -> set[tuple[str, date]]:
    rows = session.execute(
        text("SELECT gs_paper_id, date FROM scholar_paper_snapshots")
    ).fetchall()
    return {(r[0], r[1]) for r in rows}


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if not CRAWL_DIR.exists():
        sys.exit(f"Crawl directory not found: {CRAWL_DIR}")

    date_dirs = sorted(d for d in CRAWL_DIR.iterdir() if d.is_dir())
    print(f"Found {len(date_dirs)} date directories in {CRAWL_DIR}")

    with Session(engine) as session:
        author_map = build_author_map(session)
        paper_map = build_paper_map(session)
        print(f"  {len(author_map)} author name stems matched in DB")
        print(f"  {len(paper_map)} papers with GS IDs in DB")

        # Pre-load existing keys to avoid duplicate inserts
        existing_author = existing_author_snapshot_keys(session)
        existing_paper = existing_paper_snapshot_keys(session)

        author_inserted = 0
        author_skipped = 0
        author_unmatched: set[str] = set()
        paper_inserted = 0
        paper_skipped = 0

        for date_dir in date_dirs:
            try:
                snap_date = date.fromisoformat(date_dir.name)
            except ValueError:
                print(f"  Skipping non-date directory: {date_dir.name}")
                continue

            # ── Profile stats ──────────────────────────────────────────────
            for profile_file in sorted(date_dir.glob("profile_stats_*.json")):
                stem = profile_file.stem.removeprefix("profile_stats_")
                author_id = author_map.get(stem)
                if author_id is None:
                    author_unmatched.add(stem)
                    author_skipped += 1
                    continue

                key = (author_id, snap_date)
                if key in existing_author:
                    author_skipped += 1
                    continue

                try:
                    data = json.loads(profile_file.read_text())
                except Exception as e:
                    print(f"  WARN: Could not parse {profile_file}: {e}")
                    continue

                session.add(ScholarAuthorSnapshot(
                    author_id=author_id,
                    date=snap_date,
                    citations=safe_int(data.get("citations")),
                    h_index=safe_int(data.get("h-index")),
                    i10_index=safe_int(data.get("i10-index")),
                    gs_entries=safe_int(data.get("gs_entries")),
                    current_year_citations=safe_int(data.get("current_year_citations")),
                ))
                existing_author.add(key)
                author_inserted += 1

            # ── Publication stats ──────────────────────────────────────────
            # Each file has entries for one author's papers, but the papers
            # themselves are global. Process once per gs_paper_id+date.
            for pub_file in sorted(date_dir.glob("publication_stats_*.json")):
                try:
                    entries = json.loads(pub_file.read_text())
                except Exception as e:
                    print(f"  WARN: Could not parse {pub_file}: {e}")
                    continue

                if not isinstance(entries, list):
                    continue

                for entry in entries:
                    gs_paper_id = entry.get("paper_id", "")
                    if not gs_paper_id:
                        continue

                    key = (gs_paper_id, snap_date)
                    if key in existing_paper:
                        paper_skipped += 1
                        continue

                    venue_raw = entry.get("venue") or ""
                    session.add(ScholarPaperSnapshot(
                        paper_id=paper_map.get(gs_paper_id),
                        gs_paper_id=gs_paper_id,
                        date=snap_date,
                        num_citations=safe_int(entry.get("num_citations")),
                        title=(entry.get("paper_title") or "")[:512],
                        year=str(entry.get("year") or "")[:8] or None,
                        venue=strip_html(venue_raw)[:512] or None,
                        author_list=(entry.get("author_list") or "") or None,
                    ))
                    existing_paper.add(key)
                    paper_inserted += 1

        session.commit()

    # ── Backfill ScholarPaperSnapshot.paper_id for any papers now in DB ──────
    print("\nBackfilling paper_id links on existing snapshots…")
    backfilled = 0
    with Session(engine) as session:
        paper_map = build_paper_map(session)
        for gs_id, pid in paper_map.items():
            result = session.execute(
                text("UPDATE scholar_paper_snapshots SET paper_id = :pid "
                     "WHERE gs_paper_id = :gs AND (paper_id IS NULL OR paper_id != :pid)"),
                {"pid": pid, "gs": gs_id},
            )
            backfilled += result.rowcount
        session.commit()
    print(f"  {backfilled} snapshot rows linked to paper projects")

    print(f"\nDone.")
    print(f"  Author snapshots: {author_inserted} inserted, {author_skipped} skipped")
    if author_unmatched:
        print(f"  Unmatched author stems (no DB record found): {sorted(author_unmatched)}")
    print(f"  Paper snapshots:  {paper_inserted} inserted, {paper_skipped} skipped")


if __name__ == "__main__":
    main()
