import json
import os
import re
import sys
import urllib.request

# OSU Term Codes: 202701 = Fall 2026 | 202702 = Winter 2027 | 202703 = Spring 2027
TERM_CODE = "202702"
TARGET_CRNS = ["31675", "31676", "31677"]
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

SEARCH_URL = "https://classes.oregonstate.edu/api/?page=fose&route=search"
DETAILS_URL = "https://classes.oregonstate.edu/api/?page=fose&route=details"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Origin": "https://classes.oregonstate.edu",
    "Referer": "https://classes.oregonstate.edu/",
}


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_seat_info(details_data: dict, section: dict) -> tuple[int, str]:
    candidate_texts = []
    for key in ("seats", "enrollment", "seat_info", "avail", "clss_seats"):
        val = details_data.get(key)
        if val:
            candidate_texts.append(str(val))

    if not candidate_texts:
        for key, val in details_data.items():
            if isinstance(val, str) and re.search(r"(seat|avail|enroll|waitlist)", val, re.IGNORECASE):
                candidate_texts.append(f"{key}: {val}")

    for raw in candidate_texts:
        clean = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()
        match = re.search(r"(?:Seats\s*Available|Available|Open)\s*:\s*(\d+)", clean, re.IGNORECASE)
        if match:
            return int(match.group(1)), clean

    # Fallback to CourseLeaf's section status flag ("A" = Available/Open, "F" = Full)
    stat = str(section.get("stat") or details_data.get("stat") or "").strip().upper()
    avail = 1 if stat == "A" else 0
    return avail, f"stat={stat or 'unknown'} (details keys: {list(details_data.keys())})"


def check_crn(crn: str) -> tuple[str, int, str]:
    search_data = post_json(SEARCH_URL, {
        "other": {"srcdb": TERM_CODE},
        "criteria": [{"field": "crn", "value": crn}],
    })
    results = search_data.get("results", [])
    if not results:
        raise ValueError(f"CRN {crn} not found in term {TERM_CODE}")

    section = next((r for r in results if str(r.get("crn")) == str(crn)), results[0])
    course_code = section["code"]
    section_key = section.get("key", f"crn:{crn}")

    details_data = post_json(DETAILS_URL, {
        "group": f"code:{course_code}",
        "key": section_key,
        "srcdb": TERM_CODE,
        "matched": section_key,
    })

    avail, status_text = extract_seat_info(details_data, section)
    return course_code, avail, status_text


def notify(title: str, message: str) -> None:
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "urgent",
            "Tags": "rotating_light",
            "Click": "https://classes.oregonstate.edu/",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)


if __name__ == "__main__":
    had_error = False
    for crn in TARGET_CRNS:
        try:
            course_code, avail, raw_status = check_crn(crn)
            print(f"{course_code} (CRN {crn}) -> {avail} available ({raw_status})")
            if avail > 0:
                notify(
                    f"OSU Seat Open: {course_code}",
                    f"{course_code} (CRN {crn}) has {avail} open seat(s). Tap to open scheduler.",
                )
        except Exception as exc:
            print(f"Error checking CRN {crn}: {exc}")
            had_error = True

    if had_error:
        sys.exit(1)
