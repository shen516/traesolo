"""统一队名解析门面：精确别名 → DB 确认别名 → 模糊子串。"""

from __future__ import annotations

from typing import Optional

from services.real_team_crawler import (
    is_clean_team_id,
    normalize_team_display_name,
    resolve_team_alias,
)


class TeamResolver:
    """薄封装，避免各爬虫维护独立映射表。"""

    @staticmethod
    def normalize(name: Optional[str]) -> str:
        return normalize_team_display_name(name or "") or ""

    @staticmethod
    def resolve(name: Optional[str]) -> Optional[str]:
        return resolve_team_alias(name or "")

    @staticmethod
    def is_clean(team_id: Optional[str]) -> bool:
        return is_clean_team_id(team_id)

    @staticmethod
    def resolve_clean(name: Optional[str]) -> Optional[str]:
        """解析为规范 ID；脏 ID（中文/纯数字）视为未解析。"""
        tid = resolve_team_alias(name or "")
        if tid and is_clean_team_id(tid):
            return tid
        return None


team_resolver = TeamResolver()
