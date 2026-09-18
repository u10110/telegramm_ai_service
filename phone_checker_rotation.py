from __future__ import annotations

import asyncio
import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from telethon import TelegramClient, functions, types
from telethon.errors import FloodWaitError, PhoneNotOccupiedError

UTC = timezone.utc
MAX_PER_ACCOUNT_PER_DAY = 10

PHOTOS_DIR = Path(os.getenv("PHOTOS_DIR", "/app/photos"))
PUBLIC_PHOTO_BASE = os.getenv("PUBLIC_PHOTO_BASE", "http://93.183.106.243/photos").rstrip("/")

TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "/tmp/google_token.json")
RESULT_SHEET_ID = os.getenv("RESULT_SHEET_ID", "1RbKZzfvnZ4FCBBKGSi0sXnx07sX0ZEOqT31q6h_zCbw")
RESULT_SHEET_RANGE = os.getenv("RESULT_SHEET_RANGE", "Лист1")


def today(now: datetime) -> str:
    return now.astimezone(UTC).date().isoformat()


def _entry(state: dict[str, Any], account: str, now: datetime) -> dict[str, Any]:
    e = state.setdefault(account, {})
    if e.get("date") != today(now):
        e.clear()
        e.update({"date": today(now), "assigned": 0, "paused_until": ""})
    e.setdefault("assigned", 0)
    e.setdefault("paused_until", "")
    return e


def _paused(e: dict[str, Any], now: datetime) -> bool:
    raw = e.get("paused_until", "")
    if not raw:
        return False
    try:
        return datetime.fromisoformat(raw) > now
    except ValueError:
        return False


def choose_account(accounts: list[str], state: dict[str, Any], cursor: int, now: datetime) -> tuple[str | None, int | None]:
    if not accounts:
        return None, None
    for step in range(len(accounts)):
        idx = (cursor + step) % len(accounts)
        e = _entry(state, accounts[idx], now)
        if e["assigned"] < MAX_PER_ACCOUNT_PER_DAY and not _paused(e, now):
            return accounts[idx], idx
    return None, None


def mark_assigned(state: dict[str, Any], account: str, now: datetime) -> None:
    e = _entry(state, account, now)
    e["assigned"] += 1


def mark_flood_wait(state: dict[str, Any], account: str, now: datetime) -> None:
    e = _entry(state, account, now)
    e["paused_until"] = (now + timedelta(hours=24)).isoformat()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"cursor": 0, "accounts": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {"cursor": 0, "accounts": {}}
    except Exception:
        return {"cursor": 0, "accounts": {}}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def session_paths() -> list[Path]:
    raw = os.getenv("TELEGRAM_SESSIONS", "").strip()
    if raw:
        paths = [Path(x.strip()) for x in raw.split(",") if x.strip()]
    else:
        directory = Path(os.getenv("TELEGRAM_SESSION_DIR", "/app/sessions"))
        pattern = os.getenv("TELEGRAM_SESSION_GLOB", "session_*.session")
        paths = sorted(directory.glob(pattern))
    return [p for p in paths if p.exists() and not p.name.endswith("-journal")]


def proxy_config() -> dict[str, Any]:
    import python_socks
    kind = os.getenv("TELEGRAM_PROXY_TYPE", "HTTP").upper()
    return {
        "proxy_type": getattr(python_socks.ProxyType, kind, python_socks.ProxyType.HTTP),
        "addr": os.getenv("TELEGRAM_PROXY_ADDR", "vpn"),
        "port": int(os.getenv("TELEGRAM_PROXY_PORT", "10808")),
        "rdns": True,
    }


