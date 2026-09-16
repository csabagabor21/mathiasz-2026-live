#!/usr/bin/env python3
"""Same-day screenshot validation for the Mathiasz 2026 km run.

Reads the public Google Forms response Sheet (CSV), downloads each linked
screenshot from Google Drive with a service-account key, and checks whether
the photo is from the same calendar day as the submission -- no AI service
and no API key needed:

  1. EXIF capture date (works for JPEGs that still carry EXIF), else
  2. Tesseract OCR reading the activity date shown in the screenshot
     (Strava / Google Fit / Apple Health render the workout date), else
  3. status stays "pending" (manual review by the organizer).

Writes data.json for the public scoreboard. Only "verified" km counts.
"""
import csv
import hashlib
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc)


REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(REPO_DIR, "validator", "validation.json")
DATA_PATH = os.path.join(REPO_DIR, "data.json")
SHEET_CSV = os.environ.get(
    "SHEET_CSV_URL",
    "https://docs.google.com/spreadsheets/d/1Fau2nH98Jzf2f5VhLpQPfdDDa8qFQYI47sc4rDC5HS0/gviz/tq?tqx=out:csv",
)
GOAL = int(os.environ.get("GOAL_KM", "2026"))

EXIF_TAGS = (36867, 36868, 306)  # DateTimeOriginal, DateTimeDigitized, DateTime

MONTHS = {
    "január": 1, "januar": 1, "jan": 1, "january": 1,
    "február": 2, "februar": 2, "feb": 2, "february": 2,
    "március": 3, "marcius": 3, "már": 3, "mar": 3, "march": 3,
    "április": 4, "aprilis": 4, "ápr": 4, "apr": 4, "april": 4,
    "május": 5, "majus": 5, "máj": 5, "maj": 5, "may": 5,
    "június": 6, "junius": 6, "jún": 6, "jun": 6, "june": 6,
    "július": 7, "julius": 7, "júl": 7, "jul": 7, "july": 7,
    "augusztus": 8, "aug": 8, "august": 8,
    "szeptember": 9, "szept": 9, "sept": 9, "sep": 9, "september": 9,
    "október": 10, "oktober": 10, "okt": 10, "oct": 10, "october": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
TODAY_WORDS = re.compile(r"\btoday\b|\bma\b")


def parse_hu_ts(s):
    s = (s or "").strip()
    for f in ("%Y.%m.%d. %H:%M:%S", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def parse_km(v):
    if v is None:
        return None
    s = re.sub(r"km|kilométer|kilometer|\bm\b", "", str(v).lower())
    s = s.replace(" ", "").replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        n = float(m.group(0))
    except ValueError:
        return None
    if n != n or n < 0 or n > 1000000:  # NaN / negative / garbage
        return None
    return round(n, 2)


def drive_file_id(url):
    url = url or ""
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/d/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def find_col(head, keys):
    for i, h in enumerate(head):
        if any(k in str(h).lower() for k in keys):
            return i
    return -1


def mask_name(n):
    parts = str(n or "").strip().split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1][0]}."
    return (parts[0] if parts else "?")[:20]


def download_image(file_id, sa_json):
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as AuthRequest
    except ImportError:
        raise RuntimeError("google-auth package missing")
    info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    creds.refresh(AuthRequest())
    req = urllib.request.Request(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
        headers={"Authorization": "Bearer " + creds.token},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def exif_date(img_bytes):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(img_bytes))
        ex = im.getexif()
    except Exception:
        return None
    for tag in EXIF_TAGS:
        v = ex.get(tag)
        if not v:
            continue
        try:
            return datetime.strptime(str(v).strip(), "%Y:%m:%d %H:%M:%S").date()
        except ValueError:
            continue
    return None


def ocr_text(img_bytes):
    """Classic OCR (Tesseract binary), no AI service. None if unavailable."""
    import shutil
    import subprocess

    if shutil.which("tesseract") is None:
        return None
    try:
        p = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "hun+eng"],
            input=img_bytes,
            capture_output=True,
            timeout=180,
        )
    except Exception:
        return None
    if p.returncode != 0 or not p.stdout:
        return None
    return p.stdout.decode("utf-8", "replace")


