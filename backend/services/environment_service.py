# -*- coding: utf-8 -*-
"""赛事环境字段补全：天气 / 气温 / 草坪。

数据源：Open-Meteo（免费、无需 Key）
- 历史：archive-api.open-meteo.com
- 预报：api.open-meteo.com

按球场名 / 主队国家 / 联赛默认城市推断经纬度，再取开球时刻附近气象，
并据此推导草坪状况。不写随机 mock，避免污染训练与修正。
"""
from __future__ import annotations

import logging
import re
from datetime import date, time, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
import yaml
from sqlalchemy import and_, case, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 联赛 → 默认城市坐标
LEAGUE_COORDS: Dict[str, Tuple[float, float, str]] = {
    "EPL": (51.5074, -0.1278, "London"),
    "LALIGA": (40.4168, -3.7038, "Madrid"),
    "BUNDES": (52.5200, 13.4050, "Berlin"),
    "SERIEA": (41.9028, 12.4964, "Rome"),
    "LIGUE1": (48.8566, 2.3522, "Paris"),
    "UCL": (48.8566, 2.3522, "Paris"),
    "UEL": (48.8566, 2.3522, "Paris"),
    "WC": (25.2048, 55.2708, "Dubai"),
    "MLS": (40.7128, -74.0060, "New York"),
    "ERE": (52.3676, 4.9041, "Amsterdam"),
    "SPL": (55.9533, -3.1883, "Edinburgh"),
}

COUNTRY_COORDS: Dict[str, Tuple[float, float, str]] = {
    "england": (51.5074, -0.1278, "London"),
    "英国": (51.5074, -0.1278, "London"),
    "scotland": (55.9533, -3.1883, "Edinburgh"),
    "spain": (40.4168, -3.7038, "Madrid"),
    "西班牙": (40.4168, -3.7038, "Madrid"),
    "germany": (52.5200, 13.4050, "Berlin"),
    "德国": (52.5200, 13.4050, "Berlin"),
    "italy": (41.9028, 12.4964, "Rome"),
    "意大利": (41.9028, 12.4964, "Rome"),
    "france": (48.8566, 2.3522, "Paris"),
    "法国": (48.8566, 2.3522, "Paris"),
    "netherlands": (52.3676, 4.9041, "Amsterdam"),
    "portugal": (38.7223, -9.1393, "Lisbon"),
    "belgium": (50.8503, 4.3517, "Brussels"),
    "turkey": (41.0082, 28.9784, "Istanbul"),
    "brazil": (-23.5505, -46.6333, "Sao Paulo"),
    "argentina": (-34.6037, -58.3816, "Buenos Aires"),
    "usa": (40.7128, -74.0060, "New York"),
    "united states": (40.7128, -74.0060, "New York"),
    "mexico": (19.4326, -99.1332, "Mexico City"),
    "japan": (35.6762, 139.6503, "Tokyo"),
    "korea": (37.5665, 126.9780, "Seoul"),
    "south korea": (37.5665, 126.9780, "Seoul"),
    "china": (31.2304, 121.4737, "Shanghai"),
    "中国": (31.2304, 121.4737, "Shanghai"),
    "australia": (-33.8688, 151.2093, "Sydney"),
    "saudi arabia": (24.7136, 46.6753, "Riyadh"),
    "qatar": (25.2854, 51.5310, "Doha"),
    "uae": (25.2048, 55.2708, "Dubai"),
}

