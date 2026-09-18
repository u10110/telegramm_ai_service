"""Watch Telegram avatar volume and write gender/age inference into a Google Sheet.

One result per avatar file named <phone>_<user_id>.jpg. Results are written to
columns added to the source sheet: telegram_gender, telegram_age, telegram_face_status.
The worker scans existing files at startup and then polls for newly downloaded avatars.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SHEET_ID = os.environ.get("RESULT_SHEET_ID", "192OIcpHEAv_hekH7ezXX2wu4jWuoD5rG8cy58YytVGQ")
SHEET_NAME = os.environ.get("RESULT_SHEET_RANGE", "telegram_numbers_1000_no_800_with_status_checked_corrected")
TOKEN = os.environ.get("GOOGLE_TOKEN_PATH", "/tmp/google_token.json")
PHOTOS = Path(os.environ.get("PHOTOS_DIR", "/var/lib/docker/volumes/telegramm-ai-photos/_data"))
AGE_PY = "/opt/age_gender/venv/bin/python"
AGE_SCRIPT = "/opt/age_gender/age_gender.py"
STATE = Path("/tmp/age_gender_sheet_state.json")
POLL_SECONDS = 10


def sheet_client():
    creds = Credentials.from_authorized_user_file(TOKEN)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def columns_and_index(svc):
    rows = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!A1:ZZ1"
    ).execute().get("values", [[]])
    header = rows[0]
    required = ["telegram_gender", "telegram_age", "telegram_face_status"]
    missing = [x for x in required if x not in header]
    if missing:
        start = len(header)
        end = start + len(missing) - 1
        def col(n):
            out = ""
            n += 1
            while n:
                n, rem = divmod(n - 1, 26)
                out = chr(65 + rem) + out
            return out
        svc.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_NAME}!{col(start)}1:{col(end)}1",
            valueInputOption="RAW", body={"values": [missing]},
        ).execute()
        header += missing
    phones = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!A2:A"
    ).execute().get("values", [])
    phone_index = {r[0]: i + 2 for i, r in enumerate(phones) if r}
    return header, phone_index


def col_name(index):
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def analyze(image):
    cp = subprocess.run([AGE_PY, AGE_SCRIPT, str(image)], capture_output=True, text=True, timeout=120)
    if cp.returncode not in (0, 2):
        raise RuntimeError((cp.stderr or cp.stdout)[-500:])
    raw = json.loads(cp.stdout)
    # Validated CLI shape: {"results": [{"is_human", "faces", ...}], ...}.
    if isinstance(raw, dict) and "results" in raw:
        raw = (raw.get("results") or [{}])[0]
    elif isinstance(raw, list):
        raw = raw[0] if raw else {}
    faces = raw.get("faces") or []
    if not raw.get("is_human", False) or not faces:
        return "", "", "no_face"
    face = max(faces, key=lambda x: x.get("det_score", 0))
    gender = face.get("gender") or raw.get("gender") or ""
    age = face.get("age") or raw.get("age") or ""
    return str(gender), str(age), "face"


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {"done": {}}
    done = state.setdefault("done", {})
    svc = sheet_client()
    header, phone_index = columns_and_index(svc)
    gender_i, age_i, status_i = (header.index(x) for x in ("telegram_gender", "telegram_age", "telegram_face_status"))
    print(f"[ready] photos={PHOTOS}; phones={len(phone_index)}; cols={col_name(gender_i)},{col_name(age_i)},{col_name(status_i)}", flush=True)
    while True:
        for photo in sorted(PHOTOS.glob("*.jpg")) + sorted(PHOTOS.glob("*.jpeg")) + sorted(PHOTOS.glob("*.png")):
            stamp = f"{photo.stat().st_mtime_ns}:{photo.stat().st_size}"
            if done.get(photo.name) == stamp:
                continue
            m = re.match(r"^(\+?\d+)_\d+\.(?:jpg|jpeg|png)$", photo.name, re.I)
            if not m:
                done[photo.name] = stamp
                continue
            phone = m.group(1)
            if not phone.startswith("+"):
                phone = "+" + phone
            row = phone_index.get(phone)
            if not row:
                print(f"[skip] {photo.name}: phone not found", flush=True)
                done[photo.name] = stamp
                continue
            try:
                gender, age, face_status = analyze(photo)
                # Each image writes its result straight into the matching Sheet row.
                svc.spreadsheets().values().batchUpdate(
                    spreadsheetId=SHEET_ID, body={"valueInputOption": "RAW", "data": [
                        {"range": f"{SHEET_NAME}!{col_name(gender_i)}{row}:{col_name(status_i)}{row}",
                         "values": [[gender, age, face_status]]}
                    ]}
                ).execute()
                done[photo.name] = stamp
                STATE.write_text(json.dumps(state, ensure_ascii=False))
                print(f"[done] row={row} {photo.name}: gender={gender or '-'} age={age or '-'} {face_status}", flush=True)
            except Exception as exc:
                print(f"[error] {photo.name}: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
