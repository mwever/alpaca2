"""
ScimagoJR scraper — fetches SJR indicator and quartile for a journal.

Journal page: https://www.scimagojr.com/journalsearch.php?q=<scimago_id>&tip=sid
"""
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup, Tag

_BASE = "https://www.scimagojr.com"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": _BASE + "/",
}
_TIMEOUT = 20.0
_QUARTILE_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}


@dataclass
class ScimagoInfo:
    title: str
    sjr: Optional[float]          # most recent SJR value
    sjr_year: Optional[int]       # year of the SJR value
    best_quartile: Optional[str]  # best quartile in the sjr_year (Q1–Q4)
    h_index: Optional[int]
    # Per-category quartiles for the most recent year
    categories: list[tuple[str, str]]  # [(category_name, quartile), ...]


def _parse_float(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _parse_int(text: str) -> Optional[int]:
    try:
        return int(text.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _table_rows(soup: BeautifulSoup, header: str) -> list[list[str]]:
    """Find the table whose first row matches `header` and return data rows."""
    for tbl in soup.find_all("table"):
        rows = tbl.find_all("tr")
        if rows and rows[0].get_text(strip=True) == header:
            return [
                [td.get_text(strip=True) for td in row.find_all("td")]
                for row in rows[1:]
                if row.find("td")
            ]
    return []


async def fetch_scimago(scimago_id: str) -> ScimagoInfo:
    """Fetch and parse ScimagoJR data for the given source ID."""
    url = f"{_BASE}/journalsearch.php?q={scimago_id}&tip=sid&out=json"
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        # Warm up session to get cookies
        await client.get(_BASE + "/", headers={"User-Agent": _HEADERS["User-Agent"]})
        resp = await client.get(url, headers=_HEADERS)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── Title ────────────────────────────────────────────────────────────────
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # ── SJR indicator (most recent year) ────────────────────────────────────
    sjr_rows = _table_rows(soup, "YearSJR")
    sjr: Optional[float] = None
    sjr_year: Optional[int] = None
    if sjr_rows:
        # Rows sorted ascending; take the last non-empty one
        for year_str, val_str in reversed(sjr_rows):
            v = _parse_float(val_str)
            if v is not None:
                sjr = v
                sjr_year = _parse_int(year_str)
                break

    # ── Quartile per category (most recent year) ─────────────────────────────
    q_rows = _table_rows(soup, "CategoryYearQuartile")
    categories: list[tuple[str, str]] = []
    best_quartile: Optional[str] = None

    if q_rows and sjr_year:
        year_str = str(sjr_year)
        for row in q_rows:
            if len(row) >= 3 and row[1] == year_str:
                categories.append((row[0], row[2]))
        # If no rows for sjr_year, try the most recent year present
        if not categories:
            latest_year = max((row[1] for row in q_rows if len(row) >= 3), default=None)
            if latest_year:
                for row in q_rows:
                    if len(row) >= 3 and row[1] == latest_year:
                        categories.append((row[0], row[2]))
        if categories:
            best_quartile = min(
                (q for _, q in categories if q in _QUARTILE_ORDER),
                key=lambda q: _QUARTILE_ORDER.get(q, 99),
                default=None,
            )

    # ── H-index ──────────────────────────────────────────────────────────────
    h_index: Optional[int] = None
    for tag in soup.find_all(string=lambda t: t and "H index" in t):
        parent = tag.parent
        if parent:
            nxt = parent.find_next_sibling()
            if nxt:
                h_index = _parse_int(nxt.get_text(strip=True))
                break

    return ScimagoInfo(
        title=title,
        sjr=sjr,
        sjr_year=sjr_year,
        best_quartile=best_quartile,
        h_index=h_index,
        categories=categories,
    )
