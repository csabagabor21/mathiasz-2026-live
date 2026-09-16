#!/usr/bin/env python3
"""Same-day screenshot validation for the Mathiasz 2026 km run.

Reads the public Google Forms response Sheet (CSV), downloads each linked
screenshot from Google Drive with a service-account key, and checks whether
the photo was taken on the same calendar day as the submission:

  1. EXIF capture date (works for JPEGs that still carry EXIF), else
  2. Meta Llama vision reading the activity date shown in the screenshot
     (Strava / Google Fit / Apple Health render the workout date), else
  3. status stays "pending" (manual review by the organizer).

Writes data.json for the public scoreboard. Only "verified" km counts.
"""
import base64
import csv
import hashlib
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(REPO_DIR, "validator", "validation.json")
DATA_PATH = os.path.join(REPO_DIR, "data.json")
SHEET_CSV = os.environ.get(
    "SHEET_CSV_URL",
    "https://docs.google.com/spreadsheets/d/1Fau2nH98Jzf2f5VhLpQPfdDDa8qFQYI47sc4rDC5HS0/gviz/tq?tqx=out:csv",
)
GOAL = int(os.environ.get("GOAL_KM", "2026"))
LLAMA_URL = os.environ.get(
    "LLAMA_API_URL", "https://api.llama.com/compat/v1/chat/completions"
)
LLAMA_MODEL = os.environ.get("LLAMA_MODEL", "Llama-4-Maverick-17B-128E-Instruct-FP8")

EXIF_TAGS = (36867, 36868, 306)  # DateTimeOriginal, DateTimeDigitized, DateTime


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


def vision_date(img_bytes, api_key):
    import requests

    b64 = base64.b64encode(img_bytes).decode("ascii")
    payload = {
        "model": LLAMA_MODEL,
        "max_tokens": 120,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "This is a fitness app screenshot (Strava, Google Fit or Apple Health). "
                        "On which calendar date was the workout done? Use the activity date shown in the image. "
                        'Reply ONLY with JSON like {"activity_date": "YYYY-MM-DD"}, '
                        'or {"activity_date": null} if no date is visible.',
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," + b64},
                    },
                ],
            }
        ],
    }
    r = requests.post(
        LLAMA_URL,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    r.raise_for_status()
    txt = r.json()["choices"][0]["message"]["content"] or ""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", txt)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    except ValueError:
        return None


def judge(fid, sub, sa_key, llama_key):
    """Return (status, evidence). status in verified|pending|mismatch."""
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
    if not llama_key:
        return "pending", "no-ai-key"
    try:
        vd = vision_date(blob, llama_key)
    except Exception:
        return "pending", "ai-error"
    if vd is None:
        return "pending", "ai-no-date"
    if vd == sub.date():
        return "verified", f"ai:{vd.isoformat()}"
    return "mismatch", f"ai:{vd.isoformat()}"


def fetch_csv(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode("utf-8-sig")


def main():
    sa_key = os.environ.get("GOOGLE_SA_KEY", "")
    llama_key = os.environ.get("LLAMA_API_KEY", "")
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        prev = {}
    rows = list(csv.reader(fetch_csv(SHEET_CSV).splitlines()))
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
            status, evidence = judge(fid, sub, sa_key, llama_key)
            checked = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
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
        "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
