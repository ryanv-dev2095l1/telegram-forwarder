import re
import logging
from typing import List, Optional, Tuple
from telegram_forwarder.config import FilterConfig, RouteConfig

logger = logging.getLogger(__name__)


def _normalize_source_key(src: int | str) -> str:
    s = str(src)
    # telegram channel ids often come as -100xxxxxxxxxx in events
    if s.startswith("-100"):
        return s[4:]
    if s.startswith("-"):
        return s[1:]
    return s


class CompiledFilter:
    def __init__(self, cfg: FilterConfig):
        self.cfg = cfg
        flags = 0 if cfg.case_sensitive else re.IGNORECASE
        self.includes = [re.compile(p, flags) for p in cfg.include_patterns]
        self.excludes = [re.compile(p, flags) for p in cfg.exclude_patterns]

    def matches(self, text: str, has_media: bool = False) -> Tuple[bool, str]:
        # print(f"DEBUG: testing '{text[:30]}' against {len(self.includes)} patterns")
        if len(text.strip()) < self.cfg.min_length:
            return False, "too_short"

        if self.cfg.drop_media and has_media:
            return False, "media_dropped"

        # exclusion takes priority
        for ex in self.excludes:
            if ex.search(text):
                return False, f"excluded_by_{ex.pattern}"

        if not self.includes:
            return True, "all_allowed"

        for inc in self.includes:
            if inc.search(text):
                return True, f"matched_{inc.pattern}"

        return False, "no_include_match"


class RouteEngine:
    """Matches incoming telegram messages against active route configurations."""

    def __init__(self, routes: List[RouteConfig]):
        self.routes = []
        for r in routes:
            compiled = CompiledFilter(r.filters)
            # store both raw and normalized representation to avoid telethon ID mismatch
            src_map = {}
            for s in r.sources:
                src_map[str(s)] = True
                src_map[_normalize_source_key(s)] = True
            self.routes.append((r, compiled, src_map))

    def resolve(self, source_id: int | str, text: Optional[str], has_media: bool = False) -> List[RouteConfig]:
        body = text or ""
        str_id = str(source_id)
        norm_id = _normalize_source_key(source_id)
        matching_routes = []

        for route, compiled, sources in self.routes:
            if "*" not in sources and str_id not in sources and norm_id not in sources:
                continue

            ok, reason = compiled.matches(body, has_media=has_media)
            logger.debug("route '%s' src=%s -> %s (%s)", route.name, source_id, ok, reason)
            if ok:
                matching_routes.append(route)

        return matching_routes