def find_dates_in_text(text):
    """Return (candidates, today_flag). candidates: set of (year|None, month, day)."""
    t = (text or "").lower()
    cands = set()
    today = bool(TODAY_WORDS.search(t))
    for m in re.finditer(r"(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})", t):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            cands.add((y, mo, d))
    for m in re.finditer(r"(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{4})", t):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            cands.add((y, mo, d))
    letters = "a-záéíóöőúüű"
    for name, mon in MONTHS.items():
        for m in re.finditer(
            rf"(?<![{letters}]){re.escape(name)}\.?(?![{letters}])", t
        ):
            window = t[max(0, m.start() - 8):m.end() + 8]
            for d in re.findall(r"\d{1,2}", window):
                dd = int(d)
                if 1 <= dd <= 31:
                    cands.add((None, mon, dd))
    return cands, today


def ocr_same_day(text, sub):
    """Match an OCR-read date against the submission day. Returns evidence or None."""
    cands, today = find_dates_in_text(text)
    for (y, mo, d) in sorted(cands, key=lambda c: (c[0] or 0, c[1], c[2])):
        if mo == sub.month and d == sub.day and (y is None or y == sub.year):
            tag = f"{y}-{mo:02d}-{d:02d}" if y else f"????-{mo:02d}-{d:02d}"
            return f"ocr:{tag}"
    if today:
        return "ocr:today"
    return None


def judge(fid, sub, sa_key):
    """Return (status, evidence). status in verified|pending|mismatch. No AI used."""
    if not fid:
        return "pending", "no-image"
    if sub is None:
        return "pending", "no-date"
    if not sa_key:
        return "pending", "no-drive-access"
    try:
        blob = download_image(fid, sa_key)
    except Exception:
        return "pending", "download-failed"
    exd = exif_date(blob)
    if exd is not None:
        if exd == sub.date():
            return "verified", f"exif:{exd.isoformat()}"
        return "mismatch", f"exif:{exd.isoformat()}"
    txt = ocr_text(blob)
    if txt is None:
        return "pending", "ocr-missing"
    ev = ocr_same_day(txt, sub)
    if ev:
        return "verified", ev
    return "pending", "ocr-no-date"


def fetch_csv(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode("utf-8-sig")


def main():
    sa_key = os.environ.get("GOOGLE_SA_KEY", "")
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        prev = {}
    raw = fetch_csv(SHEET_CSV)
    print(f"sheet bytes={len(raw)}")
    rows = list(csv.reader(raw.splitlines()))
    if len(rows) < 2:
        print("sheet has no response rows yet")
        rows = rows  # still write empty data.json below
    head = rows[0] if rows else []
    km_col = find_col(head, ["km", "kilom", "táv", "tav", "distance"])
    if km_col < 0:
        print("ERROR: no km column found", file=sys.stderr)
        return 1
    img_col = find_col(
        head,
        ["fotó", "foto", "kép", "kep", "screenshot", "fájl", "file",
         "drive", "strava", "health", "fit"],
    )
    entries = []
    for i in range(1, len(rows)):
        r = rows[i]
        ts_raw = r[0] if len(r) > 0 else ""
        name = r[1] if len(r) > 1 else f"sor {i + 1}"
        claimed = parse_km(r[km_col]) if km_col < len(r) else None
        if claimed is None:
            continue
        img_url = r[img_col] if 0 <= img_col < len(r) else ""
        fid = drive_file_id(img_url)
        sub = parse_hu_ts(ts_raw)
        rid = hashlib.sha1(
            f"{ts_raw}|{name}|{fid}|{claimed}".encode("utf-8")
        ).hexdigest()[:16]
        rec = prev.get(rid)
        if rec and rec.get("fp") == rid:
            status, evidence, checked = (
                rec["status"],
                rec.get("evidence", "?"),
                rec.get("checked_at", "?"),
            )
        else:
            status, evidence = judge(fid, sub, sa_key)
            checked = utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            prev[rid] = {
                "fp": rid,
                "status": status,
                "evidence": evidence,
                "checked_at": checked,
                "claimed": claimed,
            }
            print(f"checked {mask_name(name)} {claimed} km -> {status} ({evidence})")
        entries.append(
            {
                "name": mask_name(name),
                "claimed": claimed,
                "status": status,
                "submitted": ts_raw.strip(),
            }
        )
    verified_total = round(sum(e["claimed"] for e in entries if e["status"] == "verified"), 2)
    pending_total = round(sum(e["claimed"] for e in entries if e["status"] != "verified"), 2)
    data = {
        "updated": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "goal": GOAL,
        "verified_total": verified_total,
        "pending_total": pending_total,
        "verified_count": sum(1 for e in entries if e["status"] == "verified"),
        "pending_count": sum(1 for e in entries if e["status"] != "verified"),
        "entries": entries,
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(prev, f, ensure_ascii=False, indent=1)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"verified={verified_total} pending={pending_total} entries={len(entries)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