VENUE_COORDS: Dict[str, Tuple[float, float, str]] = {
    "anfield": (53.4308, -2.9608, "Liverpool"),
    "安菲尔德": (53.4308, -2.9608, "Liverpool"),
    "old trafford": (53.4631, -2.2913, "Manchester"),
    "老特拉福德": (53.4631, -2.2913, "Manchester"),
    "etihad": (53.4831, -2.2004, "Manchester"),
    "伊蒂哈德": (53.4831, -2.2004, "Manchester"),
    "emirates": (51.5550, -0.1084, "London"),
    "酋长": (51.5550, -0.1084, "London"),
    "stamford": (51.4816, -0.1910, "London"),
    "斯坦福桥": (51.4816, -0.1910, "London"),
    "tottenham": (51.6042, -0.0665, "London"),
    "热刺": (51.6042, -0.0665, "London"),
    "wembley": (51.5560, -0.2795, "London"),
    "bernabeu": (40.4530, -3.6883, "Madrid"),
    "伯纳乌": (40.4530, -3.6883, "Madrid"),
    "camp nou": (41.3809, 2.1228, "Barcelona"),
    "诺坎普": (41.3809, 2.1228, "Barcelona"),
    "allianz arena": (48.2188, 11.6247, "Munich"),
    "安联": (48.2188, 11.6247, "Munich"),
    "signal iduna": (51.4926, 7.4519, "Dortmund"),
    "san siro": (45.4781, 9.1240, "Milan"),
    "圣西罗": (45.4781, 9.1240, "Milan"),
    "parc des princes": (48.8414, 2.2530, "Paris"),
    "london": (51.5074, -0.1278, "London"),
    "伦敦": (51.5074, -0.1278, "London"),
    "manchester": (53.4808, -2.2426, "Manchester"),
    "liverpool": (53.4084, -2.9916, "Liverpool"),
    "madrid": (40.4168, -3.7038, "Madrid"),
    "barcelona": (41.3874, 2.1686, "Barcelona"),
    "munich": (48.1351, 11.5820, "Munich"),
    "milan": (45.4642, 9.1900, "Milan"),
    "rome": (41.9028, 12.4964, "Rome"),
    "paris": (48.8566, 2.3522, "Paris"),
}

WMO_WEATHER = {
    0: "晴", 1: "晴", 2: "多云", 3: "阴",
    45: "阴", 48: "阴",
    51: "小雨", 53: "小雨", 55: "小雨", 56: "小雨", 57: "小雨",
    61: "小雨", 63: "小雨", 65: "大雨", 66: "小雨", 67: "大雨",
    71: "雪", 73: "雪", 75: "雪", 77: "雪",
    80: "小雨", 81: "小雨", 82: "大雨",
    85: "雪", 86: "雪",
    95: "大雨", 96: "大雨", 99: "大雨",
}


def _load_env_config() -> dict:
    cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return raw.get("environment") or {}
    except Exception:
        return {}


