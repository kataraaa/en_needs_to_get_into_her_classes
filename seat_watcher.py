import json
import os
import re
import urllib.request

TERM_CODE = "202702"  # e.g., 202702 = Winter 2027, 202703 = Spring 2027
TARGET_CRNS = ["31676", "31675", "31677"]
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

API_URL = "https://classes.oregonstate.edu/api/?page=fose&route=details"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Origin": "https://classes.oregonstate.edu",
    "Referer": "https://classes.oregonstate.edu/",
}


def check_crn(crn: str) -> tuple[int, str]:
    payload = json.dumps({
        "group": f"code:{crn}",
        "key": f"crn:{crn}",
        "srcdb": TERM_CODE,
        "matched": f"crn:{crn}",
    }).encode("utf-8")

    req = urllib.request.Request(API_URL, data=payload, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    seats_html = str(data.get("seats", ""))
    clean_text = re.sub(r"<[^>]+>", " ", seats_html).strip()
    match = re.search(r"Seats Available:\s*(\d+)", clean_text)
    if not match:
        match = re.search(r"(\d+)", clean_text)

    avail = int(match.group(1)) if match else 0
    return avail, clean_text


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
    for crn in TARGET_CRNS:
        try:
            avail, raw_status = check_crn(crn)
            print(f"CRN {crn} -> {avail} available ({raw_status})")
            if avail > 0:
                notify("OSU Seat Open!", f"CRN {crn} has {avail} open seat(s). Tap to open scheduler.")
        except Exception as exc:
            print(f"Error checking CRN {crn}: {exc}")
