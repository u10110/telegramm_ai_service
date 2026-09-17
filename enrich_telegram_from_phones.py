from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from _config import load_config
from _utils import normalize_phone
from _google import update_sheet_cells
from comms import leads


def proxy_config() -> dict[str, Any]:
    import os
    import python_socks
    return {
        "proxy_type": python_socks.ProxyType.SOCKS5,
        "addr": os.getenv("TELEGRAM_PROXY_ADDR", "sing-box"),
        "port": int(os.getenv("TELEGRAM_PROXY_PORT", "10808")),
        "rdns": True,
    }


async def run() -> dict[str, Any]:
    from telethon import TelegramClient, functions, types

    cfg = load_config()
    rows = leads(cfg)
    client = TelegramClient(str(cfg.telegram_session), cfg.telegram_api_id, cfg.telegram_api_hash, proxy=proxy_config())
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram userbot не авторизован")
        result = {"checked": 0, "updated": 0, "skipped_masked": 0, "not_found": 0, "no_public_username": 0, "errors": []}
        seen: set[str] = set()
        for row in rows:
            if str(row.get("Telegram", "") or "").strip():
                continue
            raw = str(row.get("Телефон", "") or "").strip()
            if not raw or "*" in raw:
                result["skipped_masked"] += 1
                continue
            phone = normalize_phone(raw)
            digits = "".join(ch for ch in phone if ch.isdigit())
            if len(digits) != 11 or not digits.startswith("7") or digits in seen:
                continue
            seen.add(digits)
            result["checked"] += 1
            try:
                contact = types.InputPhoneContact(client_id=0, phone="+" + digits, first_name="Lead", last_name="WB")
                imported = await client(functions.contacts.ImportContactsRequest([contact]))
                users = imported.users or []
                if not users:
                    result["not_found"] += 1
                    continue
                entity = users[0]
                username = str(getattr(entity, "username", "") or "").strip()
                if not username:
                    result["no_public_username"] += 1
                    continue
                link = "https://t.me/" + username.lstrip("@")
                update_sheet_cells(cfg, cfg.leads_tab, int(row["_row_num"]), {"Telegram": link})
                result["updated"] += 1
            except Exception as exc:
                result["errors"].append({"row": row.get("_row_num"), "phone": raw[:4] + "***", "error": repr(exc)})
        result["rows_after"] = len(leads(cfg))
        result["filled_after"] = sum(bool(str(r.get("Telegram", "")).strip()) for r in leads(cfg))
        return result
    finally:
        await client.disconnect()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
