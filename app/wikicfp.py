"""
WikiCFP scraper — fetches conference series listings and event CFP details.

Series page:  http://www.wikicfp.com/cfp/program?id=<series_id>
Event detail: http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=<id>
"""
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup, Tag

WIKICFP_BASE = "http://www.wikicfp.com"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Alpaca/1.0)"}
_TIMEOUT = 20.0

# WikiCFP uses several date formats; may include "(abstract date)" in parens
_DATE_FORMATS = [
    "%b %d, %Y",   # Jan 28, 2026
    "%B %d, %Y",   # January 28, 2026
    "%b %d %Y",    # Jan 28 2026
    "%B %d %Y",    # January 28 2026
    "%d %b %Y",    # 28 Jan 2026
    "%d %B %Y",    # 28 January 2026
]


def _parse_date(text: str) -> Optional[date]:
    # Strip parenthesised secondary date like "(Jan 23, 2026)"
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text.lower() in ("tbd", "n/a", "-", "—", ""):
        return None
    # Remove ordinal suffixes: 1st → 1
    text = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", text)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _extract_event_id(href: str) -> Optional[str]:
    m = re.search(r"eventid=(\d+)", href or "")
    return m.group(1) if m else None


def _extract_year(text: str) -> Optional[int]:
    m = re.search(r"\b(20\d{2})\b", text)
    return int(m.group(1)) if m else None


@dataclass
class EditionInfo:
    event_id: str
    title: str
    year: Optional[int]
    when_text: str
    where_text: str
    deadline_text: str


def _parse_date_range(text: str) -> tuple[Optional[date], Optional[date]]:
    """Parse 'Mon D, YYYY - Mon D, YYYY' into (start, end) dates."""
    parts = re.split(r"\s*[-–]\s*", text, maxsplit=1)
    start = _parse_date(parts[0]) if parts else None
    end = _parse_date(parts[1]) if len(parts) > 1 else None
    return start, end


@dataclass
class CFPInfo:
    year: Optional[int] = None
    location: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    abstract_deadline: Optional[date] = None
    full_paper_deadline: Optional[date] = None
    notification_date: Optional[date] = None
    camera_ready_deadline: Optional[date] = None


async def fetch_editions(series_id: str) -> list[EditionInfo]:
    """
    Fetch editions for a conference series from WikiCFP.

    `series_id` can be either:
      - A numeric program ID (e.g. "1421") → uses /cfp/program?id=<id>
      - A text search term (e.g. "automl") → uses /cfp/call?conference=<term>

    Both pages share the same two-row-per-edition table structure.
    """
    if series_id.strip().isdigit():
        url = f"{WIKICFP_BASE}/cfp/program?id={series_id}"
    else:
        url = f"{WIKICFP_BASE}/cfp/call?conference={series_id}"
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    editions: list[EditionInfo] = []

    # The editions table has a header row with bgcolor="#bbbbbb".
    # Each edition is represented by TWO consecutive <tr> rows sharing the
    # same bgcolor (#f6f6f6 or #e6e6e6, alternating per edition):
    #   Row 1: <td rowspan="2">event link</td> <td colspan="3">full title</td>
    #   Row 2: <td>when</td> <td>where</td> <td>deadline</td>
    #
    # We restrict to the editions table only to avoid picking up links from
    # the "Related Resources" sidebar box.
    editions_table = None
    for tbl in soup.find_all("table"):
        if tbl.find("tr", attrs={"bgcolor": "#bbbbbb"}):
            editions_table = tbl
            break
    if editions_table is None:
        return editions

    for link in editions_table.find_all("a", href=re.compile(r"event\.showcfp\?eventid=")):
        if not isinstance(link, Tag):
            continue
        event_id = _extract_event_id(link.get("href", ""))
        if not event_id:
            continue

        title = link.get_text(strip=True)
        year = _extract_year(title)

        # Row 1 is the parent <tr>
        row1 = link.find_parent("tr")
        if not row1 or not isinstance(row1, Tag):
            continue

        # Row 2 is the next <tr> sibling (contains when/where/deadline)
        row2 = row1.find_next_sibling("tr")
        if not row2 or not isinstance(row2, Tag):
            continue

        tds = row2.find_all("td")
        when_text = tds[0].get_text(strip=True) if len(tds) > 0 else ""
        where_text = tds[1].get_text(strip=True) if len(tds) > 1 else ""
        deadline_text = tds[2].get_text(strip=True) if len(tds) > 2 else ""

        if not year:
            year = _extract_year(when_text)

        editions.append(EditionInfo(
            event_id=event_id,
            title=title,
            year=year,
            when_text=when_text,
            where_text=where_text,
            deadline_text=deadline_text,
        ))

    return editions


async def fetch_event_cfp(event_id: str) -> CFPInfo:
    """Fetch full CFP deadline details for a specific WikiCFP event."""
    url = f"{WIKICFP_BASE}/cfp/servlet/event.showcfp?eventid={event_id}"
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    info = CFPInfo()

    # Event details use a <table> where each row has <th>Label</th><td>Value</td>
    for row in soup.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue

        label = th.get_text(strip=True).lower()
        value = td.get_text(" ", strip=True)

        if label == "when":
            y = _extract_year(value)
            if y:
                info.year = y
            info.start_date, info.end_date = _parse_date_range(value)
        elif label == "where":
            info.location = value if value.lower() not in ("tbd", "n/a", "") else None
        elif "abstract" in label:
            info.abstract_deadline = _parse_date(value)
        elif "submission" in label:
            info.full_paper_deadline = _parse_date(value)
        elif "notification" in label:
            info.notification_date = _parse_date(value)
        elif "final version" in label or "camera" in label:
            info.camera_ready_deadline = _parse_date(value)

    return info
