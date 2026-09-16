from __future__ import annotations

import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from html import unescape
from typing import Iterable

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ru,en;q=0.8",
}

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+7|8)[\s\-()]*\d[\d\s\-()]{8,}\d")
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
INSTAGRAM_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]+)", re.I)
TELEGRAM_URL_RE = re.compile(r"https?://(?:t\.me|telegram\.me)/[A-Za-z0-9_+/?=-]+", re.I)
TAG_RE = re.compile(r"<[^>]+>")

_RESERVED_EMAIL_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
    "localhost",
}
_FAKE_EMAIL_TLDS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "svg",
    "webp",
    "avif",
    "ico",
    "bmp",
    "tiff",
    "css",
    "js",
    "map",
    "woff",
    "woff2",
    "ttf",
    "eot",
    "otf",
    "mp3",
    "mp4",
    "webm",
    "pdf",
}

_COMPANY_STOPWORDS = {
    "ооо",
    "зао",
    "пао",
    "ао",
    "ип",
    "llc",
    "inc",
    "ltd",
    "company",
    "компания",
    "общество",
    "ограниченной",
    "ответственностью",
    "индивидуальный",
    "предприниматель",
}

_LEGAL_LABEL_HINTS = (
    "инн",
    "огрн",
    "кпп",
    "реквизит",
    "юридичес",
    "организац",
    "наименован",
)

_CONTACT_LABEL_HINTS = (
    "email",
    "e-mail",
    "почта",
    "телефон",
    "тел.",
    "контакт",
    "сайт",
    "web",
)

_BLOCK_PATTERNS = [
    re.compile(r"<table\b.*?</table>", re.I | re.S),
    re.compile(r"<section\b.*?</section>", re.I | re.S),
    re.compile(r"<article\b.*?</article>", re.I | re.S),
    re.compile(r"<dl\b.*?</dl>", re.I | re.S),
    re.compile(r"<(?:ul|ol)\b.*?</(?:ul|ol)>", re.I | re.S),
    re.compile(r"<div[^>]+(?:company|card|detail|contact|rekvizit|requisite|props|org|about)[^>]*>.*?</div>", re.I | re.S),
]

_ROW_BLOCK_RE = re.compile(r"<(?:tr|li|p|dd|dt)\b.*?</(?:tr|li|p|dd|dt)>", re.I | re.S)