def save_rows(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


class SheetSync:
    """Пишет результаты проверок в Google-таблицу сразу после каждой строки.

    - Ленивое подключение (при первом результате), token-файл с refresh.
    - Обновление конкретной строки по phone (поиск в закэшированном индексе).
    - Ошибки Google не роняют обход — пишутся в лог, обход продолжается.
    """

    def __init__(self) -> None:
        self._service = None
        self._sheet_name: str | None = None
        self._row_index: dict[str, int] = {}  # phone -> номер строки в таблице
        self._pending: list[tuple[int, list[str]]] = []
        self.errors: list[str] = []

    def _connect(self) -> bool:
        if self._service is not None:
            return True
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(TOKEN_PATH)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
            meta = self._service.spreadsheets().get(spreadsheetId=RESULT_SHEET_ID).execute()
            if RESULT_SHEET_RANGE and RESULT_SHEET_RANGE not in [s["properties"]["title"] for s in meta["sheets"]]:
                first = meta["sheets"][0]["properties"]["title"]
                self._sheet_name = first
            else:
                self._sheet_name = RESULT_SHEET_RANGE
            return True
        except Exception as exc:
            self.errors.append(f"sync-connect: {type(exc).__name__}: {exc}"[:200])
            self._service = None
            return False

    def build_index(self) -> int:
        """Кэширует phone -> строка; вызывается один раз перед обходом."""
        if not self._connect():
            return -1
        try:
            resp = self._service.spreadsheets().values().get(
                spreadsheetId=RESULT_SHEET_ID, range=f"{self._sheet_name}!A2:A"
            ).execute()
            for i, row in enumerate(resp.get("values", []), start=2):
                if row and row[0]:
                    self._row_index[row[0]] = i
            return len(self._row_index)
        except Exception as exc:
            self.errors.append(f"sync-index: {type(exc).__name__}: {exc}"[:200])
            return -1

    def update_row(self, phone: str, values: list[str]) -> None:
        """Обновляет строку по телефону (колонки I..AA = telegram_status..telegram_gender)."""
        if phone not in self._row_index:
            return
        row_no = self._row_index[phone]
        try:
            self._service.spreadsheets().values().update(
                spreadsheetId=RESULT_SHEET_ID,
                range=f"{self._sheet_name}!I{row_no}",
                valueInputOption="RAW",
                body={"values": [values]},
            ).execute()
        except Exception as exc:
            self.errors.append(f"sync-row {phone}: {type(exc).__name__}: {exc}"[:200])


FIELDS_OFFSET = 8  # phone,operator,region,territory,inn,source_prefix,source_from,source_to


def row_values(fields: list[str], row: dict[str, Any]) -> list[str]:
    """Колонки I..AA из dict-строки CSV (telegram_status..telegram_gender)."""
    return [str(row.get(f, "")) for f in fields[FIELDS_OFFSET:]]


async def check_one(client: TelegramClient, phone: str) -> tuple[str, Any | None]:
    contact = types.InputPhoneContact(client_id=0, phone=phone, first_name="Lead", last_name="Check")
    try:
        imported = await asyncio.wait_for(
            client(functions.contacts.ImportContactsRequest([contact])), timeout=30
        )
    except PhoneNotOccupiedError:
        return "absent", None
    users = imported.users or []
    if not users:
        return "absent", None
    user = users[0]
    about = ""
    try:
        full = await asyncio.wait_for(client(functions.users.GetFullUserRequest(id=user)), timeout=30)
        profile_users = getattr(full, "users", None) or []
        if profile_users:
            user = profile_users[0]
        full_user = getattr(full, "full_user", None)
        if full_user is not None:
            about = getattr(full_user, "about", "") or ""
    except Exception:
        pass
    return "present", (user, about)


async def run_rotation(csv_path: Path, state_path: Path, limit: int | None = None) -> dict[str, Any]:
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {"total": 0, "processed": 0, "flood_accounts": [], "remaining": 0}
    fields = list(rows[0])
    pending = [i for i, row in enumerate(rows) if row.get("telegram_status", "") in ("", "not_checked")]
    if limit is not None:
        pending = pending[:limit]
    paths = session_paths()
    accounts = [str(p) for p in paths]
    now = datetime.now(UTC)
    state = load_state(state_path)
    # Do not connect all sessions before the first check: with 100+ accounts,
    # Telegram update sync may stall startup indefinitely. Connect only an account
    # when it is selected for the next phone; keep it connected afterward.
    clients: dict[str, TelegramClient] = {}
    available: list[str] = accounts.copy()
    if not available:
        return {"total": len(rows), "processed": 0, "error": "no_session_files", "remaining": len(pending)}
    print(f"[rotation] кандидатов аккаунтов: {len(available)}; lazy-connect включён", flush=True)
    cursor = int(state.get("cursor", 0)) % len(available)
    result = {"total": len(rows), "requested": len(pending), "processed": 0, "present": 0, "absent": 0, "errors": 0, "flood_accounts": []}
    sync = SheetSync()
    indexed = sync.build_index()
    print(f"[sync] индекс таблицы: {indexed} строк; ошибки: {sync.errors or 'нет'}", flush=True)
    try:
        for idx in pending:
            now = datetime.now(UTC)
            account, account_idx = choose_account(available, state.setdefault("accounts", {}), cursor, now)
            if account is None:
                break
            # Lazy connect and authorization check for the chosen account.
            client = clients.get(account)
            if client is None:
                client = TelegramClient(account, int(os.environ["TELEGRAM_API_ID"]), os.environ["TELEGRAM_API_HASH"], proxy=proxy_config(), connection_retries=1, request_retries=1)
                try:
                    await client.connect()
                    if not await client.is_user_authorized():
                        await client.disconnect()
                        available.remove(account)
                        continue
                    clients[account] = client
                    print(f"[rotation] аккаунт подключён: {Path(account).name}", flush=True)
                except Exception as exc:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    available.remove(account)
                    print(f"[rotation] аккаунт недоступен: {Path(account).name}: {type(exc).__name__}", flush=True)
                    continue
            row = rows[idx]
            phone = "".join(ch for ch in str(row.get("phone", "")) if ch.isdigit())
            if len(phone) != 11:
                row.update(telegram_status="error", check_note="invalid phone format")
                result["errors"] += 1
                mark_assigned(state["accounts"], account, now)
            else:
                mark_assigned(state["accounts"], account, now)
                try:
                    status, payload = await check_one(client, "+" + phone)
                    if status == "present":
                        user, about = payload
                        avatar_url, avatar_error = "", ""
                        try:
                            photos = await client.get_profile_photos(user)
                            if photos:
                                PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
                                fname = f"{phone}_{user.id}.jpg"
                                target = PHOTOS_DIR / fname
                                if not target.exists():
                                    await client.download_media(photos[0], file=str(target))
                                avatar_url = f"{PUBLIC_PHOTO_BASE}/{fname}"
                        except Exception as exc:
                            avatar_error = f"{type(exc).__name__}: {exc}"[:200]
                        row.update(telegram_status="present", check_note=f"Найдено через {Path(account).name}; сообщение не отправлялось", telegram_user_id=str(user.id), telegram_username=getattr(user, "username", "") or "", telegram_first_name=getattr(user, "first_name", "") or "", telegram_last_name=getattr(user, "last_name", "") or "", telegram_bio=about or "", telegram_avatar_present="yes" if avatar_url else "no", telegram_avatar_path=avatar_url, telegram_avatar_error=avatar_error)
                        result["present"] += 1
                    else:
                        row.update(telegram_status="absent", check_note=f"Не найдено через ImportContactsRequest ({Path(account).name}); сообщение не отправлялось", telegram_avatar_present="no", telegram_avatar_path="", telegram_avatar_error="")
                        result["absent"] += 1
                except FloodWaitError as exc:
                    seconds = int(getattr(exc, "seconds", 60))
                    mark_flood_wait(state["accounts"], account, now)
                    row.update(telegram_status="not_checked", check_note=f"FloodWait {seconds}s; аккаунт остановлен на 24 часа")
                    result["flood_accounts"].append({"account": Path(account).name, "seconds": seconds})
                    save_rows(csv_path, rows, fields); save_state(state_path, state)
                    cursor = (account_idx + 1) % len(available)
                    continue
                except Exception as exc:
                    row.update(telegram_status="error", check_note=f"{type(exc).__name__}: {exc}"[:300])
                    result["errors"] += 1
            result["processed"] += 1
            cursor = (account_idx + 1) % len(available)
            state["cursor"] = cursor
            save_rows(csv_path, rows, fields); save_state(state_path, state)
            sync.update_row(row.get("phone", ""), row_values(fields, row))
            await asyncio.sleep(float(os.getenv("TELEGRAM_CHECK_DELAY", "2")))
    finally:
        for client in clients.values():
            await client.disconnect()
    result["remaining"] = sum(r.get("telegram_status", "") in ("", "not_checked") for r in rows)
    result["accounts"] = {Path(k).name: v for k, v in state.get("accounts", {}).items()}
    return result
