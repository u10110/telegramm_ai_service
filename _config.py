from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


LEADS_HEADERS = [
    "ID",
    "Дата",
    "Компания",
    "ИНН",
    "SKU",
    "Рейтинг",
    "Категория",
    "Регион",
    "Адрес",
    "Email",
    "Телефон",
    "Score",
    "Причина",
    "Статус",
    "Дата касания",
    "История",
    "ФИО",
    "Telegram",
]

COMMS_HEADERS = [
    "Компания",
    "ИНН",
    "Канал",
    "Куда отправлено",
    "Статус",
    "Дата отправки",
    "Текст касания",
    "Ссылка на Telegram",
    "Ссылка на письмо",
    "Ответ / комментарий",
]

REPLY_LOG_HEADERS = [
    "ID",
    "Дата лида",
    "Компания",
    "ИНН",
    "SKU",
    "Рейтинг",
    "Категория",
    "Регион",
    "Адрес",
    "Email",
    "Телефон",
    "Score",
    "Причина",
    "Статус до ответа",
    "Статус после ответа",
    "Hot lead статус",
    "Дата касания",
    "История",
    "ФИО",
    "Канал ответа",
    "Откуда ответ",
    "Время ответа",
    "Текст ответа",
    "Нужен автоответ",
    "Текст автоответа",
    "Комментарий менеджеру",
    "Ссылка на Telegram",
    "Ссылка на письмо",
    "ID входящего сообщения",
    "Thread / Dialog ID",
    "ID автоответа",
    "Handoff статус",
    "Handoff причина",
    "Handoff маршрут",
]

DEFAULT_DENYLIST = [
    "холодильник",
    "стиральн",
    "плита",
    "телевиз",
    "лестниц",
    "бензин",
    "лак",
    "аэрозол",
    "пиротех",
    "диван",
    "кровать",
    "матрас",
    "цифров",
    "сервис",
]


DEFAULT_OPERATIONAL_TUNING = {
    "collect": {
        "interval_seconds": 1800,
        "timeout_seconds": 1500,
        "term_grace_seconds": 20,
        "chunk_max_seconds": 900,
        "chunk_max_categories": 10,
        "enrich_max_seconds": 8,
        "daily_target": 50,
        "batch_size": 20,
        "pages": 2,
        "limit_sellers": 25,
        "max_categories": 40,
    },
    "touch": {
        "run_limit": 25,
        "telegram_daily_limit": 7,
        "telegram_first_touch_daily_limit": 7,
        "telegram_second_touch_daily_limit": 2,
        "telegram_cooldown_seconds": 2400,
        "telegram_cooldown_jitter_seconds": 600,
        "telegram_start_hour_msk": 9,
        "telegram_end_hour_msk": 20,
        "telegram_last_seen_max_age_days": 0,
        "second_touch_delay_hours": 48,
        "email_daily_limit": 0,
        "email_hourly_limit": 20,
        "email_start_hour_msk": 9,
        "email_end_hour_msk": 20,
    },
    "replies": {
        "gmail_window_hours": 72,
        "history_limit": 80,
        "telegram_fetch_limit": 100,
        "telegram_dialog_message_limit": 20,
        "gmail_max_results": 50,
        "gmail_max_pages": 10,
    },
}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return float(raw)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_env_file(base_dir: Path) -> None:
    env_path = base_dir / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _load_operational_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as fh:
            payload = tomllib.load(fh)
    except Exception as exc:
        raise RuntimeError(f"Не удалось прочитать operational config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Operational config {path} должен быть TOML-объектом верхнего уровня")
    return payload


def _section_dict(payload: dict[str, Any], section: str) -> dict[str, Any]:
    raw = payload.get(section, {})
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise RuntimeError(f"Operational config section [{section}] должен быть TOML-таблицей")
    return raw


def _section_int(section: dict[str, Any], *, section_name: str, key: str, default: int, minimum: int = 0) -> int:
    if key not in section:
        return default
    raw = section.get(key)
    try:
        value = int(raw)
    except Exception as exc:
        raise RuntimeError(f"Operational config [{section_name}].{key} должен быть целым числом, получено: {raw!r}") from exc
    if value < minimum:
        raise RuntimeError(f"Operational config [{section_name}].{key} должен быть >= {minimum}, получено: {value}")
    return value