class EnvironmentService:
    """补全并应用赛事环境字段。"""

    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "traesolo-env/1.0"})
        self._geo_cache: Dict[str, Tuple[float, float, str]] = {}

    def resolve_coords(
        self,
        *,
        venue: str = None,
        home_ground: str = None,
        country: str = None,
        league_id: str = None,
    ) -> Optional[Tuple[float, float, str]]:
        for text in (venue, home_ground):
            if not text:
                continue
            key = text.strip().lower()
            if key in self._geo_cache:
                return self._geo_cache[key]
            for name, coords in VENUE_COORDS.items():
                if name in key or key in name:
                    self._geo_cache[key] = coords
                    return coords

        if country:
            ck = country.strip().lower()
            if ck in COUNTRY_COORDS:
                return COUNTRY_COORDS[ck]
            for name, coords in COUNTRY_COORDS.items():
                if name in ck or ck in name:
                    return coords

        if league_id and league_id in LEAGUE_COORDS:
            return LEAGUE_COORDS[league_id]
        return None

    def fetch_weather_at(
        self,
        lat: float,
        lon: float,
        match_date: date,
        match_time: Optional[time] = None,
    ) -> Optional[Dict]:
        if not match_date:
            return None
        hour = match_time.hour if match_time else 15
        today = date.today()
        # 预报窗口约 16 天；更远的赛程暂不硬拉（避免 400）
        if match_date > today + timedelta(days=15):
            return None
        use_archive = match_date < today - timedelta(days=1)
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,precipitation,weathercode",
            "timezone": "auto",
            "start_date": match_date.isoformat(),
            "end_date": match_date.isoformat(),
        }
        url = self.ARCHIVE_URL if use_archive else self.FORECAST_URL
        try:
            r = self.session.get(url, params=params, timeout=20)
            r.raise_for_status()
            hourly = (r.json() or {}).get("hourly") or {}
            times = hourly.get("time") or []
            temps = hourly.get("temperature_2m") or []
            precips = hourly.get("precipitation") or []
            codes = hourly.get("weathercode") or []
            if not times:
                return None

            idx = 0
            for i, t in enumerate(times):
                if t.startswith(match_date.isoformat()) and int(t[11:13]) == hour:
                    idx = i
                    break
                if t.startswith(match_date.isoformat()):
                    idx = i
            temp = temps[idx] if idx < len(temps) else None
            precip = float(precips[idx] or 0) if idx < len(precips) else 0.0
            code = int(codes[idx]) if idx < len(codes) and codes[idx] is not None else 0
            weather = WMO_WEATHER.get(code, "多云")
            pitch = self._pitch_from_precip(precip, weather)
            return {
                "weather": weather,
                "temperature": f"{round(float(temp))}°C" if temp is not None else "",
                "pitch_condition": pitch,
                "precip_mm": round(precip, 2),
                "weather_code": code,
                "source": "open-meteo",
            }
        except Exception as e:
            logger.warning("Open-Meteo fetch failed (%.2f,%.2f %s): %s", lat, lon, match_date, e)
            return None

    @staticmethod
    def _pitch_from_precip(precip_mm: float, weather: str) -> str:
        if weather == "雪" or precip_mm >= 4.0:
            return "较差"
        if weather == "大雨" or precip_mm >= 1.5:
            return "一般"
        if weather == "小雨" or precip_mm >= 0.3:
            return "一般"
        if weather == "晴":
            return "优秀"
        return "良好"

    def enrich_match_dict(self, match: dict, home_team=None) -> dict:
        """就地补全 match dict（已有非空值不覆盖）。"""
        if match.get("weather") and match.get("pitch_condition"):
            return match
        venue = match.get("venue") or (getattr(home_team, "home_ground", None) if home_team else None)
        country = getattr(home_team, "country", None) if home_team else None
        home_ground = getattr(home_team, "home_ground", None) if home_team else None
        coords = self.resolve_coords(
            venue=venue,
            home_ground=home_ground,
            country=country,
            league_id=match.get("league_id"),
        )
        if not coords:
            return match
        lat, lon, city = coords
        if not match.get("venue") and (home_ground or city):
            match["venue"] = home_ground or city
        env = self.fetch_weather_at(lat, lon, match.get("match_date"), match.get("match_time"))
        if not env:
            return match
        if not match.get("weather"):
            match["weather"] = env["weather"]
        if not match.get("temperature"):
            match["temperature"] = env["temperature"]
        if not match.get("pitch_condition"):
            match["pitch_condition"] = env["pitch_condition"]
        return match

    def enrich_orm_match(self, db: Session, match, force: bool = False) -> bool:
        """补全 ORM Match；返回是否有写入。"""
        from db.models import Team

        if not force and match.weather and match.pitch_condition:
            return False
        home = db.query(Team).filter(Team.id == match.home_team_id).first()
        coords = self.resolve_coords(
            venue=match.venue,
            home_ground=getattr(home, "home_ground", None) if home else None,
            country=getattr(home, "country", None) if home else None,
            league_id=match.league_id,
        )
        if not coords:
            return False
        lat, lon, city = coords
        changed = False
        if not match.venue and (getattr(home, "home_ground", None) or city):
            match.venue = (home.home_ground if home and home.home_ground else city)
            changed = True
        env = self.fetch_weather_at(lat, lon, match.match_date, match.match_time)
        if not env:
            return changed  # 可能只写了 venue
        weather_written = False
        if force or not match.weather:
            match.weather = env["weather"]
            changed = True
            weather_written = True
        if force or not match.temperature:
            match.temperature = env["temperature"]
            changed = True
            weather_written = True
        if force or not match.pitch_condition:
            match.pitch_condition = env["pitch_condition"]
            changed = True
            weather_written = True
        # 标记：调用方可用 getattr 判断；默认仍返回是否有任意写入
        match._env_weather_written = weather_written  # type: ignore[attr-defined]
        return changed

    def backfill(
        self,
        db: Session,
        *,
        limit: int = 200,
        only_missing: bool = True,
        upcoming_only: bool = False,
        finished_only: bool = False,
        league_id: str = None,
        create_risk_alerts: bool = True,
        prefer_priority: bool = True,
    ) -> Dict:
        """批量补全库内赛事环境字段。

        默认优先：重点联赛、完赛有球场名、再按日期。完赛配额大于未赛，避免覆盖率长期为 0。
        """
        from db.models import Match
        from datetime import date as _date, timedelta as _td

        try:
            from services.real_team_crawler import get_priority_leagues
            priority = set(get_priority_leagues()) | {"WC"}
        except Exception:
            priority = {"EPL", "LALIGA", "BUNDES", "SERIEA", "LIGUE1", "UCL", "UEL", "WC"}

        today = _date.today()
        q = db.query(Match).filter(
            Match.match_date >= today - _td(days=365 * 3),
            Match.match_date <= today + _td(days=15),
        )
        if league_id:
            q = q.filter(Match.league_id == league_id)
        if upcoming_only:
            q = q.filter(Match.status.in_(["upcoming", "live"]))
        elif finished_only:
            q = q.filter(Match.status == "finished")
        if only_missing:
            q = q.filter(
                or_(
                    Match.weather.is_(None), Match.weather == "",
                    Match.pitch_condition.is_(None), Match.pitch_condition == "",
                )
            )

        cap = max(1, min(int(limit), 2000))
        finished_share = 0.65
        try:
            from db.database import config as app_config
            finished_share = float((app_config.get("crawler") or {}).get("env_finished_share") or 0.65)
        except Exception:
            pass
        finished_share = min(0.9, max(0.3, finished_share))

        venue_rank = case(
            (and_(Match.venue.isnot(None), Match.venue != ""), 1),
            else_=0,
        )

        def _rank_pri(m):
            is_pri = 1 if (getattr(m, "league_id", None) or "") in priority else 0
            has_venue = 1 if str(getattr(m, "venue", None) or "").strip() else 0
            d = m.match_date or today
            ord_v = d.toordinal() if hasattr(d, "toordinal") else 0
            return (is_pri if prefer_priority else 0, has_venue, ord_v)

        if prefer_priority and not league_id and not upcoming_only and not finished_only:
            fin_cap = max(1, int(round(cap * finished_share)))
            up_cap = max(1, cap - fin_cap)
            fetch_up = min(up_cap * 4, 2000)
            fetch_fin = min(fin_cap * 4, 2000)
            up_rows = (
                q.filter(Match.status.in_(["upcoming", "live"]))
                .order_by(Match.match_date.asc())
                .limit(fetch_up)
                .all()
            )
            fin_rows = (
                q.filter(Match.status == "finished")
                .order_by(venue_rank.desc(), Match.match_date.desc())
                .limit(fetch_fin)
                .all()
            )
            up_rows.sort(key=_rank_pri, reverse=True)
            fin_rows.sort(key=_rank_pri, reverse=True)
            matches = up_rows[:up_cap] + fin_rows[:fin_cap]
        else:
            fetch_n = min(max(cap * 4, cap), 3000) if prefer_priority and not league_id else cap
            order = (venue_rank.desc(), Match.match_date.desc()) if finished_only else (Match.match_date.desc(),)
            candidates = q.order_by(*order).limit(fetch_n).all()
            if prefer_priority and not league_id:
                candidates.sort(key=_rank_pri, reverse=True)
            matches = candidates[:cap]

        updated = 0
        alerts = 0
        venue_only = 0
        skipped_no_coords = 0
        for m in matches:
            try:
                before_weather = bool(m.weather)
                changed = self.enrich_orm_match(db, m, force=not only_missing)
                if changed:
                    db.commit()
                    if getattr(m, "_env_weather_written", False) or (m.weather and not before_weather):
                        updated += 1
                        if create_risk_alerts:
                            alerts += self.ensure_risk_alerts(db, m)
                    else:
                        venue_only += 1
                else:
                    skipped_no_coords += 1
            except Exception as e:
                db.rollback()
                logger.debug("enrich match %s failed: %s", getattr(m, "id", None), e)

        # 补全后覆盖快照（便于看板观测）
        coverage = {}
        try:
            finished_n = db.query(Match).filter(Match.status == "finished").count()
            env_finished = db.query(Match).filter(
                Match.status == "finished",
                Match.weather.isnot(None), Match.weather != "",
                Match.pitch_condition.isnot(None), Match.pitch_condition != "",
            ).count()
            upcoming_n = db.query(Match).filter(Match.status.in_(["upcoming", "live"])).count()
            env_upcoming = db.query(Match).filter(
                Match.status.in_(["upcoming", "live"]),
                Match.weather.isnot(None), Match.weather != "",
                Match.pitch_condition.isnot(None), Match.pitch_condition != "",
            ).count()
            coverage = {
                "finished_matches": finished_n,
                "env_finished": env_finished,
                "env_finished_pct": round(100.0 * env_finished / finished_n, 1) if finished_n else 0,
                "upcoming_matches": upcoming_n,
                "env_upcoming": env_upcoming,
                "env_upcoming_pct": round(100.0 * env_upcoming / upcoming_n, 1) if upcoming_n else 0,
            }
        except Exception:
            coverage = {}

        return {
            "scanned": len(matches),
            "updated": updated,
            "venue_only": venue_only,
            "skipped_no_coords": skipped_no_coords,
            "risk_alerts": alerts,
            "coverage": coverage,
        }

    def ensure_risk_alerts(self, db: Session, match) -> int:
        """对恶劣天气 / 较差草坪写入风控预警（同场同类型不重复）。"""
        from db.models import RiskAlert, Team

        created = 0
        weather = (match.weather or "").strip()
        pitch = (match.pitch_condition or "").strip()
        home = db.query(Team).filter(Team.id == match.home_team_id).first()
        away = db.query(Team).filter(Team.id == match.away_team_id).first()
        match_name = (
            f"{getattr(home, 'name', match.home_team_id)} vs "
            f"{getattr(away, 'name', match.away_team_id)}"
        )

        def _exists(alert_type: str) -> bool:
            return db.query(RiskAlert).filter(
                RiskAlert.match_id == match.id,
                RiskAlert.type == alert_type,
            ).first() is not None

        if weather in ("大雨", "雪", "小雨") and not _exists("weather"):
            level = "high" if weather in ("大雨", "雪") else "mid"
            db.add(RiskAlert(
                match_id=match.id,
                match_name=match_name,
                type="weather",
                level=level,
                description=(
                    f"比赛天气为「{weather}」"
                    f"{('，气温 ' + match.temperature) if match.temperature else ''}，"
                    f"可能压制进球与节奏。"
                ),
                recommended_action="下调总进球预期，关注低比分与防守型打法；临场核对阵容。",
            ))
            created += 1

        if pitch in ("一般", "较差") and not _exists("pitch"):
            level = "high" if pitch == "较差" else "mid"
            db.add(RiskAlert(
                match_id=match.id,
                match_name=match_name,
                type="pitch",
                level=level,
                description=f"草坪状况「{pitch}」，传球与控球效率可能下降。",
                recommended_action="降低传控型球队进攻权重，警惕意外低比分。",
            ))
            created += 1

        if created:
            db.commit()
        return created

    @staticmethod
    def compute_factors(
        weather: str = None,
        pitch_condition: str = None,
        temperature: str = None,
        config: dict = None,
    ) -> Dict:
        """返回 λ 修正系数与风控提示。"""
        cfg = config if config is not None else _load_env_config()
        weather_map = cfg.get("weather_lambda_factor") or {
            "晴": 1.00, "多云": 1.00, "阴": 0.98, "小雨": 0.94, "大雨": 0.88, "雪": 0.85,
        }
        pitch_map = cfg.get("pitch_lambda_factor") or {
            "优秀": 1.02, "良好": 1.00, "一般": 0.96, "较差": 0.90,
        }
        extreme = cfg.get("extreme_temp_c") or [0, 35]

        w = (weather or "").strip()
        p = (pitch_condition or "").strip()
        # 兼容旧 mock「晴天/多云/阴天」
        aliases = {
            "晴天": "晴", "阴天": "阴", "多云转晴": "多云",
            "小雨": "小雨", "大雨": "大雨", "雨": "小雨", "暴雨": "大雨",
        }
        w = aliases.get(w, w)
        w_factor = float(weather_map.get(w, 1.0))
        p_factor = float(pitch_map.get(p, 1.0))
        combined = max(0.80, min(1.08, w_factor * p_factor))

        temp_c = None
        if temperature:
            m = re.search(r"-?\d+(?:\.\d+)?", str(temperature))
            if m:
                temp_c = float(m.group(0))

        temp_penalty = False
        if temp_c is not None:
            lo, hi = float(extreme[0]), float(extreme[1])
            if temp_c < lo or temp_c > hi:
                combined *= 0.97
                temp_penalty = True

        risk_boost = bool(
            w in ("大雨", "雪", "小雨") or p in ("一般", "较差") or temp_penalty
        )
        return {
            "weather": w or None,
            "temperature": temperature or None,
            "pitch_condition": p or None,
            "weather_factor": round(w_factor, 4),
            "pitch_factor": round(p_factor, 4),
            "lambda_factor": round(combined, 4),
            "temp_c": temp_c,
            "temp_penalty": temp_penalty,
            "risk_boost": risk_boost,
            "applied": abs(combined - 1.0) > 1e-6 or bool(w or p),
        }


environment_service = EnvironmentService()
