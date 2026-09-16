from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from _config import load_config
from _utils import normalize_phone


def _require_telethon():
    try:
        from telethon import TelegramClient  # noqa: F401
        from telethon import functions, types  # noqa: F401
    except Exception as exc:
        raise RuntimeError("telethon не установлен. Установи requirements.txt") from exc


def _proxy_config() -> dict[str, Any]:
    import python_socks

    return {
        "proxy_type": python_socks.ProxyType.SOCKS5,
        "addr": os.getenv("TELEGRAM_PROXY_ADDR", "127.0.0.1"),
        "port": int(os.getenv("TELEGRAM_PROXY_PORT", "10808")),
        "rdns": True,
    }


async def _build_client(cfg, *, require_authorized: bool = True):
    _require_telethon()
    from telethon import TelegramClient

    if not cfg.telegram_api_id or not cfg.telegram_api_hash:
        raise RuntimeError("Нужны TELEGRAM_API_ID и TELEGRAM_API_HASH")
    client = TelegramClient(
        str(cfg.telegram_session),
        cfg.telegram_api_id,
        cfg.telegram_api_hash,
        proxy=_proxy_config(),
    )
    await client.connect()
    if require_authorized and not await client.is_user_authorized():
        raise RuntimeError(
            "Telegram userbot не авторизован. Запусти вручную первый логин с TELEGRAM_LOGIN_PHONE."
        )
    return client


async def _resolve_entity(client, target: str):
    from telethon import functions, types

    target = target.strip()
    if target.startswith("@"):
        return await client.get_entity(target)
    normalized = normalize_phone(target)
    digits = "".join(ch for ch in normalized if ch.isdigit())
    if digits:
        contact = types.InputPhoneContact(
            client_id=0,
            phone="+" + digits if not target.startswith("+") else target,
            first_name="Lead",
            last_name="WB",
        )
        result = await client(functions.contacts.ImportContactsRequest([contact]))
        users = result.users or []
        if users:
            return users[0]
    return await client.get_entity(target)


async def cmd_msg(cfg, target: str, text: str) -> dict[str, Any]:
    client = await _build_client(cfg)
    try:
        entity = await _resolve_entity(client, target)
        sent = await client.send_message(entity, text)
        return {
            "ok": True,
            "target": target,
            "message_id": sent.id,
            "date": sent.date.isoformat() if sent.date else "",
            "link": "",
        }
    finally:
        await client.disconnect()


async def cmd_resolve(cfg, target: str) -> dict[str, Any]:
    client = await _build_client(cfg)
    try:
        entity = await _resolve_entity(client, target)
        from telethon import types

        status = getattr(entity, "status", None)
        last_seen_status = "unknown"
        last_seen_at = ""
        expires_at = ""
        if isinstance(status, types.UserStatusOnline):
            last_seen_status = "online"
            expires = getattr(status, "expires", None)
            if expires is not None:
                expires_at = expires.isoformat()
        elif isinstance(status, types.UserStatusOffline):
            last_seen_status = "offline"
            was_online = getattr(status, "was_online", None)
            if was_online is not None:
                last_seen_at = was_online.isoformat()
        elif isinstance(status, types.UserStatusRecently):
            last_seen_status = "recently"
        elif isinstance(status, types.UserStatusLastWeek):
            last_seen_status = "last-week"
        elif isinstance(status, types.UserStatusLastMonth):
            last_seen_status = "last-month"
        elif isinstance(status, types.UserStatusEmpty):
            last_seen_status = "empty"

        return {
            "ok": True,
            "target": target,
            "id": getattr(entity, "id", None),
            "first_name": getattr(entity, "first_name", "") or "",
            "last_name": getattr(entity, "last_name", "") or "",
            "username": getattr(entity, "username", "") or "",
            "phone": getattr(entity, "phone", "") or "",
            "is_bot": bool(getattr(entity, "bot", False)),
            "last_seen_status": last_seen_status,
            "last_seen_at": last_seen_at,
            "expires_at": expires_at,
        }
    finally:
        await client.disconnect()


async def cmd_history(cfg, target: str, limit: int = 80) -> dict[str, Any]:
    client = await _build_client(cfg)
    try:
        entity = await _resolve_entity(client, target)
        events = []
        async for msg in client.iter_messages(entity, limit=limit):
            text = msg.message or ""
            if not text:
                continue
            events.append(
                {
                    "message_id": msg.id,
                    "date": msg.date.isoformat() if msg.date else "",
                    "text": text,
                    "out": bool(msg.out),
                    "reply_to_msg_id": getattr(msg, "reply_to_msg_id", None),
                }
            )
        events.sort(key=lambda x: x.get("date", ""))
        return {
            "ok": True,
            "target": target,
            "peer": {
                "id": getattr(entity, "id", None),
                "first_name": getattr(entity, "first_name", "") or "",
                "last_name": getattr(entity, "last_name", "") or "",
                "username": getattr(entity, "username", "") or "",
                "phone": getattr(entity, "phone", "") or "",
            },
            "events": events,
        }
    finally:
        await client.disconnect()