def http_get_text(url: str, *, timeout: int = 30, headers: dict[str, str] | None = None) -> str:
    bypass = str(os.getenv("WB_FORCE_DIRECT_HTTP_HOSTS", "") or "").strip()
    if bypass:
        hosts = [item.strip().lower() for item in bypass.split(",") if item.strip()]
        host = urllib.parse.urlsplit(url).hostname or ""
        if host.lower() in hosts:
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
            req = urllib.request.Request(url, headers={**DEFAULT_HEADERS, **(headers or {})})
            with opener.open(req, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
    req = urllib.request.Request(url, headers={**DEFAULT_HEADERS, **(headers or {})})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
        return response.read().decode("utf-8", errors="replace")


def http_get_json(url: str, *, timeout: int = 30, headers: dict[str, str] | None = None) -> dict:
    return json.loads(http_get_text(url, timeout=timeout, headers=headers))


def http_post_json(url: str, payload: dict, *, timeout: int = 30, headers: dict[str, str] | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **DEFAULT_HEADERS, **(headers or {})},
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def strip_html(text: str) -> str:
    clean = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", unescape(clean)).strip()


def fake_email(raw: str) -> bool:
    normalized = str(raw or "").strip().lower().rstrip(".,;)")
    if not normalized or "@" not in normalized:
        return True
    local, _, domain = normalized.partition("@")
    if not local or not domain:
        return True
    domain = domain.strip(".")
    if domain in _RESERVED_EMAIL_DOMAINS:
        return True
    if domain.endswith(".example") or domain.endswith(".localhost") or domain.endswith(".local"):
        return True
    labels = [label for label in domain.split(".") if label]
    if not labels:
        return True
    if labels[-1] in _FAKE_EMAIL_TLDS:
        return True
    return False


def extract_emails(text: str) -> list[str]:
    out = []
    seen = set()
    for email in EMAIL_RE.findall(text or ""):
        normalized = email.strip().lower().rstrip(".,;)")
        if normalized and normalized not in seen and not fake_email(normalized):
            seen.add(normalized)
            out.append(normalized)
    return out


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _company_tokens(company: str) -> list[str]:
    raw = strip_html(str(company or "")).lower()
    raw = re.sub(r"[^a-zа-я0-9]+", " ", raw, flags=re.I)
    tokens = []
    for token in raw.split():
        if len(token) < 4:
            continue
        if token in _COMPANY_STOPWORDS:
            continue
        tokens.append(token)
    return _dedupe_keep_order(tokens)


def _candidate_contact_blocks(html: str) -> list[str]:
    source = str(html or "")
    blocks: list[str] = []
    for pattern in _BLOCK_PATTERNS:
        blocks.extend(match.group(0) for match in pattern.finditer(source))
    blocks.extend(match.group(0) for match in _ROW_BLOCK_RE.finditer(source))
    if not blocks:
        blocks = [
            chunk
            for chunk in re.split(r"(?i)</(?:div|section|article|table|tr|li|p|dd|dt)>", source)
            if chunk.strip()
        ]
    return _dedupe_keep_order(blocks)


def _block_is_entity_bound(block_html: str, *, inn: str = "", company: str = "") -> bool:
    text = strip_html(block_html).lower()
    if not text:
        return False
    digits = re.sub(r"\D+", "", text)
    inn_digits = re.sub(r"\D+", "", str(inn or ""))
    if inn_digits and inn_digits in digits:
        return True
    tokens = _company_tokens(company)
    if tokens:
        hits = sum(1 for token in tokens if token in text)
        if hits >= min(2, len(tokens)):
            return True
        if hits >= 1 and any(hint in text for hint in _LEGAL_LABEL_HINTS):
            return True
    return False


def extract_entity_bound_contacts(html: str, *, inn: str = "", company: str = "") -> dict[str, list[str]]:
    emails: list[str] = []
    phones: list[str] = []
    urls: list[str] = []
    for block in _candidate_contact_blocks(html):
        if not _block_is_entity_bound(block, inn=inn, company=company):
            continue
        text = strip_html(block).lower()
        if not any(hint in text for hint in _CONTACT_LABEL_HINTS):
            continue
        emails.extend(extract_emails(block))
        phones.extend(extract_phones(block))
        urls.extend(extract_urls(block))
    return {
        "emails": _dedupe_keep_order(emails),
        "phones": _dedupe_keep_order(phones),
        "urls": _dedupe_keep_order(urls),
    }


def normalize_phone(raw: str) -> str:
    raw = (raw or "").strip()
    digits = re.sub(r"\D+", "", raw)
    if len(digits) == 11 and raw.startswith("8"):
        return "+7" + digits[1:]
    if len(digits) == 11 and raw.startswith("+") and digits.startswith("7"):
        return "+" + digits
    return raw


def valid_phone(raw: str) -> bool:
    return is_mobile(raw)


def fake_phone(raw: str) -> bool:
    digits = re.sub(r"\D+", "", raw or "")
    if not digits:
        return True
    if digits in {"79999999999", "78888888888", "80000000000"}:
        return True
    if len(set(digits)) <= 2:
        return True
    return False


def is_mobile(raw: str) -> bool:
    raw = (raw or "").strip()
    digits = re.sub(r"\D+", "", raw)
    if len(digits) != 11:
        return False
    if raw.startswith("+"):
        return digits.startswith("79")
    if raw.startswith("8"):
        return digits.startswith("89")
    return False


def extract_phones(text: str) -> list[str]:
    out = []
    seen = set()
    for phone in PHONE_RE.findall(text or ""):
        normalized = normalize_phone(phone)
        if normalized and normalized not in seen and valid_phone(normalized) and not fake_phone(normalized):
            seen.add(normalized)
            out.append(normalized)
    return out


def pick_phone(candidates: Iterable[str]) -> str:
    mobile: list[str] = []
    for candidate in candidates:
        normalized = normalize_phone(candidate)
        if not valid_phone(normalized) or fake_phone(normalized):
            continue
        mobile.append(normalized)
    return (mobile or [""])[0]


def extract_urls(text: str) -> list[str]:
    return list(dict.fromkeys(URL_RE.findall(text or "")))


def extract_telegram_urls(text: str) -> list[str]:
    """Extract public Telegram links; do not infer private accounts from phone numbers."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in TELEGRAM_URL_RE.findall(text or ""):
        url = raw.rstrip(".,;:)]}").split("?")[0].rstrip("/")
        if url and url.lower() not in seen:
            seen.add(url.lower())
            out.append(url)
    return out


def guess_domains_from_brand(brand: str) -> list[str]:
    brand = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", " ", brand or "").strip().lower()
    if not brand:
        return []
    slug = re.sub(r"\s+", "", brand)
    latin = slug.encode("ascii", errors="ignore").decode("ascii")
    candidates = [slug, latin]
    out: list[str] = []
    for item in candidates:
        item = item.strip("-._")
        if not item:
            continue
        for tld in (".ru", ".com", ".rf"):
            out.append(f"https://{item}{tld}")
    return list(dict.fromkeys(out))


def parse_query_string(qs: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(qs, keep_blank_values=True))