@dataclass(slots=True)
class Config:
    base_dir: Path
    camofox_base: str = field(default_factory=lambda: os.getenv("WB_CAMOFOX_BASE", "http://camofox:9377"))
    camofox_user_id: str = field(default_factory=lambda: os.getenv("WB_CAMOFOX_USER_ID", "hermes_fc74fa3eb7"))
    wb_dest: str = field(default_factory=lambda: os.getenv("WB_DEST", "-1257786"))
    wb_lang: str = field(default_factory=lambda: os.getenv("WB_LANG", "ru"))
    wb_locale: str = field(default_factory=lambda: os.getenv("WB_LOCALE", "ru"))
    wb_currency: str = field(default_factory=lambda: os.getenv("WB_CURR", "rub"))
    wb_spp: str = field(default_factory=lambda: os.getenv("WB_SPP", "30"))
    wb_hide_dtype: str = field(default_factory=lambda: os.getenv("WB_HIDE_DTYPE", "15"))
    wb_hide_vflags: str = field(default_factory=lambda: os.getenv("WB_HIDE_VFLAGS", "4294967296"))
    wb_menu_url: str = field(default_factory=lambda: os.getenv("WB_MENU_URL", "https://static-basket-01.wbbasket.ru/vol0/data/main-menu-ru-ru-v3.json"))
    wb_category_limit: int = field(default_factory=lambda: _env_int("WB_CATEGORY_LIMIT", 0))
    pages_per_cat: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["pages"])
    max_sku_checks_per_cat: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["limit_sellers"])
    sku_min: int = field(default_factory=lambda: _env_int("SKU_MIN", 300))
    sku_max: int = field(default_factory=lambda: _env_int("SKU_MAX", 15000))
    max_revenue: int = field(default_factory=lambda: _env_int("MAX_REVENUE", 500_000_000))
    parser_min_sku: int = field(default_factory=lambda: _env_int("PARSER_MIN_SKU", 1000))
    denylist: list[str] = field(default_factory=lambda: [x for x in os.getenv("WB_DENYLIST", "|".join(DEFAULT_DENYLIST)).split("|") if x])
    sheet_id: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEET_ID", ""))
    leads_tab: str = field(default_factory=lambda: os.getenv("GOOGLE_LEADS_TAB", "Leads"))
    comms_tab: str = field(default_factory=lambda: os.getenv("GOOGLE_COMMS_TAB", "Коммуникации"))
    reply_log_tab: str = field(default_factory=lambda: os.getenv("GOOGLE_REPLY_LOG_TAB", "Ответы"))
    google_token_path: Path = field(default_factory=lambda: Path(os.getenv("GOOGLE_TOKEN_PATH", "/root/.hermes/google_token.json")))
    google_client_secret_path: Path = field(default_factory=lambda: Path(os.getenv("GOOGLE_CLIENT_SECRET_PATH", "/root/.hermes/google_client_secret.json")))
    dadata_token: str = field(default_factory=lambda: os.getenv("DADATA_TOKEN", ""))
    dadata_secret: str = field(default_factory=lambda: os.getenv("DADATA_SECRET", ""))
    checko_project_id: str = field(default_factory=lambda: os.getenv("CHECKO_PROJECT_ID", "0"))
    telegram_api_id: int = field(default_factory=lambda: _env_int("TELEGRAM_API_ID", 0))
    telegram_api_hash: str = field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH", ""))
    telegram_session: Path = field(default_factory=lambda: Path(os.getenv("TELEGRAM_SESSION", "./telegram_userbot.session")))
    telegram_login_phone: str = field(default_factory=lambda: os.getenv("TELEGRAM_LOGIN_PHONE", ""))
    manager_bot_token: str = field(default_factory=lambda: os.getenv("MANAGER_BOT_TOKEN", ""))
    gmail_from_name: str = field(default_factory=lambda: os.getenv("GMAIL_FROM_NAME", "WB Leadgen"))
    gmail_from_email: str = field(default_factory=lambda: os.getenv("GMAIL_FROM_EMAIL", ""))
    touch_email_override: str = field(default_factory=lambda: os.getenv("TOUCH_EMAIL_OVERRIDE", "").strip())
    touch_telegram_override: str = field(default_factory=lambda: os.getenv("TOUCH_TELEGRAM_OVERRIDE", "").strip())
    touch_email_subject: str = field(default_factory=lambda: os.getenv("TOUCH_EMAIL_SUBJECT", "Партнёрство по вашему бренду на маркетплейсах"))
    touch_offer_path_raw: str = field(default_factory=lambda: os.getenv("TOUCH_OFFER_PATH", "./first_touch_offer.txt"))
    touch_telegram_offer_path_raw: str = field(default_factory=lambda: os.getenv("TOUCH_TELEGRAM_OFFER_PATH", "./first_touch_offer_telegram.txt"))
    second_touch_offer_path_raw: str = field(default_factory=lambda: os.getenv("SECOND_TOUCH_OFFER_PATH", "./second_touch_offer.txt"))
    second_touch_telegram_offer_path_raw: str = field(default_factory=lambda: os.getenv("SECOND_TOUCH_TELEGRAM_OFFER_PATH", "./second_touch_offer_telegram.txt"))
    touch_tg_daily_limit: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["telegram_daily_limit"])
    touch_tg_first_touch_daily_limit: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["telegram_first_touch_daily_limit"])
    touch_tg_second_touch_daily_limit: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["telegram_second_touch_daily_limit"])
    touch_tg_cooldown_seconds: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["telegram_cooldown_seconds"])
    touch_tg_cooldown_jitter_seconds: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["telegram_cooldown_jitter_seconds"])
    touch_tg_start_hour_msk: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["telegram_start_hour_msk"])
    touch_tg_end_hour_msk: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["telegram_end_hour_msk"])
    touch_tg_last_seen_max_age_days: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["telegram_last_seen_max_age_days"])
    touch_second_delay_hours: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["second_touch_delay_hours"])
    touch_email_daily_limit: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["email_daily_limit"])
    touch_email_hourly_limit: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["email_hourly_limit"])
    touch_email_start_hour_msk: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["email_start_hour_msk"])
    touch_email_end_hour_msk: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["email_end_hour_msk"])
    touch_run_limit: int = field(default=DEFAULT_OPERATIONAL_TUNING["touch"]["run_limit"])
    reply_history_limit: int = field(default=DEFAULT_OPERATIONAL_TUNING["replies"]["history_limit"])
    replies_gmail_window_hours: int = field(default=DEFAULT_OPERATIONAL_TUNING["replies"]["gmail_window_hours"])
    replies_telegram_fetch_limit: int = field(default=DEFAULT_OPERATIONAL_TUNING["replies"]["telegram_fetch_limit"])
    replies_telegram_dialog_message_limit: int = field(default=DEFAULT_OPERATIONAL_TUNING["replies"]["telegram_dialog_message_limit"])
    replies_gmail_max_results: int = field(default=DEFAULT_OPERATIONAL_TUNING["replies"]["gmail_max_results"])
    replies_gmail_max_pages: int = field(default=DEFAULT_OPERATIONAL_TUNING["replies"]["gmail_max_pages"])
    collect_interval_seconds: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["interval_seconds"])
    collect_timeout_seconds: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["timeout_seconds"])
    collect_term_grace_seconds: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["term_grace_seconds"])
    collect_chunk_max_seconds: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["chunk_max_seconds"])
    collect_chunk_max_categories: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["chunk_max_categories"])
    collect_enrich_max_seconds: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["enrich_max_seconds"])
    collect_daily_target: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["daily_target"])
    collect_batch_size: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["batch_size"])
    collect_pages: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["pages"])
    collect_limit_sellers: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["limit_sellers"])
    collect_max_categories: int = field(default=DEFAULT_OPERATIONAL_TUNING["collect"]["max_categories"])
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    touch_score_min: float = field(default_factory=lambda: _env_float("TOUCH_SCORE_MIN", 0.0))
    dry_run: bool = field(default_factory=lambda: _env_bool("DRY_RUN", False))
    operational_config_path: Path = field(default_factory=lambda: Path("operational_config.toml"))

    @property
    def seen_path(self) -> Path:
        return self.base_dir / "seen.json"

    @property
    def state_path(self) -> Path:
        return self.base_dir / "state.json"

    @property
    def cats_path(self) -> Path:
        return self.base_dir / "cats.json"

    @property
    def touch_state_path(self) -> Path:
        return self.base_dir / "touch_state.json"

    @property
    def replies_state_path(self) -> Path:
        return self.base_dir / "replies_state.json"

    @property
    def runs_log_path(self) -> Path:
        return self.base_dir / "runs.log"

    @property
    def handoff_target_path(self) -> Path:
        return self.base_dir / "handoff_target.json"

    @property
    def output_dir(self) -> Path:
        return self.base_dir / "output"

    @property
    def touch_offer_path(self) -> Path:
        raw = self.touch_offer_path_raw.strip()
        if not raw:
            return self.base_dir / "first_touch_offer.txt"
        path = Path(raw)
        return path if path.is_absolute() else (self.base_dir / path)

    @property
    def touch_telegram_offer_path(self) -> Path:
        raw = self.touch_telegram_offer_path_raw.strip()
        if not raw:
            return self.base_dir / "first_touch_offer_telegram.txt"
        path = Path(raw)
        return path if path.is_absolute() else (self.base_dir / path)

    @property
    def second_touch_offer_path(self) -> Path:
        raw = self.second_touch_offer_path_raw.strip()
        if not raw:
            return self.base_dir / "second_touch_offer.txt"
        path = Path(raw)
        return path if path.is_absolute() else (self.base_dir / path)

    @property
    def second_touch_telegram_offer_path(self) -> Path:
        raw = self.second_touch_telegram_offer_path_raw.strip()
        if not raw:
            return self.base_dir / "second_touch_offer_telegram.txt"
        path = Path(raw)
        return path if path.is_absolute() else (self.base_dir / path)

    def ensure_dirs(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


def _apply_operational_tuning(cfg: Config) -> None:
    cfg.operational_config_path = cfg.base_dir / "operational_config.toml"
    payload = _load_operational_file(cfg.operational_config_path)
    collect = _section_dict(payload, "collect")
    touch = _section_dict(payload, "touch")
    replies = _section_dict(payload, "replies")

    cfg.collect_interval_seconds = _section_int(collect, section_name="collect", key="interval_seconds", default=cfg.collect_interval_seconds, minimum=1)
    cfg.collect_timeout_seconds = _section_int(collect, section_name="collect", key="timeout_seconds", default=cfg.collect_timeout_seconds, minimum=1)
    cfg.collect_term_grace_seconds = _section_int(collect, section_name="collect", key="term_grace_seconds", default=cfg.collect_term_grace_seconds, minimum=1)
    cfg.collect_chunk_max_seconds = _section_int(collect, section_name="collect", key="chunk_max_seconds", default=cfg.collect_chunk_max_seconds, minimum=0)
    cfg.collect_chunk_max_categories = _section_int(collect, section_name="collect", key="chunk_max_categories", default=cfg.collect_chunk_max_categories, minimum=0)
    cfg.collect_enrich_max_seconds = _section_int(collect, section_name="collect", key="enrich_max_seconds", default=cfg.collect_enrich_max_seconds, minimum=1)
    cfg.collect_daily_target = _section_int(collect, section_name="collect", key="daily_target", default=cfg.collect_daily_target, minimum=0)
    cfg.collect_batch_size = _section_int(collect, section_name="collect", key="batch_size", default=cfg.collect_batch_size, minimum=1)
    cfg.collect_pages = _section_int(collect, section_name="collect", key="pages", default=cfg.collect_pages, minimum=1)
    cfg.collect_limit_sellers = _section_int(collect, section_name="collect", key="limit_sellers", default=cfg.collect_limit_sellers, minimum=1)
    cfg.collect_max_categories = _section_int(collect, section_name="collect", key="max_categories", default=cfg.collect_max_categories, minimum=1)

    cfg.touch_run_limit = _section_int(touch, section_name="touch", key="run_limit", default=cfg.touch_run_limit, minimum=1)
    legacy_tg_daily_limit = _section_int(touch, section_name="touch", key="telegram_daily_limit", default=cfg.touch_tg_daily_limit, minimum=0)
    cfg.touch_tg_first_touch_daily_limit = _section_int(
        touch,
        section_name="touch",
        key="telegram_first_touch_daily_limit",
        default=legacy_tg_daily_limit,
        minimum=0,
    )
    cfg.touch_tg_second_touch_daily_limit = _section_int(
        touch,
        section_name="touch",
        key="telegram_second_touch_daily_limit",
        default=cfg.touch_tg_second_touch_daily_limit,
        minimum=0,
    )
    cfg.touch_tg_daily_limit = cfg.touch_tg_first_touch_daily_limit
    cfg.touch_tg_cooldown_seconds = _section_int(touch, section_name="touch", key="telegram_cooldown_seconds", default=cfg.touch_tg_cooldown_seconds, minimum=0)
    cfg.touch_tg_cooldown_jitter_seconds = _section_int(touch, section_name="touch", key="telegram_cooldown_jitter_seconds", default=cfg.touch_tg_cooldown_jitter_seconds, minimum=0)
    cfg.touch_tg_start_hour_msk = _section_int(touch, section_name="touch", key="telegram_start_hour_msk", default=cfg.touch_tg_start_hour_msk, minimum=0)
    cfg.touch_tg_end_hour_msk = _section_int(touch, section_name="touch", key="telegram_end_hour_msk", default=cfg.touch_tg_end_hour_msk, minimum=0)
    cfg.touch_tg_last_seen_max_age_days = _section_int(touch, section_name="touch", key="telegram_last_seen_max_age_days", default=cfg.touch_tg_last_seen_max_age_days, minimum=0)
    cfg.touch_second_delay_hours = _section_int(touch, section_name="touch", key="second_touch_delay_hours", default=cfg.touch_second_delay_hours, minimum=0)
    cfg.touch_email_daily_limit = _section_int(touch, section_name="touch", key="email_daily_limit", default=cfg.touch_email_daily_limit, minimum=0)
    cfg.touch_email_hourly_limit = _section_int(touch, section_name="touch", key="email_hourly_limit", default=cfg.touch_email_hourly_limit, minimum=0)
    cfg.touch_email_start_hour_msk = _section_int(touch, section_name="touch", key="email_start_hour_msk", default=cfg.touch_email_start_hour_msk, minimum=0)
    cfg.touch_email_end_hour_msk = _section_int(touch, section_name="touch", key="email_end_hour_msk", default=cfg.touch_email_end_hour_msk, minimum=0)

    if cfg.touch_tg_start_hour_msk > 23:
        raise RuntimeError(f"Operational config [touch].telegram_start_hour_msk должен быть <= 23, получено: {cfg.touch_tg_start_hour_msk}")
    if cfg.touch_tg_end_hour_msk > 24:
        raise RuntimeError(f"Operational config [touch].telegram_end_hour_msk должен быть <= 24, получено: {cfg.touch_tg_end_hour_msk}")
    if cfg.touch_tg_start_hour_msk >= cfg.touch_tg_end_hour_msk:
        raise RuntimeError(
            f"Operational config [touch].telegram_start_hour_msk должен быть < telegram_end_hour_msk, получено: "
            f"{cfg.touch_tg_start_hour_msk} >= {cfg.touch_tg_end_hour_msk}"
        )
    if cfg.touch_email_start_hour_msk > 23:
        raise RuntimeError(f"Operational config [touch].email_start_hour_msk должен быть <= 23, получено: {cfg.touch_email_start_hour_msk}")
    if cfg.touch_email_end_hour_msk > 24:
        raise RuntimeError(f"Operational config [touch].email_end_hour_msk должен быть <= 24, получено: {cfg.touch_email_end_hour_msk}")
    if cfg.touch_email_start_hour_msk >= cfg.touch_email_end_hour_msk:
        raise RuntimeError(
            f"Operational config [touch].email_start_hour_msk должен быть < email_end_hour_msk, получено: "
            f"{cfg.touch_email_start_hour_msk} >= {cfg.touch_email_end_hour_msk}"
        )

    cfg.replies_gmail_window_hours = _section_int(replies, section_name="replies", key="gmail_window_hours", default=cfg.replies_gmail_window_hours, minimum=1)
    cfg.reply_history_limit = _section_int(replies, section_name="replies", key="history_limit", default=cfg.reply_history_limit, minimum=1)
    cfg.replies_telegram_fetch_limit = _section_int(replies, section_name="replies", key="telegram_fetch_limit", default=cfg.replies_telegram_fetch_limit, minimum=1)
    cfg.replies_telegram_dialog_message_limit = _section_int(replies, section_name="replies", key="telegram_dialog_message_limit", default=cfg.replies_telegram_dialog_message_limit, minimum=1)
    cfg.replies_gmail_max_results = _section_int(replies, section_name="replies", key="gmail_max_results", default=cfg.replies_gmail_max_results, minimum=1)
    cfg.replies_gmail_max_pages = _section_int(replies, section_name="replies", key="gmail_max_pages", default=cfg.replies_gmail_max_pages, minimum=1)

    cfg.pages_per_cat = cfg.collect_pages
    cfg.max_sku_checks_per_cat = cfg.collect_limit_sellers


def load_config(base_dir: str | Path | None = None) -> Config:
    here = Path(base_dir or Path(__file__).resolve().parent)
    _load_env_file(here)
    cfg = Config(base_dir=here)
    _apply_operational_tuning(cfg)
    cfg.ensure_dirs()
    return cfg


def load_handoff_target(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
