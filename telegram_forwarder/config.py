import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import yaml


@dataclass
class FilterConfig:
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    case_sensitive: bool = False
    drop_media: bool = False
    min_length: int = 0


@dataclass
class TelegramTarget:
    chat_id: int | str
    topic_id: Optional[int] = None
    silent: bool = False


@dataclass
class WebhookTarget:
    url: str
    token: Optional[str] = None
    timeout_sec: float = 5.0


@dataclass
class RouteConfig:
    name: str
    sources: List[int | str]
    filters: FilterConfig
    tg_destinations: List[TelegramTarget] = field(default_factory=list)
    webhooks: List[WebhookTarget] = field(default_factory=list)


@dataclass
class MetricsConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 9102


@dataclass
class AppConfig:
    """Top-level daemon configuration loaded from YAML."""
    api_id: int
    api_hash: str
    session_name: str
    routes: List[RouteConfig]
    metrics: MetricsConfig = field(default_factory=MetricsConfig)


def load_config(path: Path) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    routes = []
    for r in raw.get("routes", []):
        filt_raw = r.get("filters", {})
        filt = FilterConfig(
            include_patterns=filt_raw.get("include", []),
            exclude_patterns=filt_raw.get("exclude", []),
            case_sensitive=filt_raw.get("case_sensitive", False),
            drop_media=filt_raw.get("drop_media", False),
            min_length=filt_raw.get("min_length", 0),
        )

        tg_dests = []
        for t in r.get("telegram_targets", []):
            tg_dests.append(
                TelegramTarget(
                    chat_id=t["chat_id"],
                    topic_id=t.get("topic_id"),
                    silent=t.get("silent", False),
                )
            )

        wh_dests = []
        for w in r.get("webhook_targets", []):
            wh_dests.append(
                WebhookTarget(
                    url=w["url"],
                    token=w.get("token"),
                    timeout_sec=float(w.get("timeout", 5.0)),
                )
            )

        routes.append(
            RouteConfig(
                name=r.get("name", "default"),
                sources=r.get("sources", []),
                filters=filt,
                tg_destinations=tg_dests,
                webhooks=wh_dests,
            )
        )

    m_raw = raw.get("metrics", {})
    metrics_cfg = MetricsConfig(
        enabled=m_raw.get("enabled", True),
        host=m_raw.get("host", "127.0.0.1"),
        port=int(m_raw.get("port", 9102)),
    )

    tg_block = raw.get("telegram", {})
    # allow env vars to take precedence for secrets
    api_id_val = os.getenv("TG_API_ID", tg_block.get("api_id"))
    api_hash_val = os.getenv("TG_API_HASH", tg_block.get("api_hash"))

    if not api_id_val or not api_hash_val:
        raise ValueError("TG api_id and api_hash must be set either in config or via env vars")

    return AppConfig(
        api_id=int(api_id_val),
        api_hash=str(api_hash_val),
        session_name=os.getenv("TG_SESSION", tg_block.get("session_name", "forwarder_session")),
        routes=routes,
        metrics=metrics_cfg,
    )
