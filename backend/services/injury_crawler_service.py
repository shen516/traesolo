"""ESPN 伤病采集 → 临场 RiskAlert(type=injury)。

仅作竞技分析风控提示，不构成投注建议。
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class InjuryCrawlerService:
    def crawl_priority_injuries(self, crawl_type: str = "scheduled") -> dict:
        from db.database import SessionLocal
        from services.crawler_service import crawler_service
        from services.real_team_crawler import (
            ESPN_LEAGUE_MAP,
            get_priority_leagues,
            get_extended_leagues,
            get_p3_dual_leagues,
        )

        start = datetime.now()
        team_crawler = getattr(crawler_service, "_team_crawler", None)
        if not team_crawler:
            return {"status": "failed", "error": "team crawler unavailable", "created": 0}

        allow = set(get_priority_leagues()) | set(get_extended_leagues()) | set(get_p3_dual_leagues()) | {"WC", "EC"}
        leagues = [lid for lid in allow if lid in ESPN_LEAGUE_MAP]
        # 稳定顺序：重点 → 扩展 → P3 双源 → 其余
        order = list(get_priority_leagues()) + list(get_extended_leagues()) + list(get_p3_dual_leagues()) + ["WC", "EC"]
        seen = set()
        ordered = []
        for lid in order:
            if lid in leagues and lid not in seen:
                seen.add(lid)
                ordered.append(lid)
        leagues = ordered
        injuries_by_team: Dict[str, List[dict]] = {}
        fetched_teams = 0
        errors: List[str] = []

        for lid in leagues:
            espn_code = ESPN_LEAGUE_MAP[lid]
            try:
                mapping, rows = self._crawl_league_injuries(team_crawler, lid, espn_code)
                fetched_teams += len(mapping)
                for tid, items in rows.items():
                    injuries_by_team.setdefault(tid, []).extend(items)
            except Exception as e:
                errors.append(f"{lid}: {e}")
                logger.warning("injury crawl failed for %s: %s", lid, e)
            time.sleep(0.15)

        db = SessionLocal()
        try:
            created = self._write_match_alerts(db, injuries_by_team)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("injury alert persist failed: %s", e)
            return {
                "status": "failed",
                "error": str(e),
                "created": 0,
                "teams_scanned": fetched_teams,
                "injury_rows": sum(len(v) for v in injuries_by_team.values()),
            }
        finally:
            db.close()

        duration_ms = int((datetime.now() - start).total_seconds() * 1000)
        payload = {
            "status": "success",
            "leagues": leagues,
            "teams_scanned": fetched_teams,
            "injury_rows": sum(len(v) for v in injuries_by_team.values()),
            "alerts_upserted": created,
            "errors": errors[:5],
            "duration_ms": duration_ms,
        }
        try:
            crawler_service._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="injury",
                league_id=None,
                league_name="伤病采集",
                found_count=payload["injury_rows"],
                saved_count=created,
                updated_count=created,
                status="success" if created or not errors else "failed",
                crawled_data=__import__("json").dumps(payload, ensure_ascii=False, default=str),
                started_at=start,
                finished_at=datetime.now(),
                duration_ms=duration_ms,
                error_message="; ".join(errors[:3]) if errors else None,
            )
        except Exception:
            pass
        return payload

    def _crawl_league_injuries(self, team_crawler, league_id: str, espn_code: str) -> Tuple[Dict[str, str], Dict[str, List[dict]]]:
        """返回 (espn_id→team_id, team_id→injury list)。"""
        teams = team_crawler._crawl_espn(league_id, espn_code) or []
        mapping = {}
        for t in teams:
            espn_id = str(t.get("espn_id") or "").strip()
            tid = str(t.get("id") or "").strip()
            if espn_id and tid:
                mapping[espn_id] = tid

        by_team: Dict[str, List[dict]] = {}
        # 优先联赛级 injuries
        league_rows = self._fetch_league_injuries(team_crawler, espn_code)
        if league_rows:
            for row in league_rows:
                espn_tid = str(row.get("espn_team_id") or "")
                tid = mapping.get(espn_tid) or row.get("team_id")
                if not tid:
                    continue
                by_team.setdefault(tid, []).append(row)
            return mapping, by_team

        for espn_id, tid in list(mapping.items())[:40]:
            try:
                items = self._fetch_team_injuries(team_crawler, espn_code, espn_id, tid)
                if items:
                    by_team[tid] = items
            except Exception as e:
                logger.debug("team injuries %s/%s failed: %s", espn_code, espn_id, e)
            time.sleep(0.12)
        return mapping, by_team

    def _fetch_league_injuries(self, team_crawler, espn_code: str) -> List[dict]:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}/injuries"
        try:
            r = team_crawler._espn_get(url)
            if r.status_code != 200:
                return []
            data = r.json() or {}
        except Exception:
            return []
        return self._parse_injuries_payload(data)

    def _fetch_team_injuries(self, team_crawler, espn_code: str, espn_team_id: str, team_id: str) -> List[dict]:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}/teams/{espn_team_id}/injuries"
        r = team_crawler._espn_get(url)
        if r.status_code != 200:
            return []
        rows = self._parse_injuries_payload(r.json() or {})
        for row in rows:
            row["team_id"] = team_id
            row["espn_team_id"] = espn_team_id
        return rows

    def _parse_injuries_payload(self, data: dict) -> List[dict]:
        rows = []
        # 常见结构：{"items":[...]} 或 {"athletes":[...]} 或嵌套 teams
        candidates = []
        if isinstance(data.get("items"), list):
            candidates.extend(data["items"])
        if isinstance(data.get("athletes"), list):
            candidates.extend(data["athletes"])
        for team_block in data.get("teams") or []:
            if isinstance(team_block, dict):
                candidates.extend(team_block.get("injuries") or team_block.get("athletes") or [])
        for inj in data.get("injuries") or []:
            if isinstance(inj, dict):
                candidates.append(inj)

        for item in candidates:
            if not isinstance(item, dict):
                continue
            athlete = item.get("athlete") or item.get("player") or {}
            name = (
                athlete.get("displayName")
                or athlete.get("fullName")
                or item.get("displayName")
                or item.get("name")
                or ""
            ).strip()
            if not name:
                continue
            status = (
                (item.get("status") or {}).get("type")
                if isinstance(item.get("status"), dict)
                else item.get("status")
            ) or item.get("type") or "Out"
            detail = item.get("longComment") or item.get("shortComment") or item.get("description") or ""
            team = item.get("team") or {}
            espn_team_id = str(team.get("id") or item.get("teamId") or "")
            rows.append({
                "player_name": name,
                "status": str(status),
                "detail": str(detail)[:200],
                "espn_team_id": espn_team_id,
                "team_id": None,
            })
        return rows

    def _write_match_alerts(self, db, injuries_by_team: Dict[str, List[dict]]) -> int:
        from db.models import Match, RiskAlert, Team

        if not injuries_by_team:
            return 0
        today = date.today()
        until = today + timedelta(days=14)
        matches = (
            db.query(Match)
            .filter(
                Match.status.in_(["upcoming", "live"]),
                Match.match_date >= today,
                Match.match_date <= until,
            )
            .all()
        )
        upserted = 0
        for m in matches:
            home_inj = injuries_by_team.get(m.home_team_id) or []
            away_inj = injuries_by_team.get(m.away_team_id) or []
            if not home_inj and not away_inj:
                continue
            home = db.query(Team).filter(Team.id == m.home_team_id).first()
            away = db.query(Team).filter(Team.id == m.away_team_id).first()
            match_name = (
                f"{getattr(home, 'name', m.home_team_id)} vs "
                f"{getattr(away, 'name', m.away_team_id)}"
            )
            home_txt = "、".join(f"{x['player_name']}({x['status']})" for x in home_inj[:8]) or "无"
            away_txt = "、".join(f"{x['player_name']}({x['status']})" for x in away_inj[:8]) or "无"
            description = f"伤停提示：主队 {home_txt}；客队 {away_txt}"
            level = "high" if (len(home_inj) + len(away_inj)) >= 3 else "mid"
            existing = (
                db.query(RiskAlert)
                .filter(
                    RiskAlert.match_id == m.id,
                    RiskAlert.type == "injury",
                    RiskAlert.is_processed == False,  # noqa: E712
                )
                .first()
            )
            if existing:
                existing.description = description
                existing.level = level
                existing.match_name = match_name
                existing.recommended_action = "临场核对首发与伤停名单，下调缺阵核心相关进攻预期。"
            else:
                db.add(RiskAlert(
                    match_id=m.id,
                    match_name=match_name,
                    type="injury",
                    level=level,
                    description=description,
                    recommended_action="临场核对首发与伤停名单，下调缺阵核心相关进攻预期。",
                    is_processed=False,
                ))
            upserted += 1
        return upserted


injury_crawler_service = InjuryCrawlerService()
