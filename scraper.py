"""
Scrapes NTU WISH class schedule from:
https://wish.wis.ntu.edu.sg/webexe/owa/aus_schedule.main
"""

import re
import requests
from bs4 import BeautifulSoup

WISH_MAIN = "https://wish.wis.ntu.edu.sg/webexe/owa/aus_schedule.main"
WISH_RESULTS = "https://wish.wis.ntu.edu.sg/webexe/owa/AUS_SCHEDULE.main_display1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": WISH_MAIN,
}


def fetch_schedule_by_course_code(course_code: str, acad_year: str = "2025;2") -> list[dict]:
    """Search by course code (e.g. 'SC1003', 'MH1810')."""
    payload = {
        "r_subj_code": course_code.upper().strip(),
        "r_search_type": "F",
        "boption": "Search",
        "acadsem": acad_year,
        "staff_access": "false",
    }
    response = requests.post(WISH_RESULTS, data=payload, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return _parse_schedule_html(response.text)


def fetch_schedule_by_index(course_code: str, index_number: str, acad_year: str = "2025;2") -> list[dict]:
    """
    Fetch all slots for a specific index number within a course.
    WISH has no direct index lookup — search by course code and filter.
    """
    all_slots = fetch_schedule_by_course_code(course_code, acad_year)
    return [s for s in all_slots if s["index_number"] == index_number.strip()]


def _parse_schedule_html(html: str) -> list[dict]:
    """
    WISH results page structure (confirmed from live site):

    Tables come in pairs:
      - Even index (0, 2, 4 ...): course header — row 0 = [course_code, course_name~, AU]
      - Odd index  (1, 3, 5 ...): slot rows    — [index, class_type, group, day, time, venue, remark]
        index cell is blank for continuation rows sharing the same index number.
    """
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    results = []

    for pair_start in range(0, len(tables) - 1, 2):
        header_table = tables[pair_start]
        slots_table = tables[pair_start + 1]

        # Extract course code and name from header table first row
        header_rows = header_table.find_all("tr")
        if not header_rows:
            continue
        header_cells = [c.get_text(strip=True) for c in header_rows[0].find_all("td")]
        if len(header_cells) < 2 or not _looks_like_course_code(header_cells[0]):
            continue

        course_code = header_cells[0]
        course_name = header_cells[1].rstrip("~").strip()

        current_index = ""
        for row in slots_table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 6:
                continue
            text_cells = [c.get_text(strip=True) for c in cells]

            idx_val, class_type, group, day, time_range, venue = text_cells[:6]
            remark = text_cells[6] if len(text_cells) > 6 else ""

            if idx_val.isdigit():
                current_index = idx_val

            if not current_index or not class_type:
                continue

            time_start, time_end = _split_time(time_range)

            results.append({
                "course_code": course_code,
                "course_name": course_name,
                "index_number": current_index,
                "class_type": class_type,
                "group": group,
                "day": day,
                "time_start": time_start,
                "time_end": time_end,
                "venue": venue,
                "remark": remark,
            })

    return results


def _looks_like_course_code(text: str) -> bool:
    return bool(re.match(r"^[A-Z]{2,4}\d{4}[A-Z]?$", text.strip()))


def _split_time(time_range: str):
    if "-" in time_range:
        parts = time_range.split("-")
        return parts[0].strip(), parts[1].strip()
    return time_range.strip(), ""