async def cmd_replies(cfg, since_iso: str = "", limit: int = 100, per_dialog_limit: int = 20) -> dict[str, Any]:
    client = await _build_client(cfg)
    since_dt = datetime.fromisoformat(since_iso) if since_iso else None
    if since_dt and since_dt.tzinfo is None:
        since_dt = since_dt.replace(tzinfo=timezone.utc)
    events = []
    try:
        async for dialog in client.iter_dialogs(limit=limit):
            if not getattr(dialog, "is_user", False):
                continue
            entity = dialog.entity
            phone = getattr(entity, "phone", "") or ""
            username = getattr(entity, "username", "") or ""
            async for msg in client.iter_messages(entity, limit=per_dialog_limit):
                if msg.out:
                    continue
                if since_dt and msg.date and msg.date < since_dt:
                    continue
                if not (msg.message or "").strip():
                    continue
                events.append(
                    {
                        "dialog_id": dialog.id,
                        "phone": normalize_phone(phone) if phone else "",
                        "username": f"@{username}" if username else "",
                        "text": msg.message or "",
                        "date": msg.date.isoformat() if msg.date else "",
                        "message_id": msg.id,
                    }
                )
        events.sort(key=lambda x: x.get("date", ""))
        return {"ok": True, "events": events}
    finally:
        await client.disconnect()


async def cmd_auth_start(cfg) -> dict[str, Any]:
    phone = (cfg.telegram_login_phone or "").strip()
    if not phone:
        raise RuntimeError("Нужен TELEGRAM_LOGIN_PHONE")
    client = await _build_client(cfg, require_authorized=False)
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            return {"ok": True, "authorized": True, "id": me.id, "username": getattr(me, "username", "")}
        result = await client.send_code_request(phone)
        return {
            "ok": True,
            "authorized": False,
            "phone": phone,
            "phone_code_hash": result.phone_code_hash,
            "type": type(result.type).__name__ if getattr(result, "type", None) is not None else "",
        }
    finally:
        await client.disconnect()


async def cmd_auth_finish(cfg, code: str, phone_code_hash: str, password: str = "") -> dict[str, Any]:
    from telethon.errors import SessionPasswordNeededError

    phone = (cfg.telegram_login_phone or "").strip()
    if not phone:
        raise RuntimeError("Нужен TELEGRAM_LOGIN_PHONE")
    client = await _build_client(cfg, require_authorized=False)
    try:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                return {"ok": False, "password_required": True}
            await client.sign_in(password=password)
        me = await client.get_me()
        return {"ok": True, "authorized": True, "id": me.id, "username": getattr(me, "username", "")}
    finally:
        await client.disconnect()


def cli() -> None:
    parser = argparse.ArgumentParser(description="Telegram userbot helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_msg = sub.add_parser("msg")
    p_msg.add_argument("target")
    p_msg.add_argument("text")

    p_resolve = sub.add_parser("resolve")
    p_resolve.add_argument("target")

    p_history = sub.add_parser("history")
    p_history.add_argument("target")
    p_history.add_argument("--limit", type=int, default=80)

    p_replies = sub.add_parser("replies")
    p_replies.add_argument("--since", default="")
    p_replies.add_argument("--limit", type=int, default=100)
    p_replies.add_argument("--per-dialog-limit", type=int, default=20)

    sub.add_parser("auth-check")
    sub.add_parser("auth-start")
    p_auth_finish = sub.add_parser("auth-finish")
    p_auth_finish.add_argument("code")
    p_auth_finish.add_argument("phone_code_hash")
    p_auth_finish.add_argument("--password", default="")

    args = parser.parse_args()
    cfg = load_config()

    async def run():
        if args.cmd == "msg":
            return await cmd_msg(cfg, args.target, args.text)
        if args.cmd == "resolve":
            return await cmd_resolve(cfg, args.target)
        if args.cmd == "history":
            return await cmd_history(cfg, args.target, args.limit)
        if args.cmd == "replies":
            return await cmd_replies(cfg, args.since, args.limit, args.per_dialog_limit)
        if args.cmd == "auth-start":
            return await cmd_auth_start(cfg)
        if args.cmd == "auth-finish":
            return await cmd_auth_finish(cfg, args.code, args.phone_code_hash, args.password)
        client = await _build_client(cfg)
        try:
            me = await client.get_me()
            return {"ok": True, "id": me.id, "username": getattr(me, "username", "")}
        finally:
            await client.disconnect()

    result = asyncio.run(run())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
