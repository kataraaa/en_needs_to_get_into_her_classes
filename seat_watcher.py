from datetime import datetime, timedelta, timezone
import json
import os
import sys
import urllib.request

# OSU Term Codes: 202701 = Fall 2026 | 202702 = Winter 2027 | 202703 = Spring 2027
TERM_CODE = "202702"
TARGET_CRNS = ["39013"]
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

# Mute phone alerts until Thursday, November 19, 2026 at 5:00 AM PST
PST = timezone(timedelta(hours=-8))
MUTE_UNTIL = datetime(2026, 11, 19, 5, 0, 0, tzinfo=PST)

SEARCH_URL = "https://classes.oregonstate.edu/api/?page=fose&route=search"
REGISTRATION_URL = (
    "https://prodapps.isadm.oregonstate.edu/StudentRegistrationSsb/ssb/term/termSelection?mode=registration"
)
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Origin": "https://classes.oregonstate.edu",
    "Referer": "https://classes.oregonstate.edu/",
}


def check_crn(crn: str) -> dict:
    payload = json.dumps({
        "other": {"srcdb": TERM_CODE},
        "criteria": [{"field": "crn", "value": crn}],
    }).encode("utf-8")

    req = urllib.request.Request(SEARCH_URL, data=payload, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = data.get("results", [])
    if not results:
        raise ValueError(f"CRN {crn} not found in term {TERM_CODE}")

    section = next((r for r in results if str(r.get("crn")) == str(crn)), results[0])
    stat = str(section.get("stat", "")).strip().upper()
    if not stat:
        raise ValueError(f"Missing status flag for CRN {crn}")

    return {
        "code": section.get("code", "Unknown"),
        "no": section.get("no", ""),
        "schd": section.get("schd", ""),
        "stat": stat,
        "is_open": stat == "A",
    }


def notify(title: str, message: str) -> None:
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "urgent",
            "Tags": "rotating_light",
            "Click": REGISTRATION_URL,
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)


if __name__ == "__main__":
    had_error = False
    now_pst = datetime.now(PST)
    is_muted = now_pst < MUTE_UNTIL

    for crn in TARGET_CRNS:
        try:
            info = check_crn(crn)
            label = f"{info['code']}-{info['no']} ({info['schd']})".strip()
            status_label = "OPEN (stat=A)" if info["is_open"] else f"FULL (stat={info['stat']})"
            print(f"CRN {crn} | {label} -> {status_label}")

            if info["is_open"]:
                if is_muted:
                    print(f"  -> Notification muted until {MUTE_UNTIL.strftime('%a %b %d %I:%M %p')} PST")
                else:
                    notify(
                        f"Class Seat Open: {info['code']} (CRN {crn})",
                        f"CRN {crn} | {label} is now OPEN. Tap to open OSU Registration.",
                    )
        except Exception as exc:
            print(f"Error checking CRN {crn}: {exc}")
            had_error = True

    if had_error:
        sys.exit(1)
