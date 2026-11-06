import logging
import json
import re
import threading
import time as time_module
from datetime import date, datetime, time, timedelta
from typing import List, Dict, Optional, Tuple

from db.database import SessionLocal
from db.models import League, Team, Match, Player, Standing, TopScorer, CrawlLog
from services.crud_service import (
    MatchService, LeagueService, TeamService, CrawlLogService, PlayerService,
    MatchPlayerStatService, MatchTeamStatService, StandingService, ScorerService,
)
logger = logging.getLogger(__name__)


def _is_media(value) -> bool:
    if not value:
        return False
    text = str(value)
    return text.startswith(("http://", "https://", "/static/"))


def _crawler_cfg() -> dict:
    try:
        from db.database import config as app_config
        return dict((app_config or {}).get("crawler") or {})
    except Exception:
        return {}


from services.crawler.base import MatchCrawler, PlayerCrawler

class CrawlerService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._crawlers = {}
            cls._instance._default_crawler = None
            try:
                from .real_crawler import RealMatchCrawler
                cls._instance._real_crawler = RealMatchCrawler()
                cls._instance._default_crawler = cls._instance._real_crawler
            except Exception as e:
                logger.warning(f"Failed to load RealMatchCrawler: {e}")
                cls._instance._real_crawler = None
            cls._instance._player_crawlers = {}
            cls._instance._default_player_crawler = None
            try:
                from .real_player_crawler import RealPlayerCrawler
                cls._instance._real_player_crawler = RealPlayerCrawler()
                cls._instance._default_player_crawler = cls._instance._real_player_crawler
                cls._instance._player_crawlers['WC'] = cls._instance._real_player_crawler
            except Exception as e:
                logger.warning(f"Failed to load RealPlayerCrawler: {e}")
                cls._instance._real_player_crawler = None
            try:
                from .fifa_world_cup_crawler import FifaWorldCupCrawler
                cls._instance._fifa_crawler = FifaWorldCupCrawler()
                cls._instance._crawlers['WC'] = cls._instance._fifa_crawler
            except Exception as e:
                logger.warning(f"Failed to load FifaWorldCupCrawler: {e}")
                cls._instance._fifa_crawler = None
            try:
                from .live_500_crawler import Live500MatchCrawler
                cls._instance._live_500_crawler = Live500MatchCrawler()
            except Exception as e:
                logger.warning(f"Failed to load Live500MatchCrawler: {e}")
                cls._instance._live_500_crawler = None
            try:
                from .live_jingcai_crawler import LiveJingcaiCrawler
                cls._instance._live_jingcai_crawler = LiveJingcaiCrawler()
            except Exception as e:
                logger.warning(f"Failed to load LiveJingcaiCrawler: {e}")
                cls._instance._live_jingcai_crawler = None
            try:
                from .league_crawler import LeagueCrawler
                cls._instance._league_crawler = LeagueCrawler()
            except Exception as e:
                logger.warning(f"Failed to load LeagueCrawler: {e}")
                cls._instance._league_crawler = None
            try:
                from .real_team_crawler import RealTeamCrawler
                cls._instance._team_crawler = RealTeamCrawler()
            except Exception as e:
                logger.warning(f"Failed to load RealTeamCrawler: {e}")
                cls._instance._team_crawler = None
            cls._instance._p0_lock = threading.Lock()
            cls._instance._p0_status = cls._empty_p0_status()
        return cls._instance

    @staticmethod
    def _empty_p0_status() -> Dict:
        return {
            "running": False,
            "status": "idle",
            "phase": None,
            "message": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "progress": {},
            "result": None,
            "job_id": None,
            "job_mode": None,
        }

    def use_real_player_crawler(self, enable: bool = True):
        """兼容旧调用：仅允许真实球员爬虫，忽略 disable。"""
        if self._real_player_crawler:
            self._default_player_crawler = self._real_player_crawler
            logger.info("Real player crawler active (mock removed)")
        elif not enable:
            logger.warning("Mock player crawler removed; cannot disable real crawler")

    def register_crawler(self, league_id: str, crawler: MatchCrawler):
        self._crawlers[league_id] = crawler

    def use_real_crawler(self, enable: bool = True):
        """兼容旧调用：仅允许真实赛程爬虫，忽略 disable。"""
        if self._real_crawler:
            self._default_crawler = self._real_crawler
            logger.info("Real match crawler active (mock removed)")
        elif not enable:
            logger.warning("Mock match crawler removed; cannot disable real crawler")

    def register_player_crawler(self, league_id: str, crawler: PlayerCrawler):
        self._player_crawlers[league_id] = crawler

    def crawl_league(self, league_id: str, days_ahead: int = 7, crawl_type: str = 'manual') -> Dict:
        """采集单联赛赛程：有 500 URL 主用 500，空或仅 ESPN 映射时兜底 ESPN。"""
        start_time = datetime.now()
        logger.info(f"Starting crawl for league: {league_id} (type: {crawl_type})")

        db = SessionLocal()
        try:
            league = LeagueService.get_by_id(db, league_id)
            league_name = league.name if league else league_id
            source_url = league.source_url if league else None
        finally:
            db.close()

        try:
            raw_matches = []
            if getattr(self, '_team_crawler', None):
                try:
                    # crawl_fixtures 内部：500 主 → ESPN 软兜底
                    raw_matches = self._team_crawler.crawl_fixtures(
                        league_id, source_url=source_url, include_history=False
                    )
                except Exception as e:
                    logger.warning("Fixture crawl failed for %s: %s", league_id, e)
            if not raw_matches:
                logger.warning(
                    "No real fixtures for %s; skipping (mock fallback removed)", league_id
                )
            saved_count, updated_count = self._save_matches(raw_matches)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            logger.info(
                f"Crawl completed for league {league_id}: {len(raw_matches)} found, "
                f"{saved_count} saved, {updated_count} updated"
            )
            
            self._save_crawl_log(
                crawl_type=crawl_type,
                league_id=league_id,
                league_name=league_name,
                found_count=len(raw_matches),
                saved_count=saved_count,
                updated_count=updated_count,
                status='success',
                crawled_data=json.dumps(raw_matches, default=str, ensure_ascii=False),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )
            
            return {
                'league_id': league_id,
                'found_count': len(raw_matches),
                'saved_count': saved_count,
                'updated_count': updated_count,
                'status': 'success',
                'duration_ms': duration_ms
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            logger.error(f"Crawl failed for league {league_id}: {str(e)}")
            
            self._save_crawl_log(
                crawl_type=crawl_type,
                league_id=league_id,
                league_name=league_name,
                found_count=0,
                saved_count=0,
                status='failed',
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )
            
            return {
                'league_id': league_id,
                'found_count': 0,
                'saved_count': 0,
                'status': 'failed',
                'error': str(e),
                'duration_ms': duration_ms
            }

    def crawl_all_leagues(self, days_ahead: int = 7, crawl_type: str = 'scheduled') -> List[Dict]:
        """采集重点联赛及有球队数据的规范联赛赛程。"""
        start_time = datetime.now()
        logger.info(f"Starting crawl for canonical leagues (type: {crawl_type})")

        from services.real_team_crawler import get_priority_leagues, ESPN_LEAGUE_MAP, CANONICAL_FIVE00_URL
        db = SessionLocal()
        try:
            target_ids = []
            for lid in get_priority_leagues():
                if LeagueService.get_by_id(db, lid) and lid not in target_ids:
                    target_ids.append(lid)
            for lid in list(ESPN_LEAGUE_MAP.keys()) + list(CANONICAL_FIVE00_URL.keys()):
                if lid not in target_ids and LeagueService.get_by_id(db, lid):
                    target_ids.append(lid)
            for lg in LeagueService.get_active(db):
                if lg.id not in target_ids and lg.source_url:
                    team_n = db.query(Team).filter(Team.league_id == lg.id).count()
                    if team_n > 0:
                        target_ids.append(lg.id)
        finally:
            db.close()

        results = []
        try:
            for lid in target_ids:
                results.append(self.crawl_league(lid, days_ahead, crawl_type))

            if self._real_crawler:
                skip_jingcai = False
                try:
                    from services.scheduler_service import scheduler
                    skip_jingcai = scheduler.is_task_enabled("jingcai_odds_crawl")
                except Exception:
                    skip_jingcai = False
                if skip_jingcai:
                    results.append({
                        'league_id': 'all',
                        'found_count': 0,
                        'saved_count': 0,
                        'updated_count': 0,
                        'status': 'skipped',
                        'reason': 'jingcai_odds_crawl_enabled',
                    })
                else:
                    try:
                        jingcai = self._real_crawler.crawl('all', days_ahead)
                        saved, updated = self._save_matches(jingcai)
                        results.append({
                            'league_id': 'all',
                            'found_count': len(jingcai),
                            'saved_count': saved,
                            'updated_count': updated,
                            'status': 'success',
                        })
                    except Exception as e:
                        logger.warning("Jingcai crawl failed: %s", e)

            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            total_found = sum(r.get('found_count', 0) for r in results)
            total_saved = sum(r.get('saved_count', 0) for r in results)

            self._save_crawl_log(
                crawl_type=crawl_type,
                league_id=None,
                league_name='规范联赛赛程',
                found_count=total_found,
                saved_count=total_saved,
                status='success' if all(r.get('status') == 'success' for r in results) else 'partial',
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )
            return results
        except Exception as e:
            logger.error("crawl_all_leagues failed: %s", e)
            return results or [{'status': 'failed', 'error': str(e)}]

    def _save_matches(self, raw_matches: List[Dict]) -> Tuple[int, int]:
        from db.models import League, Match
        db = SessionLocal()
        saved_count = 0
        updated_count = 0
        processed = 0
        try:
            for match_data in raw_matches:
                processed += 1
                # 定期提交/释放读事务，避免大批量 skip 时长时间占着 matches 元数据锁
                # （否则启动/训练进程里的 ALTER 会把全库堵住）
                if processed % 80 == 0:
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()

                # 竞彩：已有 fixture_id 的场次优先只更新赔率/让球（避免队名映射失败丢赔率）
                fixture_id = str(match_data.get('fixture_id') or '').strip()
                if fixture_id:
                    by_fid = db.query(Match).filter(Match.fixture_id == fixture_id).first()
                    if by_fid:
                        odds_payload = {k: match_data.get(k) for k in (
                            'handicap', 'handicap_line', 'process_id',
                            'odds_nspf_win', 'odds_nspf_draw', 'odds_nspf_lose',
                            'odds_spf_win', 'odds_spf_draw', 'odds_spf_lose',
                            'odds_bf_json',
                            'is_single', 'buy_end_time', 'round_name',
                            'status', 'home_goals', 'away_goals', 'result',
                            'match_date', 'match_time',
                            'half_score', 'match_no', 'source',
                        )}
                        try:
                            from services.odds_snapshot_service import maybe_snapshot_odds
                            maybe_snapshot_odds(db, by_fid, odds_payload, source="500_trade")
                        except Exception as e:
                            logger.debug("odds snapshot failed for %s: %s", by_fid.id, e)
                        changed = False
                        for key, val in odds_payload.items():
                            if val is None:
                                continue
                            if getattr(by_fid, key, None) != val:
                                setattr(by_fid, key, val)
                                changed = True
                        if changed:
                            db.commit()
                            updated_count += 1
                        continue

                league_id = match_data.get('league_id')
                if not league_id:
                    logger.debug("Skip match %s: missing league_id", match_data.get('id'))
                    continue

                if not self._ensure_jingcai_entities(db, match_data):
                    logger.debug(
                        "Skip match %s: cannot ensure league/teams league=%s",
                        match_data.get('id'), league_id,
                    )
                    continue
                league_id = match_data.get('league_id')

                from services.match_dedup import (
                    canonical_match_id,
                    find_existing_match,
                    resolve_ingest_teams,
                )
                resolved = resolve_ingest_teams(
                    db,
                    league_id,
                    match_data.get('home_team_id'),
                    match_data.get('away_team_id'),
                    match_data.get('home_team_name'),
                    match_data.get('away_team_name'),
                    self._remap_team_id,
                )
                if not resolved:
                    logger.info(
                        "Skip match %s: unresolved teams %s vs %s",
                        match_data.get('id'),
                        match_data.get('home_team_id'),
                        match_data.get('away_team_id'),
                    )
                    continue
                match_data['home_team_id'], match_data['away_team_id'] = resolved
                match_data['id'] = canonical_match_id(
                    league_id, match_data.get('match_date'), resolved[0], resolved[1]
                )

                match_data_clean = {k: v for k, v in match_data.items() if k in [
                    'id', 'league_id', 'home_team_id', 'away_team_id', 'match_date', 'match_time',
                    'venue', 'status', 'home_goals', 'away_goals', 'result', 'weather',
                    'temperature', 'pitch_condition', 'stage', 'group_name', 'round_name',
                    'fixture_id', 'process_id', 'handicap', 'handicap_line',
                    'odds_nspf_win', 'odds_nspf_draw', 'odds_nspf_lose',
                    'odds_spf_win', 'odds_spf_draw', 'odds_spf_lose',
                    'odds_bf_json',
                    'is_single', 'buy_end_time',
                    'half_score', 'match_no', 'source',
                ]}
                existing = find_existing_match(
                    db,
                    league_id=match_data_clean.get('league_id'),
                    match_date=match_data_clean.get('match_date'),
                    home_team_id=match_data_clean.get('home_team_id'),
                    away_team_id=match_data_clean.get('away_team_id'),
                    fixture_id=match_data_clean.get('fixture_id'),
                    remap_team_fn=self._remap_team_id,
                )
                if existing:
                    changed = False
                    try:
                        from services.odds_snapshot_service import maybe_snapshot_odds
                        maybe_snapshot_odds(db, existing, match_data_clean, source="500_trade")
                    except Exception as e:
                        logger.debug("odds snapshot failed for %s: %s", existing.id, e)
                    for key in [
                        'status', 'home_goals', 'away_goals', 'result', 'match_date', 'match_time',
                        'round_name', 'league_id', 'fixture_id', 'process_id', 'handicap', 'handicap_line',
                        'odds_nspf_win', 'odds_nspf_draw', 'odds_nspf_lose',
                        'odds_spf_win', 'odds_spf_draw', 'odds_spf_lose',
                        'odds_bf_json',
                        'is_single', 'buy_end_time',
                        'half_score', 'match_no', 'source',
                        'venue', 'weather', 'temperature', 'pitch_condition',
                    ]:
                        if key in match_data_clean and match_data_clean[key] is not None:
                            # 环境字段：仅在新值非空时覆盖，避免空串冲掉已补全数据
                            if key in ('venue', 'weather', 'temperature', 'pitch_condition'):
                                new_val = match_data_clean[key]
                                if new_val == '' or new_val is None:
                                    continue
                            if getattr(existing, key, None) != match_data_clean[key]:
                                setattr(existing, key, match_data_clean[key])
                                changed = True
                    if changed:
                        db.commit()
                        updated_count += 1
                    continue

                MatchService.create(db, match_data_clean)
                saved_count += 1
                try:
                    from services.odds_snapshot_service import has_any_odds, normalize_bf_json, odds_tuple_from_obj
                    from db.models import OddsSnapshot
                    bf_text = normalize_bf_json(match_data_clean.get("odds_bf_json"))
                    if has_any_odds(odds_tuple_from_obj(match_data_clean)) or bf_text:
                        db.add(OddsSnapshot(
                            match_id=match_data_clean["id"],
                            fixture_id=match_data_clean.get("fixture_id"),
                            source="500_trade",
                            captured_at=datetime.now(),
                            handicap=match_data_clean.get("handicap"),
                            odds_nspf_win=match_data_clean.get("odds_nspf_win"),
                            odds_nspf_draw=match_data_clean.get("odds_nspf_draw"),
                            odds_nspf_lose=match_data_clean.get("odds_nspf_lose"),
                            odds_spf_win=match_data_clean.get("odds_spf_win"),
                            odds_spf_draw=match_data_clean.get("odds_spf_draw"),
                            odds_spf_lose=match_data_clean.get("odds_spf_lose"),
                            odds_bf_json=bf_text,
                        ))
                        db.commit()
                except Exception as e:
                    logger.debug("initial odds snapshot skipped: %s", e)
            try:
                db.commit()
            except Exception:
                db.rollback()
        finally:
            db.close()
        return saved_count, updated_count

    def _ensure_jingcai_entities(self, db, match_data: Dict) -> bool:
        """确保竞彩入库所需联赛/球队存在；优先映射到本库球队，否则建 T{500id} 壳。"""
        from db.models import League
        from services.real_team_crawler import is_clean_team_id

        league_id = (match_data.get('league_id') or '')[:20]
        if not league_id:
            return False
        if not db.query(League).filter(League.id == league_id).first():
            try:
                LeagueService.create(db, {
                    'id': league_id,
                    'name': (match_data.get('league_name') or league_id)[:100],
                    'icon': '⚽',
                    'category': 'domestic',
                    'level': 2,
                    'is_active': True,
                    'avg_goals': 2.70,
                })
                logger.info("Created league stub %s (%s)", league_id, match_data.get('league_name'))
            except Exception as e:
                db.rollback()
                logger.warning("Create league %s failed: %s", league_id, e)
                if not db.query(League).filter(League.id == league_id).first():
                    return False

        for id_key, name_key in (
            ('home_team_id', 'home_team_name'),
            ('away_team_id', 'away_team_name'),
        ):
            tid = match_data.get(id_key)
            tname = match_data.get(name_key) or tid
            remapped = self._remap_team_id(
                db, league_id, team_id=tid, team_name=tname, allow_global=True,
            )
            if remapped and TeamService.get_by_id(db, remapped):
                match_data[id_key] = remapped
                continue
            if not is_clean_team_id(tid):
                return False
            if TeamService.get_by_id(db, tid):
                continue
            try:
                TeamService.create(db, {
                    'id': str(tid)[:20],
                    'name': str(tname)[:100],
                    'short_name': str(tname)[:20],
                    'league_id': league_id,
                    'elo_rating': 1500,
                })
                logger.info("Created team stub %s - %s (%s)", tid, tname, league_id)
            except Exception as e:
                db.rollback()
                logger.warning("Create team %s failed: %s", tid, e)
                if not TeamService.get_by_id(db, tid):
                    return False
        return True

    def crawl_jingcai_odds(self, days_ahead: int = 7, crawl_type: str = "scheduled") -> Dict:
        """仅爬取 trade.500.com/jczq 胜平负/让球并入库。"""
        start_time = datetime.now()
        if not self._real_crawler:
            return {"status": "failed", "error": "竞彩采集器未加载", "found_count": 0, "saved_count": 0}
        try:
            raw = self._real_crawler._crawl_jczq_trade(days_ahead=days_ahead)
            saved, updated = self._save_matches(raw)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            status = "success"
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="odds",
                league_id=None,
                league_name="竞彩胜平负/让球",
                found_count=len(raw),
                saved_count=saved,
                updated_count=updated,
                status=status,
                crawled_data=json.dumps(
                    {"source": "https://trade.500.com/jczq/", "days_ahead": days_ahead},
                    ensure_ascii=False,
                ),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {
                "status": status,
                "found_count": len(raw),
                "saved_count": saved,
                "updated_count": updated,
                "duration_ms": duration_ms,
                "disclaimer": "仅供分析，不构成投注建议",
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            logger.error("crawl_jingcai_odds failed: %s", e)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="odds",
                league_id=None,
                league_name="竞彩胜平负/让球",
                found_count=0,
                saved_count=0,
                status="failed",
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {
                "status": "failed",
                "error": str(e),
                "found_count": 0,
                "saved_count": 0,
                "duration_ms": duration_ms,
            }

    def crawl_jingcai_bf_odds(self, days_ahead: int = 7, days_back: int = 0, crawl_type: str = "scheduled") -> Dict:
        """爬取 trade.500.com/jczq 比分页投注区 SP 并入库。

        days_back>0 时回补历史日期，用于「竞彩分析」历史比分列表补齐（分析用）。
        """
        start_time = datetime.now()
        is_history = int(days_back or 0) > 0 and int(days_ahead or 0) == 0
        log_name = "竞彩分析历史比分" if is_history else "竞彩比分"
        if not self._real_crawler:
            return {"status": "failed", "error": "竞彩采集器未加载", "found_count": 0, "saved_count": 0}
        try:
            raw = self._real_crawler._crawl_jczq_bf(days_ahead=days_ahead, days_back=days_back)
            saved, updated = self._save_matches(raw)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            status = "success"
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="odds",
                league_id=None,
                league_name=log_name,
                found_count=len(raw),
                saved_count=saved,
                updated_count=updated,
                status=status,
                crawled_data=json.dumps(
                    {
                        "source": "https://trade.500.com/jczq/?playid=271&g=2",
                        "days_ahead": days_ahead,
                        "days_back": days_back,
                    },
                    ensure_ascii=False,
                ),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {
                "status": status,
                "found_count": len(raw),
                "saved_count": saved,
                "updated_count": updated,
                "duration_ms": duration_ms,
                "disclaimer": "仅供分析，不构成投注建议",
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            logger.error("crawl_jingcai_bf_odds failed: %s", e)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="odds",
                league_id=None,
                league_name=log_name,
                found_count=0,
                saved_count=0,
                status="failed",
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {
                "status": "failed",
                "error": str(e),
                "found_count": 0,
                "saved_count": 0,
                "duration_ms": duration_ms,
            }

    def crawl_jingcai_bf_history(self, days_back: int = 30, crawl_type: str = "scheduled") -> Dict:
        """回补「竞彩分析」历史比分列表：trade.500.com/jczq?playid=271 历史日期投注区 SP。

        仅向后回补（days_ahead=0），用于补齐历史比分列表数据（分析用，非投注建议）。
        """
        return self.crawl_jingcai_bf_odds(
            days_ahead=0,
            days_back=days_back,
            crawl_type=crawl_type,
        )

    def crawl_jingcai_scores(
        self,
        days_back: int = 7,
        match_date: date = None,
        crawl_type: str = "scheduled",
    ) -> Dict:
        """从 trade.500.com/jczq?playid=269&g=2&date= 赛果回查回写比分（并覆盖更新赔率字段）。"""
        start_time = datetime.now()
        if not self._real_crawler:
            return {"status": "failed", "error": "竞彩采集器未加载", "found_count": 0, "updated_count": 0}
        try:
            from services.match_dedup import dedup_crawled_matches

            days = max(1, min(int(days_back or 7), 30))
            date_list = []
            if match_date:
                date_list = [match_date]
            else:
                date_list = [date.today() - timedelta(days=i) for i in range(0, days + 1)]

            buckets = []
            for d in date_list:
                buckets.extend(self._real_crawler._crawl_by_date(d.strftime("%Y-%m-%d")))
            raw = dedup_crawled_matches(buckets)
            # 优先按 fixture_id 更新已有场次比分；同时落库赔率变化
            score_updated, score_skipped = self._update_match_score_status(raw)
            saved, updated = self._save_matches(raw)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            status = "success"
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="odds",
                league_id=None,
                league_name="竞彩赛果回写",
                found_count=len(raw),
                saved_count=saved,
                updated_count=max(score_updated, updated),
                status=status,
                crawled_data=json.dumps(
                    {
                        "source": "https://trade.500.com/jczq/?playid=269&g=2",
                        "days_back": days if not match_date else 0,
                        "match_date": match_date.isoformat() if match_date else None,
                        "dates": [d.isoformat() for d in date_list],
                        "score_updated": score_updated,
                        "score_skipped": score_skipped,
                        "saved": saved,
                        "updated": updated,
                    },
                    ensure_ascii=False,
                ),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {
                "status": status,
                "found_count": len(raw),
                "saved_count": saved,
                "updated_count": updated,
                "score_updated": score_updated,
                "score_skipped": score_skipped,
                "duration_ms": duration_ms,
                "disclaimer": "仅供分析，不构成投注建议",
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            logger.error("crawl_jingcai_scores failed: %s", e)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="odds",
                league_id=None,
                league_name="竞彩赛果回写",
                found_count=0,
                saved_count=0,
                status="failed",
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {
                "status": "failed",
                "error": str(e),
                "found_count": 0,
                "updated_count": 0,
                "duration_ms": duration_ms,
            }

    def cleanup_stale_upcoming(self) -> int:
        """去掉已过期却仍标成未开赛的场次，以及初始化写入的演示赛程。"""
        db = SessionLocal()
        removed = 0
        try:
            from db.models import MatchPrediction, MatchPlayerStat, MatchTeamStat, OddsSnapshot, RiskAlert
            today = date.today()
            stale = db.query(Match).filter(
                Match.status == 'upcoming',
                Match.match_date < today,
            ).all()
            for match in stale:
                try:
                    db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id == match.id).delete()
                    db.query(MatchTeamStat).filter(MatchTeamStat.match_id == match.id).delete()
                    db.query(OddsSnapshot).filter(OddsSnapshot.match_id == match.id).delete()
                    db.query(MatchPrediction).filter(MatchPrediction.match_id == match.id).delete()
                    db.query(RiskAlert).filter(RiskAlert.match_id == match.id).delete()
                    db.delete(match)
                    removed += 1
                except Exception as e:
                    db.rollback()
                    logger.debug("Skip deleting match %s: %s", match.id, e)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("Cleanup stale upcoming failed: %s", e)
        finally:
            db.close()
        logger.info("Removed %s stale upcoming matches", removed)
        return removed

    def _save_crawl_log(self, **kwargs):
        # MySQL TEXT ≈ 64KB；历史赛程 JSON 常超限，截断为摘要以免整条日志写入失败
        raw = kwargs.get("crawled_data")
        if raw and isinstance(raw, str) and len(raw.encode("utf-8", errors="ignore")) > 60000:
            try:
                payload = json.loads(raw)
                if isinstance(payload, list):
                    sample = payload[:5]
                    kwargs["crawled_data"] = json.dumps(
                        {"total": len(payload), "sample": sample, "truncated": True},
                        default=str,
                        ensure_ascii=False,
                    )
                else:
                    kwargs["crawled_data"] = raw[:20000] + "...[truncated]"
            except Exception:
                kwargs["crawled_data"] = raw[:20000] + "...[truncated]"
        db = SessionLocal()
        try:
            CrawlLogService.create(db, kwargs)
        except Exception as e:
            logger.error(f"Failed to save crawl log: {str(e)}")
        finally:
            db.close()

    # ===== 历史赛事采集 =====

    def crawl_historical_league(
        self,
        league_id: str,
        days_back: int = 30,
        crawl_type: str = 'manual',
        start_date: date = None,
        seasons_back: int = 2,
    ) -> Dict:
        start_time = datetime.now()
        logger.info(f"Starting historical crawl for league: {league_id} (type: {crawl_type})")

        db = SessionLocal()
        try:
            league = LeagueService.get_by_id(db, league_id)
            league_name = league.name if league else league_id
            source_url = league.source_url if league else None
        finally:
            db.close()

        try:
            raw_matches = []
            if getattr(self, '_team_crawler', None):
                try:
                    raw_matches = self._team_crawler.crawl_fixtures(
                        league_id,
                        source_url=source_url,
                        include_history=True,
                        seasons_back=seasons_back,
                    )
                except Exception as e:
                    logger.warning("Historical fixture crawl failed for %s: %s", league_id, e)
            if not raw_matches:
                logger.warning(
                    "No real historical fixtures for %s; skipping (mock fallback removed)",
                    league_id,
                )
            saved_count, updated_count = self._save_matches(raw_matches)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            logger.info(f"Historical crawl completed for league {league_id}: {len(raw_matches)} found, {saved_count} saved")

            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='match',
                league_id=league_id,
                league_name=league_name,
                found_count=len(raw_matches),
                saved_count=saved_count,
                status='success',
                crawled_data=json.dumps(raw_matches, default=str, ensure_ascii=False),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )

            return {
                'league_id': league_id,
                'found_count': len(raw_matches),
                'saved_count': saved_count,
                'status': 'success',
                'duration_ms': duration_ms
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            logger.error(f"Historical crawl failed for league {league_id}: {str(e)}")

            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='match',
                league_id=league_id,
                league_name=league_name,
                found_count=0,
                saved_count=0,
                status='failed',
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )

            return {
                'league_id': league_id,
                'found_count': 0,
                'saved_count': 0,
                'status': 'failed',
                'error': str(e),
                'duration_ms': duration_ms
            }

    def crawl_all_historical(
        self,
        days_back: int = 30,
        crawl_type: str = 'manual',
        start_date: date = None,
        seasons_back: int = 2,
    ) -> List[Dict]:
        from services.real_team_crawler import get_priority_leagues
        if not start_date:
            start_date = date(date.today().year, 1, 1)
        start_time = datetime.now()
        logger.info(
            "Starting historical crawl for priority leagues (type: %s, from %s, seasons_back=%s)",
            crawl_type, start_date, seasons_back,
        )

        db = SessionLocal()
        try:
            target_ids = [
                lid for lid in get_priority_leagues()
                if LeagueService.get_by_id(db, lid)
            ]
        finally:
            db.close()

        results = []
        for lid in target_ids:
            results.append(
                self.crawl_historical_league(
                    lid, days_back, crawl_type, start_date, seasons_back=seasons_back
                )
            )

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        total_found = sum(r.get('found_count', 0) for r in results)
        total_saved = sum(r.get('saved_count', 0) for r in results)

        self._save_crawl_log(
            crawl_type=crawl_type,
            crawl_category='match',
            league_id=None,
            league_name='规范联赛历史赛程',
            found_count=total_found,
            saved_count=total_saved,
            status='success' if results and all(r['status'] == 'success' for r in results) else 'failed',
            started_at=start_time,
            finished_at=end_time,
            duration_ms=duration_ms
        )
        return results

    def _save_historical_matches(self, raw_matches: List[Dict]) -> int:
        from services.match_dedup import (
            canonical_match_id,
            find_existing_match,
            resolve_ingest_teams,
        )
        db = SessionLocal()
        saved_count = 0
        try:
            for match_data in raw_matches:
                league_id = match_data.get('league_id') or 'OTHER'
                resolved = resolve_ingest_teams(
                    db,
                    league_id,
                    match_data.get('home_team_id'),
                    match_data.get('away_team_id'),
                    match_data.get('home_team_name'),
                    match_data.get('away_team_name'),
                    self._remap_team_id,
                )
                if not resolved:
                    continue
                match_data['home_team_id'], match_data['away_team_id'] = resolved
                match_data['id'] = canonical_match_id(
                    league_id, match_data.get('match_date'), resolved[0], resolved[1]
                )

                match_data_clean = {k: v for k, v in match_data.items() if k in [
                    'id', 'league_id', 'home_team_id', 'away_team_id', 'match_date', 'match_time',
                    'venue', 'status', 'home_goals', 'away_goals', 'result', 'weather',
                    'temperature', 'pitch_condition', 'stage', 'group_name', 'round_name',
                    'fixture_id', 'process_id', 'handicap', 'handicap_line',
                    'odds_nspf_win', 'odds_nspf_draw', 'odds_nspf_lose',
                    'odds_spf_win', 'odds_spf_draw', 'odds_spf_lose',
                    'odds_bf_json',
                    'is_single', 'buy_end_time',
                    'half_score', 'match_no', 'source',
                ]}
                existing = find_existing_match(
                    db,
                    league_id=match_data_clean.get('league_id'),
                    match_date=match_data_clean.get('match_date'),
                    home_team_id=match_data_clean.get('home_team_id'),
                    away_team_id=match_data_clean.get('away_team_id'),
                    fixture_id=match_data_clean.get('fixture_id'),
                    remap_team_fn=self._remap_team_id,
                )
                if existing:
                    changed = False
                    for key in [
                        'status', 'home_goals', 'away_goals', 'result', 'match_date', 'match_time',
                        'round_name', 'league_id', 'fixture_id', 'process_id', 'handicap', 'handicap_line',
                        'odds_nspf_win', 'odds_nspf_draw', 'odds_nspf_lose',
                        'odds_spf_win', 'odds_spf_draw', 'odds_spf_lose',
                        'odds_bf_json',
                        'is_single', 'buy_end_time',
                        'half_score', 'match_no', 'source',
                        'venue', 'weather', 'temperature', 'pitch_condition',
                    ]:
                        if key not in match_data_clean or match_data_clean[key] is None:
                            continue
                        if key in ('venue', 'weather', 'temperature', 'pitch_condition'):
                            if match_data_clean[key] == '':
                                continue
                        if getattr(existing, key, None) != match_data_clean[key]:
                            setattr(existing, key, match_data_clean[key])
                            changed = True
                    if changed:
                        db.commit()
                    continue

                player_stats_data = match_data.pop('player_stats', [])

                match = MatchService.create(db, match_data_clean)
                saved_count += 1

                for stat_data in player_stats_data:
                    stat_data['match_id'] = match.id
                    MatchPlayerStatService.create(db, stat_data)

        finally:
            db.close()
        return saved_count

    def cleanup_dirty_teams_and_matches(self) -> Dict:
        """清理中文/数字前缀脏球队 ID 及其赛事；可映射的赛事合并到规范 ID 场次。"""
        from services.real_team_crawler import is_clean_team_id, resolve_team_alias
        from db.models import (
            MatchPrediction, MatchPlayerStat, MatchTeamStat, OddsSnapshot, RiskAlert, UserFavorite, UserHistory,
            Standing, TopScorer, Player,
        )

        db = SessionLocal()
        stats = {
            "dirty_teams": 0,
            "matches_deleted": 0,
            "matches_merged": 0,
            "teams_deleted": 0,
            "predictions_deleted": 0,
            "standings_deleted": 0,
            "players_nulled": 0,
        }
        try:
            def _resolve_side(tid: str, league_id: str) -> Optional[str]:
                if is_clean_team_id(tid) and TeamService.get_by_id(db, tid):
                    return tid
                alias = resolve_team_alias(tid)
                if is_clean_team_id(alias) and TeamService.get_by_id(db, alias):
                    return alias
                remapped = self._remap_team_id(
                    db, league_id or "", team_id=tid, team_name=tid, allow_global=True
                )
                if is_clean_team_id(remapped) and TeamService.get_by_id(db, remapped):
                    return remapped
                return None

            def _purge_match(match_id: str):
                stats["predictions_deleted"] += db.query(MatchPrediction).filter(
                    MatchPrediction.match_id == match_id
                ).delete(synchronize_session=False)
                db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id == match_id).delete(
                    synchronize_session=False
                )
                db.query(MatchTeamStat).filter(MatchTeamStat.match_id == match_id).delete(
                    synchronize_session=False
                )
                db.query(OddsSnapshot).filter(OddsSnapshot.match_id == match_id).delete(
                    synchronize_session=False
                )
                db.query(RiskAlert).filter(RiskAlert.match_id == match_id).delete(
                    synchronize_session=False
                )
                db.query(UserFavorite).filter(UserFavorite.match_id == match_id).delete(
                    synchronize_session=False
                )
                db.query(UserHistory).filter(UserHistory.match_id == match_id).delete(
                    synchronize_session=False
                )
                db.query(Match).filter(Match.id == match_id).delete(synchronize_session=False)

            dirty_rows = []
            for m in db.query(Match).all():
                if (
                    not is_clean_team_id(m.home_team_id)
                    or not is_clean_team_id(m.away_team_id)
                    or any("\u4e00" <= c <= "\u9fff" for c in (m.id or ""))
                ):
                    dirty_rows.append({
                        "id": m.id,
                        "league_id": m.league_id,
                        "home_team_id": m.home_team_id,
                        "away_team_id": m.away_team_id,
                        "match_date": m.match_date,
                        "fixture_id": m.fixture_id,
                        "process_id": m.process_id,
                        "handicap": m.handicap,
                        "odds_nspf_win": m.odds_nspf_win,
                        "odds_nspf_draw": m.odds_nspf_draw,
                        "odds_nspf_lose": m.odds_nspf_lose,
                        "odds_spf_win": m.odds_spf_win,
                        "odds_spf_draw": m.odds_spf_draw,
                        "odds_spf_lose": m.odds_spf_lose,
                        "is_single": m.is_single,
                        "buy_end_time": m.buy_end_time,
                        "venue": m.venue,
                        "weather": m.weather,
                        "temperature": m.temperature,
                        "pitch_condition": m.pitch_condition,
                        "round_name": m.round_name,
                        "match_time": m.match_time,
                        "status": m.status,
                        "home_goals": m.home_goals,
                        "away_goals": m.away_goals,
                        "result": m.result,
                        "stage": m.stage,
                        "group_name": m.group_name,
                    })

            for row in dirty_rows:
                mid = row["id"]
                home = _resolve_side(row["home_team_id"], row["league_id"])
                away = _resolve_side(row["away_team_id"], row["league_id"])
                if home and away and home != away and row.get("match_date"):
                    date_s = row["match_date"].strftime("%Y-%m-%d")
                    new_id = f"{row['league_id']}-{date_s}-{home}-{away}"[:50]
                    existing = MatchService.get_by_id(db, new_id)
                    if existing:
                        for key in (
                            "fixture_id", "process_id", "handicap",
                            "odds_nspf_win", "odds_nspf_draw", "odds_nspf_lose",
                            "odds_spf_win", "odds_spf_draw", "odds_spf_lose",
                            "is_single", "buy_end_time", "venue",
                            "weather", "temperature", "pitch_condition", "round_name",
                        ):
                            new_val = row.get(key)
                            if new_val in (None, ""):
                                continue
                            if getattr(existing, key, None) in (None, ""):
                                setattr(existing, key, new_val)
                        _purge_match(mid)
                        stats["matches_merged"] += 1
                        continue
                    if new_id != mid:
                        payload = dict(row)
                        payload["id"] = new_id
                        payload["home_team_id"] = home
                        payload["away_team_id"] = away
                        db.add(Match(**payload))
                        db.flush()
                        db.query(MatchPrediction).filter(MatchPrediction.match_id == mid).update(
                            {"match_id": new_id}, synchronize_session=False
                        )
                        db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id == mid).update(
                            {"match_id": new_id}, synchronize_session=False
                        )
                        db.query(RiskAlert).filter(RiskAlert.match_id == mid).update(
                            {"match_id": new_id}, synchronize_session=False
                        )
                        db.query(UserFavorite).filter(UserFavorite.match_id == mid).update(
                            {"match_id": new_id}, synchronize_session=False
                        )
                        db.query(UserHistory).filter(UserHistory.match_id == mid).update(
                            {"match_id": new_id}, synchronize_session=False
                        )
                        db.query(Match).filter(Match.id == mid).delete(synchronize_session=False)
                        stats["matches_merged"] += 1
                        continue

                _purge_match(mid)
                stats["matches_deleted"] += 1

            db.expire_all()

            dirty_teams = [t.id for t in db.query(Team).all() if not is_clean_team_id(t.id)]
            stats["dirty_teams"] = len(dirty_teams)
            from db.models import User
            for tid in dirty_teams:
                still = db.query(Match).filter(
                    (Match.home_team_id == tid) | (Match.away_team_id == tid)
                ).count()
                if still:
                    continue
                stats["standings_deleted"] += db.query(Standing).filter(
                    Standing.team_id == tid
                ).delete(synchronize_session=False)
                db.query(TopScorer).filter(TopScorer.team_id == tid).delete(
                    synchronize_session=False
                )
                db.query(MatchPlayerStat).filter(MatchPlayerStat.team_id == tid).delete(
                    synchronize_session=False
                )
                n = db.query(Player).filter(Player.team_id == tid).update(
                    {"team_id": None}, synchronize_session=False
                )
                stats["players_nulled"] += n or 0
                db.query(UserFavorite).filter(UserFavorite.team_id == tid).delete(
                    synchronize_session=False
                )
                db.query(User).filter(User.favorite_team_id == tid).update(
                    {"favorite_team_id": None}, synchronize_session=False
                )
                db.query(Team).filter(Team.id == tid).delete(synchronize_session=False)
                stats["teams_deleted"] += 1

            db.commit()
            logger.info("cleanup_dirty_teams_and_matches done: %s", stats)
            return {"status": "success", **stats}
        except Exception as e:
            db.rollback()
            logger.exception("cleanup_dirty_teams_and_matches failed")
            return {"status": "failed", "error": str(e), **stats}
        finally:
            db.close()

    # ===== 球员数据采集 =====

    def crawl_players(self, league_id: str = None, team_id: str = None, crawl_type: str = 'manual') -> Dict:
        """采集真实球队阵容（500.com 球员名单），无模拟数据。"""
        start_time = datetime.now()
        scope = f"league {league_id}" if league_id else (f"team {team_id}" if team_id else "all")
        logger.info(f"Starting player crawl for {scope} (type: {crawl_type})")

        db = SessionLocal()
        try:
            source_url = None
            target_league = league_id
            if team_id and not target_league:
                team = TeamService.get_by_id(db, team_id)
                target_league = team.league_id if team else None
            if target_league:
                league = LeagueService.get_by_id(db, target_league)
                league_name = league.name if league else target_league
                source_url = league.source_url if league else None
                from services.real_team_crawler import CANONICAL_FIVE00_URL, FIVE00_TO_CANONICAL
                canonical = FIVE00_TO_CANONICAL.get(target_league, target_league)
                source_url = source_url or CANONICAL_FIVE00_URL.get(canonical)
            else:
                league_name = '全部联赛'
        finally:
            db.close()

        try:
            raw_players = []
            if getattr(self, '_team_crawler', None) and target_league:
                raw_players = self._team_crawler.crawl_squads(
                    target_league, source_url=source_url, team_id=team_id
                )
            if not raw_players:
                crawler = None
                if league_id:
                    crawler = self._player_crawlers.get(league_id)
                if crawler is None and self._default_player_crawler and league_id == "WC":
                    crawler = self._default_player_crawler
                if crawler:
                    raw_players = crawler.crawl(league_id=league_id, team_id=team_id) or []
                else:
                    logger.warning(
                        "No real squad data for %s; skipping (mock player crawler removed)",
                        scope,
                    )
            saved_count = self._save_players(raw_players)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            logger.info(f"Player crawl completed for {scope}: {len(raw_players)} found, {saved_count} saved")

            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='squad',
                league_id=league_id or target_league,
                league_name=league_name,
                found_count=len(raw_players),
                saved_count=saved_count,
                updated_count=0,
                status='success',
                crawled_data=json.dumps(
                    [{'id': p.get('id'), 'name': p.get('name'), 'team_id': p.get('team_id')} for p in raw_players[:40]],
                    ensure_ascii=False
                ),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )

            return {
                'scope': scope,
                'league_id': league_id or target_league,
                'found_count': len(raw_players),
                'saved_count': saved_count,
                'status': 'success',
                'duration_ms': duration_ms
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            logger.error(f"Player crawl failed for {scope}: {str(e)}")

            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='squad',
                league_id=league_id,
                league_name=league_name,
                found_count=0,
                saved_count=0,
                updated_count=0,
                status='failed',
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )

            return {
                'scope': scope,
                'league_id': league_id,
                'found_count': 0,
                'updated_count': 0,
                'status': 'failed',
                'error': str(e),
                'duration_ms': duration_ms
            }

    def crawl_live500(self, crawl_type: str = 'manual') -> Dict:
        """重点联赛比分/状态轻量回写（Live500 看板 → 已有场次，不新建非规范赛事）。"""
        start_time = datetime.now()
        logger.info("Starting Live500 score/status crawl (type: %s)", crawl_type)

        live = getattr(self, "_live_500_crawler", None)
        if not live:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="match",
                league_id=None,
                league_name="Live500",
                found_count=0,
                saved_count=0,
                status="failed",
                error_message="Live500 crawler not loaded",
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {"status": "failed", "error": "Live500 crawler not loaded"}

        try:
            from services.real_team_crawler import get_priority_leagues
            raw_matches = live.crawl("all") or []
            priority = set(get_priority_leagues())
            raw_matches = [m for m in raw_matches if m.get("league_id") in priority]
            updated_count, skipped = self._update_match_score_status(raw_matches)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="match",
                league_id=None,
                league_name="Live500比分回写",
                found_count=len(raw_matches),
                saved_count=0,
                updated_count=updated_count,
                status="success",
                crawled_data=json.dumps(
                    {
                        "updated": updated_count,
                        "skipped": skipped,
                        "mode": "score_status_only",
                        "leagues": list(priority),
                    },
                    ensure_ascii=False,
                ),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            logger.info(
                "Live500 score/status: found=%s updated=%s skipped=%s",
                len(raw_matches), updated_count, skipped,
            )
            return {
                "league_id": "LIVE500",
                "found_count": len(raw_matches),
                "updated_count": updated_count,
                "skipped": skipped,
                "status": "success",
                "duration_ms": duration_ms,
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            logger.error("Live500 crawl failed: %s", e)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="match",
                league_id=None,
                league_name="Live500比分回写",
                found_count=0,
                saved_count=0,
                status="failed",
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {
                "league_id": "LIVE500",
                "found_count": 0,
                "updated_count": 0,
                "status": "failed",
                "error": str(e),
                "duration_ms": duration_ms,
            }

    def crawl_live_jingcai(self, days_ahead: int = 1, crawl_type: str = "manual") -> Dict:
        """采集 live.500.com/jczq.php 竞彩比分列表并入库（分析用，非投注建议）。"""
        start_time = datetime.now()
        logger.info("Starting LiveJingcai crawl (type: %s)", crawl_type)
        jc = getattr(self, "_live_jingcai_crawler", None)
        if not jc:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="odds",
                league_id=None,
                league_name="竞彩比分",
                found_count=0,
                saved_count=0,
                status="failed",
                error_message="LiveJingcai crawler not loaded",
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {"status": "failed", "error": "LiveJingcai crawler not loaded"}

        try:
            raw_matches = jc.crawl(days_ahead=days_ahead) or []
            saved, updated = self._save_matches(raw_matches)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="odds",
                league_id=None,
                league_name="竞彩比分",
                found_count=len(raw_matches),
                saved_count=saved,
                updated_count=updated,
                status="success",
                crawled_data=json.dumps(
                    {
                        "source": "https://live.500.com/jczq.php",
                        "days_ahead": days_ahead,
                    },
                    ensure_ascii=False,
                ),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            logger.info(
                "LiveJingcai crawl done: found=%s saved=%s updated=%s",
                len(raw_matches), saved, updated,
            )
            return {
                "status": "success",
                "found_count": len(raw_matches),
                "saved_count": saved,
                "updated_count": updated,
                "duration_ms": duration_ms,
                "disclaimer": "仅供分析，不构成投注建议",
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            logger.error("LiveJingcai crawl failed: %s", e)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="odds",
                league_id=None,
                league_name="竞彩比分",
                found_count=0,
                saved_count=0,
                status="failed",
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {
                "status": "failed",
                "error": str(e),
                "found_count": 0,
                "saved_count": 0,
                "duration_ms": duration_ms,
            }

    def _update_match_score_status(self, raw_matches: List[Dict]) -> Tuple[int, int]:
        """只更新已存在场次的 status / 比分 / result，不插入新行。"""
        from services.match_dedup import find_existing_match
        from services.team_resolver import TeamResolver
        from db.models import Match as MatchModel

        updated = 0
        skipped = 0
        db = SessionLocal()
        try:
            for raw in raw_matches or []:
                existing = None
                fid = str(raw.get("fixture_id") or "").strip()
                if fid:
                    existing = db.query(MatchModel).filter(MatchModel.fixture_id == fid).first()

                if not existing:
                    league_id = raw.get("league_id")
                    match_date = raw.get("match_date")
                    home_name = raw.get("home_team_name") or ""
                    away_name = raw.get("away_team_name") or ""
                    home_id = (
                        TeamResolver.resolve_clean(home_name)
                        or (
                            raw.get("home_team_id")
                            if TeamResolver.is_clean(raw.get("home_team_id"))
                            else None
                        )
                    )
                    away_id = (
                        TeamResolver.resolve_clean(away_name)
                        or (
                            raw.get("away_team_id")
                            if TeamResolver.is_clean(raw.get("away_team_id"))
                            else None
                        )
                    )
                    if not league_id or not match_date or not home_id or not away_id:
                        skipped += 1
                        continue
                    existing = find_existing_match(
                        db,
                        league_id=league_id,
                        match_date=match_date,
                        home_team_id=home_id,
                        away_team_id=away_id,
                        fixture_id=raw.get("fixture_id"),
                        remap_team_fn=self._remap_team_id,
                    )
                if not existing:
                    skipped += 1
                    continue
                changed = False
                status = raw.get("status")
                if status in ("upcoming", "live", "finished") and existing.status != status:
                    existing.status = status
                    changed = True
                if raw.get("home_goals") is not None and existing.home_goals != raw.get("home_goals"):
                    existing.home_goals = int(raw.get("home_goals") or 0)
                    changed = True
                if raw.get("away_goals") is not None and existing.away_goals != raw.get("away_goals"):
                    existing.away_goals = int(raw.get("away_goals") or 0)
                    changed = True
                result = raw.get("result")
                if result in ("H", "A", "D") and existing.result != result:
                    existing.result = result
                    changed = True
                elif existing.home_goals is not None and existing.away_goals is not None:
                    hg, ag = int(existing.home_goals), int(existing.away_goals)
                    derived = "H" if hg > ag else ("A" if hg < ag else "D")
                    if existing.result != derived:
                        existing.result = derived
                        changed = True
                if changed:
                    updated += 1
            if updated:
                db.commit()
                from services.jingcai_score_top3 import invalidate_pool_cache
                invalidate_pool_cache()
            else:
                db.rollback()
        except Exception as e:
            db.rollback()
            logger.error("update match score/status failed: %s", e)
            raise
        finally:
            db.close()
        return updated, skipped

    def crawl_all_players(self, crawl_type: str = 'scheduled') -> List[Dict]:
        """采集规范联赛的真实阵容。"""
        from services.real_team_crawler import ESPN_LEAGUE_MAP, CANONICAL_FIVE00_URL
        start_time = datetime.now()
        logger.info(f"Starting player crawl for canonical leagues (type: {crawl_type})")

        db = SessionLocal()
        try:
            target_ids = []
            for lid in list(ESPN_LEAGUE_MAP.keys()) + list(CANONICAL_FIVE00_URL.keys()):
                if lid not in target_ids and LeagueService.get_by_id(db, lid):
                    target_ids.append(lid)
        finally:
            db.close()

        results = []
        for lid in target_ids:
            results.append(self.crawl_players(league_id=lid, crawl_type=crawl_type))

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        total_found = sum(r.get('found_count', 0) for r in results)
        total_saved = sum(r.get('saved_count', 0) for r in results)

        self._save_crawl_log(
            crawl_type=crawl_type,
            crawl_category='squad',
            league_id=None,
            league_name='规范联赛阵容',
            found_count=total_found,
            saved_count=total_saved,
            status='success' if results and all(r.get('status') == 'success' for r in results) else 'failed',
            started_at=start_time,
            finished_at=end_time,
            duration_ms=duration_ms
        )
        logger.info(f"Player crawl all leagues completed: {total_found} found, {total_saved} saved")
        return results

    def _save_player_stats(self, raw_stats: List[Dict]) -> int:
        """按球队+球衣号/姓名匹配已有球员，刷新进球等统计。"""
        db = SessionLocal()
        saved_count = 0
        try:
            for raw in raw_stats:
                team_id = raw.get("team_id")
                if not team_id or not TeamService.get_by_id(db, team_id):
                    continue

                player = None
                if raw.get("id"):
                    player = PlayerService.get_by_id(db, str(raw["id"])[:30])
                if not player and raw.get("jersey_number") is not None:
                    player = db.query(Player).filter(
                        Player.team_id == team_id,
                        Player.jersey_number == raw["jersey_number"],
                    ).first()
                if not player and raw.get("name"):
                    player = db.query(Player).filter(
                        Player.team_id == team_id,
                        Player.name == raw["name"],
                    ).first()

                if not player:
                    continue

                update_fields = {}
                for stat_key in ("goals", "assists", "appearances", "yellow_cards", "red_cards"):
                    if stat_key in raw and raw[stat_key] is not None:
                        update_fields[stat_key] = raw[stat_key]
                if not update_fields:
                    continue

                try:
                    PlayerService.update(db, player.id, update_fields)
                    saved_count += 1
                except Exception as e:
                    db.rollback()
                    logger.warning("Skip player stats %s: %s", player.id, e)
        finally:
            db.close()
        return saved_count

    def crawl_player_stats(self, league_id: str = None, team_id: str = None, crawl_type: str = 'manual') -> Dict:
        """采集球员进球/助攻/出场数据（ESPN roster + 500.com 兜底），并刷新已有记录。"""
        start_time = datetime.now()
        scope = f"league {league_id}" if league_id else (f"team {team_id}" if team_id else "all")
        logger.info(f"Starting player stats crawl for {scope} (type: {crawl_type})")

        db = SessionLocal()
        try:
            source_url = None
            target_league = league_id
            if team_id and not target_league:
                team = TeamService.get_by_id(db, team_id)
                target_league = team.league_id if team else None
            if target_league:
                league = LeagueService.get_by_id(db, target_league)
                league_name = league.name if league else target_league
                source_url = league.source_url if league else None
                from services.real_team_crawler import CANONICAL_FIVE00_URL, FIVE00_TO_CANONICAL
                canonical = FIVE00_TO_CANONICAL.get(target_league, target_league)
                source_url = source_url or CANONICAL_FIVE00_URL.get(canonical)
            else:
                league_name = '全部联赛'
        finally:
            db.close()

        try:
            if not getattr(self, '_team_crawler', None):
                raise RuntimeError("Team crawler not loaded")
            if not target_league:
                raise ValueError("请指定 league_id 或 team_id")

            raw_stats = self._team_crawler.crawl_squad_stats(
                target_league, source_url=source_url, team_id=team_id
            )
            with_stats = [p for p in raw_stats if (p.get('goals') or p.get('assists') or p.get('appearances'))]
            saved_count = self._save_player_stats(raw_stats)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            logger.info(
                "Player stats crawl completed for %s: %s found, %s with stats, %s saved",
                scope, len(raw_stats), len(with_stats), saved_count,
            )

            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='player',
                league_id=league_id or target_league,
                league_name=league_name,
                found_count=len(raw_stats),
                saved_count=saved_count,
                updated_count=len(with_stats),
                status='success',
                crawled_data=json.dumps(
                    [
                        {
                            'id': p.get('id'), 'name': p.get('name'),
                            'goals': p.get('goals'), 'assists': p.get('assists'),
                            'appearances': p.get('appearances'),
                        }
                        for p in with_stats[:40]
                    ],
                    ensure_ascii=False,
                ),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )

            return {
                'scope': scope,
                'league_id': league_id or target_league,
                'found_count': len(raw_stats),
                'with_stats_count': len(with_stats),
                'saved_count': saved_count,
                'status': 'success',
                'duration_ms': duration_ms,
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            logger.error("Player stats crawl failed for %s: %s", scope, e)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='player',
                league_id=league_id or target_league,
                league_name=league_name,
                found_count=0,
                saved_count=0,
                status='failed',
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            return {
                'scope': scope,
                'league_id': league_id or target_league,
                'found_count': 0,
                'saved_count': 0,
                'status': 'failed',
                'error': str(e),
                'duration_ms': duration_ms,
            }

    def crawl_all_player_stats(self, crawl_type: str = 'scheduled') -> List[Dict]:
        """批量采集规范联赛的球员进球/助攻/出场数据。"""
        from services.real_team_crawler import ESPN_LEAGUE_MAP, CANONICAL_FIVE00_URL
        start_time = datetime.now()
        logger.info("Starting player stats crawl for canonical leagues (type: %s)", crawl_type)

        db = SessionLocal()
        try:
            target_ids = []
            for lid in list(ESPN_LEAGUE_MAP.keys()) + list(CANONICAL_FIVE00_URL.keys()):
                if lid not in target_ids and LeagueService.get_by_id(db, lid):
                    target_ids.append(lid)
        finally:
            db.close()

        results = []
        for lid in target_ids:
            results.append(self.crawl_player_stats(league_id=lid, crawl_type=crawl_type))

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        total_found = sum(r.get('found_count', 0) for r in results)
        total_saved = sum(r.get('saved_count', 0) for r in results)
        total_with_stats = sum(r.get('with_stats_count', 0) for r in results)

        self._save_crawl_log(
            crawl_type=crawl_type,
            crawl_category='player',
            league_id=None,
            league_name='球员进球统计',
            found_count=total_found,
            saved_count=total_saved,
            updated_count=total_with_stats,
            status='success' if results and all(r.get('status') == 'success' for r in results) else 'failed',
            started_at=start_time,
            finished_at=end_time,
            duration_ms=duration_ms,
        )
        logger.info(
            "Player stats crawl all leagues completed: %s found, %s with stats, %s saved",
            total_found, total_with_stats, total_saved,
        )
        return results

    # ===== 逐场球员统计采集 =====

    def _resolve_match_player_id(self, db, team_id: str, stat_data: Dict) -> Optional[str]:
        """将采集到的球员信息映射到本地 players 表；不存在则自动建档（满足外键）。"""
        valid_pos = {'GK', 'CB', 'RB', 'LB', 'DM', 'CM', 'AM', 'RM', 'LM', 'RW', 'LW', 'ST'}
        name = (stat_data.get("player_name") or "").strip()
        position = stat_data.get("position") or "CM"
        if position not in valid_pos:
            position = "CM"
        jersey = stat_data.get("jersey_number")
        player_id = (stat_data.get("player_id") or "").strip() or None

        if player_id:
            existing = PlayerService.get_by_id(db, player_id)
            if existing:
                return existing.id

        if name:
            player = db.query(Player).filter(
                Player.team_id == team_id,
                Player.name == name,
            ).first()
            if player:
                return player.id

        if jersey not in (None, ""):
            try:
                jersey_int = int(jersey)
            except (TypeError, ValueError):
                jersey_int = None
            if jersey_int is not None:
                player = db.query(Player).filter(
                    Player.team_id == team_id,
                    Player.jersey_number == jersey_int,
                ).first()
                if player:
                    return player.id

        # ESPN 球员本地不存在：写入 stubs，保证 match_player_stats 外键可落库
        new_id = (player_id or f"PX{team_id}{(name or 'UNK')[:12]}")[:30]
        # 避免同队同名冲突以外的 id 碰撞
        if PlayerService.get_by_id(db, new_id):
            suffix = abs(hash(f"{team_id}:{name}:{jersey}")) % 10000
            new_id = f"{new_id[:24]}{suffix}"[:30]

        if not PlayerService.get_by_id(db, new_id):
            try:
                PlayerService.create(db, {
                    "id": new_id,
                    "name": name or new_id,
                    "short_name": (name or new_id)[:20],
                    "jersey_number": int(jersey) if jersey not in (None, "") else None,
                    "position": position,
                    "team_id": team_id,
                    "goals": 0,
                    "assists": 0,
                    "appearances": 0,
                    "yellow_cards": 0,
                    "red_cards": 0,
                })
            except Exception as e:
                logger.warning("Auto-create player %s failed: %s", new_id, e)
                db.rollback()
                # 回滚后重查（并发/已存在）
                again = PlayerService.get_by_id(db, new_id)
                if again:
                    return again.id
                if name:
                    again = db.query(Player).filter(
                        Player.team_id == team_id, Player.name == name
                    ).first()
                    if again:
                        return again.id
                return None
        return new_id

    def _save_match_player_stats(self, match_id: str, raw_stats: List[Dict]) -> int:
        db = SessionLocal()
        saved = 0
        try:
            MatchPlayerStatService.delete_by_match(db, match_id)
            batch = []
            seen_players = set()
            for raw in raw_stats:
                team_id = raw.get("team_id")
                if not team_id:
                    continue
                if not TeamService.get_by_id(db, team_id):
                    continue
                player_id = self._resolve_match_player_id(db, team_id, raw)
                if not player_id or player_id in seen_players:
                    continue
                seen_players.add(player_id)
                payload = {
                    "match_id": match_id,
                    "player_id": player_id,
                    "team_id": team_id,
                    "is_home": bool(raw.get("is_home")),
                    "position": raw.get("position") or "CM",
                    "goals": int(raw.get("goals") or 0),
                    "assists": int(raw.get("assists") or 0),
                    "shots": int(raw.get("shots") or 0),
                    "shots_on_target": int(raw.get("shots_on_target") or 0),
                    "passes": int(raw.get("passes") or 0),
                    "pass_accuracy": raw.get("pass_accuracy"),
                    "tackles": int(raw.get("tackles") or 0),
                    "interceptions": int(raw.get("interceptions") or 0),
                    "clearances": int(raw.get("clearances") or 0),
                    "dribbles": int(raw.get("dribbles") or 0),
                    "dribble_success": int(raw.get("dribble_success") or 0),
                    "fouls_committed": int(raw.get("fouls_committed") or 0),
                    "fouls_suffered": int(raw.get("fouls_suffered") or 0),
                    "yellow_cards": int(raw.get("yellow_cards") or 0),
                    "red_cards": int(raw.get("red_cards") or 0),
                    "minutes_played": int(raw.get("minutes_played") or 0),
                    "rating": raw.get("rating"),
                }
                if payload["position"] not in {
                    'GK', 'CB', 'RB', 'LB', 'DM', 'CM', 'AM', 'RM', 'LM', 'RW', 'LW', 'ST'
                }:
                    payload["position"] = "CM"
                batch.append(payload)
            if batch:
                try:
                    saved = MatchPlayerStatService.batch_create(db, batch)
                except Exception as e:
                    db.rollback()
                    logger.error("batch_create match_player_stats failed for %s: %s", match_id, e)
                    saved = 0
        finally:
            db.close()
        return saved

    def _save_match_team_stats(self, match_id: str, team_rows: List[Dict]) -> int:
        if not team_rows:
            return 0
        db = SessionLocal()
        try:
            return MatchTeamStatService.upsert_for_match(db, match_id, team_rows)
        except Exception as e:
            logger.error("Save match team stats failed for %s: %s", match_id, e)
            try:
                db.rollback()
            except Exception:
                logger.warning("rollback match team stats failed for %s", match_id, exc_info=True)
            return 0
        finally:
            db.close()

    def _team_espn_map_score(self, team: Optional[object]) -> int:
        """估计球队能否映射到 ESPN（越高越优先补采）。"""
        if not team:
            return 0
        from services.real_team_crawler import ESPN_MATCH_ALIASES, ESPN_NAME_HINTS, TEAM_ALIASES

        tid = str(getattr(team, "id", "") or "").strip()
        name = str(getattr(team, "name", "") or "").strip()
        short = str(getattr(team, "short_name", "") or "").strip()
        score = 0
        # 规范短 ID（五大联赛主队）优先于 500.com 的 T*
        if tid and not tid.upper().startswith("T"):
            score += 3
        elif tid and len(tid) <= 5 and tid.isalpha():
            score += 3
        crawler = getattr(self, "_team_crawler", None)
        keys = [tid.lower(), name.lower(), short.lower()]
        for k in list(keys):
            if k:
                keys.append(re.sub(r"[\s\-\.]", "", k))
        for k in keys:
            if not k:
                continue
            if k in ESPN_MATCH_ALIASES or k in ESPN_NAME_HINTS or k in TEAM_ALIASES:
                score += 2
                break
            if crawler and crawler._alias_lookup(k):
                score += 2
                break
            try:
                from services.team_alias_service import alias_is_known
                if alias_is_known(k):
                    score += 2
                    break
            except Exception:
                pass
        if name and any("\u4e00" <= ch <= "\u9fff" for ch in name):
            # 有中文名时，别名表命中才可靠
            for k in (name.lower(), short.lower(), tid.lower()):
                if k in ESPN_MATCH_ALIASES or k in ESPN_NAME_HINTS:
                    score += 1
                    break
        return score

    def _match_espn_stage_priority(self, match) -> int:
        """欧冠等杯赛：正赛/可映射阶段优先；资格赛垫底（ESPN 常无源）。"""
        stage = str(getattr(match, "stage", "") or "").strip().lower()
        rn = str(getattr(match, "round_name", "") or "").strip()
        lid = str(getattr(match, "league_id", "") or "").upper()
        if lid != "UCL" and stage not in ("qualifying", "playoff", "play_in"):
            return 0
        if stage == "qualifying" or "资格" in rn:
            return -20
        if any(k in rn for k in ("第一圈", "第二圈")):
            return 1
        if "第三圈" in rn or stage == "play_in":
            return 4
        if "附加赛" in rn or stage == "playoff":
            return 6
        if stage in ("league", "group") or any(k in rn for k in ("联赛", "小组")):
            return 8
        if stage in (
            "knockout", "round_of_16", "quarter_final", "semi_final", "final"
        ) or any(k in rn for k in ("淘汰", "十六强", "八强", "半准", "半决赛", "决赛", "四分之一")):
            return 10
        return 2

    def _get_matches_needing_player_stats(
        self,
        db,
        league_id: str = None,
        match_id: str = None,
        limit: int = 50,
        prioritize_mappable: bool = True,
        prefer_older: bool = False,
    ):
        from db.models import MatchPlayerStat, MatchTeamStat
        from sqlalchemy import and_, or_

        player_ids = db.query(MatchPlayerStat.match_id).distinct()
        team_ids = db.query(MatchTeamStat.match_id).distinct()
        query = db.query(Match).filter(Match.status == "finished")
        if league_id:
            query = query.filter(Match.league_id == league_id)
        if match_id:
            query = query.filter(Match.id == match_id)
        else:
            # 球员或球队射门任一已有则不再占补采额度
            query = query.filter(~Match.id.in_(player_ids), ~Match.id.in_(team_ids))
            # 欧冠资格赛 ESPN 几乎无源，不占用补采额度
            if prioritize_mappable:
                ucl_qual = and_(
                    Match.league_id == "UCL",
                    or_(Match.stage == "qualifying", Match.round_name.contains("资格")),
                )
                query = query.filter(~ucl_qual)
        # 多取再按 ESPN 可映射性 + 阶段优先级重排；补采历史缺口时加大窗口
        if match_id or not prioritize_mappable:
            fetch_n = limit
        else:
            fetch_n = min(max(limit * 5, limit), 1200)
        date_col = Match.match_date.asc() if prefer_older else Match.match_date.desc()
        time_col = Match.match_time.asc() if prefer_older else Match.match_time.desc()
        rows = query.order_by(date_col, time_col).limit(fetch_n).all()
        if not prioritize_mappable or match_id or len(rows) <= limit:
            return rows[:limit]

        scored = []
        for m in rows:
            home = TeamService.get_by_id(db, m.home_team_id)
            away = TeamService.get_by_id(db, m.away_team_id)
            map_score = self._team_espn_map_score(home) + self._team_espn_map_score(away)
            stage_bonus = self._match_espn_stage_priority(m)
            # prefer_older：映射分+阶段优先，其次更早日期；默认偏近
            date_key = m.match_date or date.min
            ord_v = date_key.toordinal() if hasattr(date_key, "toordinal") else 0
            secondary = -ord_v if prefer_older else ord_v
            scored.append((map_score + stage_bonus, secondary, m))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [m for _, __, m in scored[:limit]]

    def crawl_match_player_stats(
        self,
        match_id: str = None,
        league_id: str = None,
        limit: int = 50,
        crawl_type: str = "manual",
        prioritize_mappable: bool = True,
        prefer_older: bool = False,
    ) -> Dict:
        """采集逐场球员统计（ESPN 单场 summary；无 mock 兜底）。"""
        start_time = datetime.now()
        team_crawler = getattr(self, "_team_crawler", None)
        if team_crawler and hasattr(team_crawler, "clear_espn_scoreboard_cache"):
            team_crawler.clear_espn_scoreboard_cache()

        db = SessionLocal()
        try:
            matches = self._get_matches_needing_player_stats(
                db,
                league_id=league_id,
                match_id=match_id,
                limit=limit,
                prioritize_mappable=prioritize_mappable,
                prefer_older=prefer_older,
            )
            league_name = "全部联赛"
            if league_id:
                league = LeagueService.get_by_id(db, league_id)
                league_name = league.name if league else league_id
            elif match_id and matches:
                league = LeagueService.get_by_id(db, matches[0].league_id)
                league_name = league.name if league else matches[0].league_id
        finally:
            db.close()

        found_count = len(matches)
        saved_matches = 0
        saved_stats = 0
        saved_team_rows = 0
        espn_hits = 0
        five00_hits = 0
        fallback_hits = 0
        miss_count = 0
        errors = []

        for match in matches:
            db = SessionLocal()
            try:
                home = TeamService.get_by_id(db, match.home_team_id)
                away = TeamService.get_by_id(db, match.away_team_id)
                if not home or not away:
                    continue
                home_info = {"id": home.id, "name": home.name, "short_name": home.short_name}
                away_info = {"id": away.id, "name": away.name, "short_name": away.short_name}
            finally:
                db.close()

            raw_stats = []
            team_rows = []
            if team_crawler and match.league_id:
                try:
                    if hasattr(team_crawler, "crawl_match_stats_bundle"):
                        raw_stats, team_rows = team_crawler.crawl_match_stats_bundle(
                            match.league_id,
                            home_info,
                            away_info,
                            match.match_date,
                            home_goals=match.home_goals,
                            away_goals=match.away_goals,
                        )
                    else:
                        raw_stats = team_crawler.crawl_match_player_stats(
                            match.league_id,
                            home_info,
                            away_info,
                            match.match_date,
                            home_goals=match.home_goals,
                            away_goals=match.away_goals,
                        )
                except Exception as e:
                    errors.append(f"{match.id}: ESPN {e}")

            if raw_stats:
                espn_hits += 1

            if not team_rows and raw_stats and team_crawler and hasattr(
                team_crawler, "aggregate_team_shots_from_players"
            ):
                team_rows = team_crawler.aggregate_team_shots_from_players(
                    raw_stats, home_info, away_info
                )

            if not raw_stats and not team_rows and getattr(match, "fixture_id", None):
                try:
                    from services.five00_fenxi_crawler import five00_fenxi_crawler
                    team_rows = five00_fenxi_crawler.crawl_team_shots(
                        match.fixture_id, home_info["id"], away_info["id"]
                    )
                    if team_rows:
                        five00_hits += 1
                except Exception as e:
                    errors.append(f"{match.id}: 500 fenxi {e}")

            if not raw_stats and not team_rows:
                miss_count += 1
                continue

            player_count = 0
            team_count = 0
            if raw_stats:
                try:
                    player_count = self._save_match_player_stats(match.id, raw_stats)
                except Exception as e:
                    errors.append(f"{match.id}: save players {e}")
                    logger.error("Save match player stats failed for %s: %s", match.id, e)
            if team_rows:
                try:
                    team_count = self._save_match_team_stats(match.id, team_rows)
                except Exception as e:
                    errors.append(f"{match.id}: save teams {e}")
                    logger.error("Save match team stats failed for %s: %s", match.id, e)

            if player_count > 0 or team_count > 0:
                saved_matches += 1
                saved_stats += player_count
                saved_team_rows += team_count
            else:
                errors.append(f"{match.id}: saved 0 rows")
            time_module.sleep(0.2)

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        status = "success" if saved_matches > 0 or found_count == 0 else "failed"

        self._save_crawl_log(
            crawl_type=crawl_type,
            crawl_category="match_player",
            league_id=league_id,
            league_name=league_name,
            found_count=found_count,
            saved_count=saved_stats + saved_team_rows,
            updated_count=saved_matches,
            status=status,
            started_at=start_time,
            finished_at=end_time,
            duration_ms=duration_ms,
            error_message="; ".join(errors[:5]) if errors else None,
            crawled_data=json.dumps(
                {
                    "espn_hits": espn_hits,
                    "five00_hits": five00_hits,
                    "fallback_hits": fallback_hits,
                    "miss_count": miss_count,
                    "saved_team_rows": saved_team_rows,
                    "prioritize_mappable": prioritize_mappable,
                    "prefer_older": prefer_older,
                },
                ensure_ascii=False,
            ),
        )

        result = {
            "league_id": league_id,
            "match_id": match_id,
            "found_count": found_count,
            "saved_matches": saved_matches,
            "saved_stats": saved_stats,
            "saved_team_rows": saved_team_rows,
            "espn_hits": espn_hits,
            "five00_hits": five00_hits,
            "fallback_hits": fallback_hits,
            "miss_count": miss_count,
            "status": status,
            "duration_ms": duration_ms,
        }
        logger.info(
            "Match player stats crawl: %s matches, players=%s teams=%s (ESPN %s, 500 %s, miss %s)",
            saved_matches, saved_stats, saved_team_rows, espn_hits, five00_hits, miss_count,
        )
        return result

    def _stats_prefer_older_flag(self) -> bool:
        """定时逐场补采交替：上次偏近则本次挖历史，反之亦然。"""
        db = SessionLocal()
        try:
            last = (
                db.query(CrawlLog)
                .filter(
                    CrawlLog.crawl_category == "match_player",
                    CrawlLog.league_name == "逐场球员统计",
                )
                .order_by(CrawlLog.id.desc())
                .first()
            )
            if not last or not last.crawled_data:
                return True
            payload = json.loads(last.crawled_data)
            return not bool(payload.get("prefer_older"))
        except Exception:
            return True
        finally:
            db.close()

    def _stats_limit_for_league(self, league_id: str, base_limit: int) -> int:
        extra = int(_crawler_cfg().get("stats_ucl_extra") or 80)
        if str(league_id or "").upper() == "UCL":
            return int(base_limit) + extra
        return int(base_limit)

    def _resolve_stats_limits(
        self,
        db,
        target_ids: List[str],
        *,
        explicit_limit: Optional[int] = None,
        budget_key: str = "budget_per_run",
    ) -> Tuple[Dict[str, int], Optional[dict]]:
        """SLA 开启且未指定固定 limit 时按缺口分配；否则沿用定额 + UCL extra。"""
        from services.crawler_sla import allocate_for_leagues, sla_enabled, sla_section

        cfg = _crawler_cfg()
        ids = [str(x) for x in (target_ids or []) if x]
        if explicit_limit is not None or not sla_enabled(cfg):
            base = int(explicit_limit if explicit_limit is not None else (cfg.get("stats_limit_per_league") or 150))
            return {lid: self._stats_limit_for_league(lid, base) for lid in ids}, None
        sec = sla_section(cfg)
        budget = sec.get(budget_key)
        if budget_key == "priority_budget":
            budget = int(budget if budget is not None else (sec.get("priority_budget") or 400))
        else:
            budget = int(budget if budget is not None else (sec.get("budget_per_run") or 900))
        try:
            plan = allocate_for_leagues(db, ids, budget=budget, cfg=cfg)
            limits = dict(plan.get("limits") or {})
            for lid in ids:
                limits.setdefault(lid, int(sec.get("min_limit") or 20))
            return limits, plan
        except Exception as e:
            logger.warning("SLA allocate failed, fallback to flat quota: %s", e)
            base = int(cfg.get("stats_limit_per_league") or 150)
            return {lid: self._stats_limit_for_league(lid, base) for lid in ids}, None

    def _should_run_train_after_crawl(self, stats_saved_matches: int) -> tuple:
        """P1：射门覆盖未明显增长且训练未滞后时跳过 train_all。"""
        min_delta = int(_crawler_cfg().get("train_min_stats_delta") or 50)
        saved = int(stats_saved_matches or 0)
        if saved >= min_delta:
            return True, f"本次新补射门 {saved} 场"
        try:
            from services.data_quality_service import data_quality_service
            db = SessionLocal()
            try:
                lag = (data_quality_service.summary(db) or {}).get("training_lag") or {}
            finally:
                db.close()
        except Exception as e:
            logger.debug("train-after-crawl lag check failed: %s", e)
            return True, "无法判断训练滞后，继续训练"
        if lag.get("last_train_samples") is None:
            return True, "尚无成功训练记录"
        if lag.get("is_stale"):
            return True, "训练已滞后于库内数据"
        return False, f"射门仅增 {saved} 且训练未滞后，跳过 train_all"

    def crawl_all_match_player_stats(
        self, crawl_type: str = "scheduled", limit_per_league: int = None
    ) -> List[Dict]:
        """批量补全重点+扩展联赛完赛场次的逐场球员统计（优先 ESPN 真实射门数据）。"""
        from services.real_team_crawler import get_stats_leagues, ESPN_LEAGUE_MAP

        cfg = _crawler_cfg()
        explicit_limit = limit_per_league
        prefer_older = self._stats_prefer_older_flag() if crawl_type == "scheduled" else False

        start_time = datetime.now()
        db = SessionLocal()
        try:
            target_ids = []
            for lid in get_stats_leagues():
                if lid in ESPN_LEAGUE_MAP and LeagueService.get_by_id(db, lid) and lid not in target_ids:
                    target_ids.append(lid)
            for lid in ESPN_LEAGUE_MAP:
                if lid not in target_ids and LeagueService.get_by_id(db, lid):
                    # 纯映射联赛（如 NOR/K1/WC）也纳入，但 SLA 配额靠 by_league
                    target_ids.append(lid)
            limits, sla_plan = self._resolve_stats_limits(
                db, target_ids, explicit_limit=explicit_limit, budget_key="budget_per_run"
            )
        finally:
            db.close()

        results = []
        for lid in target_ids:
            results.append(self.crawl_match_player_stats(
                league_id=lid,
                limit=int(limits.get(lid) or (explicit_limit or cfg.get("stats_limit_per_league") or 150)),
                crawl_type=crawl_type,
                prioritize_mappable=True,
                prefer_older=prefer_older,
            ))

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        total_found = sum(r.get("found_count", 0) for r in results)
        total_saved = sum(r.get("saved_stats", 0) for r in results)
        total_matches = sum(r.get("saved_matches", 0) for r in results)
        espn_hits = sum(r.get("espn_hits", 0) for r in results)
        log_payload = {
            "espn_hits": espn_hits,
            "leagues": target_ids,
            "prefer_older": prefer_older,
            "limits": limits,
            "ucl_extra": int(cfg.get("stats_ucl_extra") or 80),
        }
        if sla_plan:
            log_payload["sla"] = {
                "budget": sla_plan.get("budget"),
                "allocated": sla_plan.get("allocated"),
                "limits": sla_plan.get("limits"),
            }
        else:
            log_payload["limit_per_league"] = explicit_limit if explicit_limit is not None else int(
                cfg.get("stats_limit_per_league") or 150
            )

        self._save_crawl_log(
            crawl_type=crawl_type,
            crawl_category="match_player",
            league_id=None,
            league_name="逐场球员统计",
            found_count=total_found,
            saved_count=total_saved,
            updated_count=total_matches,
            status="success" if total_saved > 0 else "failed",
            crawled_data=json.dumps(log_payload, ensure_ascii=False),
            started_at=start_time,
            finished_at=end_time,
            duration_ms=duration_ms,
        )
        logger.info(
            "All match player stats crawl: %s matches, %s stat rows (espn_hits=%s prefer_older=%s sla=%s)",
            total_matches, total_saved, espn_hits, prefer_older, bool(sla_plan),
        )
        try:
            self.check_quality_alerts(crawl_type=crawl_type, full=False)
        except Exception as e:
            logger.warning("quality alerts after stats crawl failed: %s", e)
        return results

    def check_quality_alerts(self, crawl_type: str = "scheduled", full: bool = True) -> Dict:
        """数据质量告警（定时任务走 full=True；逐场批次后可 full=False 跳过映射扫描）。"""
        from services.quality_alert_service import evaluate_and_persist

        db = SessionLocal()
        try:
            return evaluate_and_persist(db, crawl_type=crawl_type, full=full)
        except Exception as e:
            logger.warning("quality alert check failed: %s", e)
            return {"status": "failed", "error": str(e), "created": 0}
        finally:
            db.close()

    def crawl_injuries(self, crawl_type: str = "scheduled") -> Dict:
        """采集重点联赛伤病并写入临场 injury 风控预警。"""
        from services.injury_crawler_service import injury_crawler_service
        return injury_crawler_service.crawl_priority_injuries(crawl_type=crawl_type)

    def backfill_priority_match_player_stats(
        self,
        limit_per_league: int = 250,
        crawl_type: str = "manual",
        prefer_older: bool = True,
    ) -> Dict:
        """重点联赛 ESPN 逐场统计缺场补采（队名可映射优先；默认挖历史缺口）。"""
        from services.real_team_crawler import get_stats_leagues, ESPN_LEAGUE_MAP

        start_time = datetime.now()
        results = []
        for lid in get_stats_leagues():
            if lid not in ESPN_LEAGUE_MAP:
                continue
            results.append(
                self.crawl_match_player_stats(
                    league_id=lid,
                    limit=self._stats_limit_for_league(lid, limit_per_league),
                    crawl_type=crawl_type,
                    prioritize_mappable=True,
                    prefer_older=prefer_older,
                )
            )
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        payload = {
            "status": "success" if any(r.get("saved_matches", 0) > 0 for r in results) else "failed",
            "results": results,
            "saved_matches": sum(r.get("saved_matches", 0) for r in results),
            "saved_stats": sum(r.get("saved_stats", 0) for r in results),
            "espn_hits": sum(r.get("espn_hits", 0) for r in results),
            "miss_count": sum(r.get("miss_count", 0) for r in results),
            "duration_ms": duration_ms,
            "limit_per_league": limit_per_league,
            "prefer_older": prefer_older,
        }
        self._save_crawl_log(
            crawl_type=crawl_type,
            crawl_category="match_player",
            league_id=None,
            league_name="重点联赛逐场补采",
            found_count=sum(r.get("found_count", 0) for r in results),
            saved_count=payload["saved_stats"],
            updated_count=payload["saved_matches"],
            status=payload["status"],
            crawled_data=json.dumps(payload, default=str, ensure_ascii=False),
            started_at=start_time,
            finished_at=end_time,
            duration_ms=duration_ms,
        )
        return payload

    def _save_players(self, raw_players: List[Dict], refresh_stats: bool = False) -> int:
        """保存球员阵容，过滤非法字段；同队同名则更新而不是重复插入。"""
        allowed = {
            'id', 'name', 'short_name', 'jersey_number', 'position', 'team_id',
            'nationality', 'birth_date', 'height', 'weight', 'foot',
            'market_value', 'goals', 'assists', 'appearances', 'yellow_cards', 'red_cards',
            'photo',
        }
        valid_pos = {'GK', 'CB', 'RB', 'LB', 'DM', 'CM', 'AM', 'RM', 'LM', 'RW', 'LW', 'ST'}
        db = SessionLocal()
        saved_count = 0
        try:
            for raw in raw_players:
                if not raw.get('id') or not raw.get('name') or not raw.get('team_id'):
                    continue
                if not TeamService.get_by_id(db, raw['team_id']):
                    continue
                payload = {k: v for k, v in raw.items() if k in allowed}
                pos = payload.get('position')
                payload['position'] = pos if pos in valid_pos else 'CM'
                payload['id'] = str(payload['id'])[:30]
                payload['short_name'] = (payload.get('short_name') or payload['name'])[:20]
                if payload.get('jersey_number') in ('', None, 0):
                    payload['jersey_number'] = None

                player = PlayerService.get_by_id(db, payload['id'])
                if not player:
                    player = db.query(Player).filter(
                        Player.team_id == payload['team_id'],
                        Player.name == payload['name']
                    ).first()
                try:
                    if player:
                        update_fields = {
                            'name': payload.get('name', player.name),
                            'short_name': payload.get('short_name', player.short_name),
                            'position': payload.get('position', player.position),
                            'team_id': payload.get('team_id', player.team_id),
                        }
                        if payload.get('jersey_number') and not player.jersey_number:
                            update_fields['jersey_number'] = payload['jersey_number']
                        if payload.get('height') and not player.height:
                            update_fields['height'] = payload['height']
                        if payload.get('weight') and not player.weight:
                            update_fields['weight'] = payload['weight']
                        for stat_key in ('goals', 'assists', 'appearances'):
                            if stat_key not in payload or payload[stat_key] is None:
                                continue
                            if refresh_stats or (payload.get(stat_key) and (getattr(player, stat_key) or 0) == 0):
                                update_fields[stat_key] = payload[stat_key]
                        if _is_media(payload.get('photo')) and not _is_media(getattr(player, 'photo', None)):
                            update_fields['photo'] = payload['photo']
                        PlayerService.update(db, player.id, update_fields)
                    else:
                        PlayerService.create(db, payload)
                        logger.info("Created player %s - %s (%s)", payload['id'], payload['name'], payload['team_id'])
                    saved_count += 1
                except Exception as e:
                    db.rollback()
                    logger.warning("Skip player %s: %s", payload.get('id'), e)
        finally:
            db.close()
        return saved_count

    # ===== 球队数据采集 =====

    def crawl_teams(self, league_id: str = None, crawl_type: str = 'manual', include_500: bool = False) -> Dict:
        """采集真实球队名单（ESPN + 500.com 积分榜，无模拟数据）"""
        start_time = datetime.now()
        if not getattr(self, '_team_crawler', None):
            return {'status': 'failed', 'error': 'Team crawler not loaded'}

        db = SessionLocal()
        try:
            if league_id:
                league = LeagueService.get_by_id(db, league_id)
                target_ids = [league.id] if league else []
                if not target_ids:
                    return {'status': 'failed', 'error': f'League {league_id} not found'}
            else:
                from services.real_team_crawler import ESPN_LEAGUE_MAP, FIVE00_TO_CANONICAL
                mapped_ids = list(ESPN_LEAGUE_MAP.keys())
                target_ids = [lid for lid in mapped_ids if LeagueService.get_by_id(db, lid)]
                if include_500:
                    skip = set(mapped_ids) | set(FIVE00_TO_CANONICAL.keys())
                    extras = [
                        lg.id for lg in LeagueService.get_active(db)
                        if lg.source_url and lg.id not in skip
                    ]
                    target_ids.extend(extras)
        finally:
            db.close()

        all_raw = []
        total_saved = 0
        total_updated = 0
        league_results = []
        try:
            from services.real_team_crawler import FIVE00_TO_CANONICAL
            for lid in target_ids:
                db = SessionLocal()
                try:
                    league = LeagueService.get_by_id(db, lid)
                    if not league:
                        continue
                    canonical_id = FIVE00_TO_CANONICAL.get(lid, lid)
                    save_league = LeagueService.get_by_id(db, canonical_id) or league
                    source_url = league.source_url
                    save_id = save_league.id
                    save_country = save_league.country or ''
                finally:
                    db.close()
                raw = self._team_crawler.crawl_league(canonical_id, source_url=source_url)
                saved, updated = self._save_teams(raw, save_id, save_country)
                all_raw.extend(raw)
                total_saved += saved
                total_updated += updated
                league_results.append({
                    'league_id': save_id,
                    'found_count': len(raw),
                    'saved_count': saved,
                    'updated_count': updated,
                })
                logger.info(
                    "Team crawl %s: found=%s saved=%s updated=%s",
                    save_id, len(raw), saved, updated
                )

            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='team',
                league_id=league_id,
                league_name=league_id or '规范联赛球队名单',
                found_count=len(all_raw),
                saved_count=total_saved,
                updated_count=total_updated,
                status='success',
                crawled_data=json.dumps(
                    [{'id': t.get('id'), 'name': t.get('name'), 'league_id': t.get('league_id')} for t in all_raw],
                    ensure_ascii=False
                ),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )
            return {
                'status': 'success',
                'found_count': len(all_raw),
                'saved_count': total_saved,
                'updated_count': total_updated,
                'leagues': league_results,
                'duration_ms': duration_ms,
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            logger.error("Team crawl failed: %s", e)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='team',
                league_id=league_id,
                league_name=league_id or '规范联赛球队名单',
                found_count=0,
                saved_count=0,
                status='failed',
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )
            return {'status': 'failed', 'error': str(e), 'duration_ms': duration_ms}

    def crawl_all_teams(self, crawl_type: str = 'scheduled') -> Dict:
        return self.crawl_teams(league_id=None, crawl_type=crawl_type, include_500=False)

    def _save_teams(self, raw_teams: List[Dict], league_id: str, country: str = '') -> Tuple[int, int]:
        db = SessionLocal()
        saved_count = 0
        updated_count = 0
        allowed = {
            'id', 'name', 'short_name', 'logo', 'league_id', 'country',
            'elo_rating', 'attack_strength', 'defense_strength', 'home_ground', 'founded_year'
        }
        # 英格兰升降级共用队 ID（如 SOU/WOL）；允许 EPL↔ECH 互迁，其它联赛仍禁止撞 ID 覆盖
        english_pyramid = {"EPL", "ECH"}
        try:
            for item in raw_teams:
                payload = {k: v for k, v in item.items() if k in allowed}
                payload['league_id'] = league_id
                if not payload.get('country'):
                    payload['country'] = country or ''
                existing = TeamService.get_by_id(db, payload['id'])
                if existing:
                    # 禁止跨联赛覆盖同 ID 球队（如 MLS Atlanta 与 Serie A Atalanta 撞 ATL）
                    if existing.league_id and existing.league_id != league_id:
                        can_reassign = (
                            existing.league_id in english_pyramid
                            and league_id in english_pyramid
                        )
                        if not can_reassign:
                            continue
                    update_fields = {
                        'name': payload.get('name', existing.name),
                        'short_name': payload.get('short_name', existing.short_name),
                    }
                    if payload.get('country') and not existing.country:
                        update_fields['country'] = payload['country']
                    if not existing.home_ground and payload.get('home_ground'):
                        update_fields['home_ground'] = payload['home_ground']
                    if (not existing.league_id) or (
                        existing.league_id != league_id
                        and existing.league_id in english_pyramid
                        and league_id in english_pyramid
                    ):
                        update_fields['league_id'] = league_id
                    if _is_media(payload.get('logo')) and not _is_media(existing.logo):
                        update_fields['logo'] = payload['logo']
                    TeamService.update(db, payload['id'], update_fields)
                    updated_count += 1
                else:
                    TeamService.create(db, payload)
                    saved_count += 1
                    logger.info("Created team %s - %s", payload['id'], payload.get('name'))
        finally:
            db.close()
        return saved_count, updated_count

    # ===== 联赛数据采集 =====

    def crawl_leagues(self, crawl_type: str = 'manual') -> Dict:
        """采集 liansai.500.com 联赛数据"""
        start_time = datetime.now()
        logger.info(f"Starting league crawl (type: {crawl_type})")

        if not self._league_crawler:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            logger.error("League crawler not loaded")
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='league',
                league_id=None,
                league_name='League Crawl',
                found_count=0,
                saved_count=0,
                status='failed',
                error_message='League crawler not loaded',
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )
            return {'status': 'failed', 'error': 'League crawler not loaded'}

        try:
            raw_leagues = self._league_crawler.crawl()
            saved_count, updated_count = self._save_leagues(raw_leagues)
            from services.league_parent import backfill_league_parents
            db_bf = SessionLocal()
            try:
                backfill_count = backfill_league_parents(db_bf)
                if backfill_count:
                    logger.info("League parent backfill: %s updated", backfill_count)
            finally:
                db_bf.close()
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            logger.info(f"League crawl completed: {len(raw_leagues)} found, {saved_count} saved, {updated_count} updated")

            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='league',
                league_id=None,
                league_name='League Crawl',
                found_count=len(raw_leagues),
                saved_count=saved_count,
                updated_count=updated_count,
                status='success',
                crawled_data=json.dumps(raw_leagues, default=str, ensure_ascii=False),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )

            return {
                'found_count': len(raw_leagues),
                'saved_count': saved_count,
                'updated_count': updated_count,
                'status': 'success',
                'duration_ms': duration_ms
            }
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            logger.error(f"League crawl failed: {str(e)}")

            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category='league',
                league_id=None,
                league_name='League Crawl',
                found_count=0,
                saved_count=0,
                status='failed',
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms
            )

            return {
                'found_count': 0,
                'saved_count': 0,
                'updated_count': 0,
                'status': 'failed',
                'error': str(e),
                'duration_ms': duration_ms
            }

    def enrich_league(
        self,
        league_id: str,
        include_history: bool = False,
        seasons_back: int = 0,
        crawl_type: str = 'manual',
    ) -> Dict:
        """为单个联赛补齐真实球队名单 + 赛程/赛果 + 阵容 + 积分榜 + 射手榜 + 图片。"""
        from services.real_team_crawler import FIVE00_TO_CANONICAL, CANONICAL_FIVE00_URL, get_priority_leagues

        team_result = self.crawl_teams(league_id=league_id, crawl_type=crawl_type)
        db = SessionLocal()
        try:
            league = LeagueService.get_by_id(db, league_id)
            source_url = league.source_url if league else None
            canonical = FIVE00_TO_CANONICAL.get(league_id, league_id)
            if not source_url:
                source_url = CANONICAL_FIVE00_URL.get(canonical)
                if source_url and league and not league.source_url:
                    LeagueService.update(db, league.id, {'source_url': source_url})
        finally:
            db.close()

        back = seasons_back
        if include_history and back <= 0:
            back = 2 if canonical in get_priority_leagues() else 1

        match_result = {'found_count': 0, 'saved_count': 0, 'updated_count': 0, 'status': 'skipped'}
        if getattr(self, '_team_crawler', None):
            raw = self._team_crawler.crawl_fixtures(
                league_id,
                source_url=source_url,
                include_history=include_history,
                seasons_back=back,
            )
            saved, updated = self._save_matches(raw)
            match_result = {
                'found_count': len(raw),
                'saved_count': saved,
                'updated_count': updated,
                'status': 'success',
            }
        player_result = {'found_count': 0, 'saved_count': 0, 'status': 'skipped'}
        if getattr(self, '_team_crawler', None):
            squad = self._team_crawler.crawl_squads(
                league_id, source_url=source_url
            )
            saved_p = self._save_players(squad)
            player_result = {
                'found_count': len(squad),
                'saved_count': saved_p,
                'status': 'success',
            }
        standings_result = self.crawl_standings(league_id=league_id, crawl_type=crawl_type)
        scorers_result = self.crawl_scorers(league_id=league_id, crawl_type=crawl_type)
        image_result = {'status': 'skipped'}
        try:
            image_result = self.crawl_images(league_id=league_id, include_players=False)
        except Exception as e:
            logger.warning("Image crawl failed for %s: %s", league_id, e)
            image_result = {'status': 'failed', 'error': str(e)}
        return {
            'status': 'success',
            'league_id': league_id,
            'teams': team_result,
            'matches': match_result,
            'players': player_result,
            'standings': standings_result,
            'scorers': scorers_result,
            'images': image_result,
        }

    def crawl_standings(self, league_id: str = None, crawl_type: str = 'manual') -> Dict:
        """采集积分榜（ESPN 优先，500.com 兜底）。"""
        from services.real_team_crawler import get_priority_leagues, FIVE00_TO_CANONICAL, CANONICAL_FIVE00_URL

        start_time = datetime.now()
        target_ids = [league_id] if league_id else list(get_priority_leagues())
        results = []
        total_saved = 0
        for lid in target_ids:
            if not lid:
                continue
            canonical = FIVE00_TO_CANONICAL.get(lid, lid)
            db = SessionLocal()
            try:
                league = LeagueService.get_by_id(db, canonical)
                source_url = (league.source_url if league else None) or CANONICAL_FIVE00_URL.get(canonical)
                league_name = league.name if league else canonical
            finally:
                db.close()
            if not getattr(self, '_team_crawler', None):
                results.append({'league_id': canonical, 'status': 'failed', 'error': 'team crawler unavailable'})
                continue
            try:
                rows, season = self._team_crawler.crawl_standings(canonical, source_url=source_url)
                saved = self._save_standings(rows, season)
                total_saved += saved
                results.append({
                    'league_id': canonical,
                    'season': season,
                    'found_count': len(rows),
                    'saved_count': saved,
                    'status': 'success' if saved or not rows else 'empty',
                })
            except Exception as e:
                logger.error("Standings crawl failed for %s: %s", canonical, e)
                results.append({'league_id': canonical, 'status': 'failed', 'error': str(e)})

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        self._save_crawl_log(
            crawl_type=crawl_type,
            crawl_category='standings',
            league_id=league_id or 'PRIORITY',
            league_name='积分榜采集',
            found_count=sum(int(r.get('found_count') or 0) for r in results),
            saved_count=total_saved,
            updated_count=0,
            status='success' if any(r.get('status') == 'success' for r in results) else 'failed',
            crawled_data=json.dumps(results, default=str, ensure_ascii=False),
            started_at=start_time,
            finished_at=end_time,
            duration_ms=duration_ms,
        )
        if league_id:
            return results[0] if results else {'status': 'failed', 'error': 'no result'}
        return {'status': 'success', 'results': results, 'duration_ms': duration_ms, 'saved_count': total_saved}

    def crawl_scorers(self, league_id: str = None, crawl_type: str = 'manual') -> Dict:
        """采集射手榜（ESPN statistics 优先）。"""
        from services.real_team_crawler import get_priority_leagues, FIVE00_TO_CANONICAL, CANONICAL_FIVE00_URL

        start_time = datetime.now()
        target_ids = [league_id] if league_id else list(get_priority_leagues())
        results = []
        total_saved = 0
        for lid in target_ids:
            if not lid:
                continue
            canonical = FIVE00_TO_CANONICAL.get(lid, lid)
            db = SessionLocal()
            try:
                league = LeagueService.get_by_id(db, canonical)
                source_url = (league.source_url if league else None) or CANONICAL_FIVE00_URL.get(canonical)
            finally:
                db.close()
            if not getattr(self, '_team_crawler', None):
                results.append({'league_id': canonical, 'status': 'failed', 'error': 'team crawler unavailable'})
                continue
            try:
                rows, season = self._team_crawler.crawl_top_scorers(canonical, source_url=source_url)
                saved = self._save_scorers(rows, season)
                total_saved += saved
                results.append({
                    'league_id': canonical,
                    'season': season,
                    'found_count': len(rows),
                    'saved_count': saved,
                    'status': 'success' if saved or not rows else 'empty',
                })
            except Exception as e:
                logger.error("Scorers crawl failed for %s: %s", canonical, e)
                results.append({'league_id': canonical, 'status': 'failed', 'error': str(e)})

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        self._save_crawl_log(
            crawl_type=crawl_type,
            crawl_category='scorers',
            league_id=league_id or 'PRIORITY',
            league_name='射手榜采集',
            found_count=sum(int(r.get('found_count') or 0) for r in results),
            saved_count=total_saved,
            updated_count=0,
            status='success' if any(r.get('status') == 'success' for r in results) else 'failed',
            crawled_data=json.dumps(results, default=str, ensure_ascii=False),
            started_at=start_time,
            finished_at=end_time,
            duration_ms=duration_ms,
        )
        if league_id:
            return results[0] if results else {'status': 'failed', 'error': 'no result'}
        return {'status': 'success', 'results': results, 'duration_ms': duration_ms, 'saved_count': total_saved}

    def crawl_environment(
        self,
        limit: int = None,
        only_missing: bool = True,
        upcoming_only: bool = False,
        finished_only: bool = False,
        league_id: str = None,
        crawl_type: str = "manual",
    ) -> Dict:
        """Open-Meteo 补全赛事天气 / 气温 / 草坪，并生成环境类风控预警。"""
        from services.environment_service import environment_service

        if limit is None:
            limit = int(_crawler_cfg().get("env_limit") or 1000)

        start_time = datetime.now()
        db = SessionLocal()
        try:
            result = environment_service.backfill(
                db,
                limit=limit,
                only_missing=only_missing,
                upcoming_only=upcoming_only,
                finished_only=finished_only,
                league_id=league_id,
                create_risk_alerts=True,
                prefer_priority=True,
            )
            status = "success"
            error_message = None
        except Exception as e:
            logger.error("Environment crawl failed: %s", e)
            result = {"scanned": 0, "updated": 0, "venue_only": 0, "risk_alerts": 0, "coverage": {}}
            status = "failed"
            error_message = str(e)
        finally:
            db.close()

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        self._save_crawl_log(
            crawl_type=crawl_type,
            crawl_category="environment",
            league_id=league_id or "ALL",
            league_name="气象环境补全",
            found_count=int(result.get("scanned") or 0),
            saved_count=int(result.get("updated") or 0),
            updated_count=int(result.get("venue_only") or 0),
            status=status,
            error_message=error_message,
            crawled_data=json.dumps(result, default=str, ensure_ascii=False),
            started_at=start_time,
            finished_at=end_time,
            duration_ms=duration_ms,
        )
        return {"status": status, "duration_ms": duration_ms, **result}

    def _remap_team_id(
        self,
        db,
        league_id: str,
        team_id: Optional[str] = None,
        team_name: Optional[str] = None,
        team_short: Optional[str] = None,
        allow_global: bool = False,
    ) -> Optional[str]:
        """将 ESPN/500 队名或缩写映射到本库球队 ID（按联赛优先）。"""
        from db.models import Team
        from services.real_team_crawler import TEAM_ALIASES, ESPN_MATCH_ALIASES

        teams = db.query(Team).filter(Team.league_id == league_id).all()
        by_id = {t.id: t for t in teams}
        if team_id and team_id in by_id:
            return team_id

        # ESPN 缩写 → 本库 ID：利用 ESPN_MATCH_ALIASES 的反向候选
        espn_to_aliases: Dict[str, set] = {}
        for alias, espn_code in ESPN_MATCH_ALIASES.items():
            code = (espn_code or "").upper()
            if code:
                espn_to_aliases.setdefault(code, set()).add(alias)

        if team_id:
            for alias in espn_to_aliases.get(str(team_id).upper(), set()):
                if alias.isascii() and 2 <= len(alias) <= 5:
                    cand = alias.upper()
                    if cand in by_id:
                        return cand
                tid = TEAM_ALIASES.get(alias) or TEAM_ALIASES.get(alias.lower())
                if tid and tid in by_id:
                    return tid
                for t in teams:
                    if t.name and (alias in t.name or t.name in alias):
                        return t.id

        name_index: Dict[str, str] = {}
        for t in teams:
            for key in (t.id, t.name, t.short_name):
                if not key:
                    continue
                k = str(key).strip().lower()
                name_index[k] = t.id
                name_index[re.sub(r"[\s\-\.]", "", k)] = t.id
            for alias, tid in TEAM_ALIASES.items():
                if tid == t.id:
                    name_index[alias] = t.id

        crawler = self._team_crawler
        for candidate in (team_name, team_short, team_id):
            if not candidate:
                continue
            key = str(candidate).strip().lower()
            compact = re.sub(r"[\s\-\.]", "", key)
            if key in name_index:
                return name_index[key]
            if compact in name_index:
                return name_index[compact]
            alias = crawler._alias_lookup(str(candidate))
            if alias and alias in by_id:
                return alias
            if alias and alias.lower() in name_index:
                return name_index[alias.lower()]

        for t in teams:
            for cand in (team_name, team_short):
                if not cand or not t.name:
                    continue
                if cand.lower() in t.name.lower() or t.name.lower() in cand.lower():
                    return t.id

        if allow_global and team_id and TeamService.get_by_id(db, team_id):
            return team_id
        if allow_global:
            for candidate in (team_name, team_short, team_id):
                if not candidate:
                    continue
                alias = crawler._alias_lookup(str(candidate))
                if alias and TeamService.get_by_id(db, alias):
                    return alias
        return None

    def _save_standings(self, rows: List[Dict], season: str) -> int:
        if not rows:
            return 0
        db = SessionLocal()
        try:
            league_id = rows[0]['league_id']
            cleaned = []
            seen_teams = set()
            for row in rows:
                tid = self._remap_team_id(
                    db,
                    league_id,
                    team_id=row.get('team_id'),
                    team_name=row.get('team_name'),
                    team_short=row.get('team_short'),
                    allow_global=(league_id == 'UCL'),
                )
                if not tid:
                    logger.debug(
                        "Skip standing row unmatched team_id=%s name=%s league=%s",
                        row.get('team_id'), row.get('team_name'), league_id,
                    )
                    continue
                if tid in seen_teams:
                    logger.debug("Skip duplicate standing remap team_id=%s league=%s", tid, league_id)
                    continue
                seen_teams.add(tid)
                cleaned.append({
                    'league_id': league_id,
                    'team_id': tid,
                    'season': season or row.get('season') or '',
                    'rank': int(row.get('rank') or 0),
                    'played': int(row.get('played') or 0),
                    'won': int(row.get('won') or 0),
                    'drawn': int(row.get('drawn') or 0),
                    'lost': int(row.get('lost') or 0),
                    'goals_for': int(row.get('goals_for') or 0),
                    'goals_against': int(row.get('goals_against') or 0),
                    'goal_diff': int(row.get('goal_diff') or row.get('goal_difference') or 0),
                    'points': int(row.get('points') or 0),
                    'update_date': row.get('update_date') or date.today(),
                })
            if not cleaned:
                return 0
            return StandingService.replace_for_league_season(
                db, league_id, cleaned[0]['season'], cleaned
            )
        finally:
            db.close()

    def _save_scorers(self, rows: List[Dict], season: str) -> int:
        if not rows:
            return 0
        db = SessionLocal()
        try:
            league_id = rows[0]['league_id']
            cleaned = []
            for row in rows:
                tid = self._remap_team_id(
                    db,
                    league_id,
                    team_id=row.get('team_id'),
                    team_name=row.get('team_name'),
                    team_short=row.get('team_short'),
                    allow_global=True,
                )
                name = (row.get('player_name') or '').strip()
                if not name:
                    continue
                cleaned.append({
                    'player_name': name[:100],
                    'team_id': tid,
                    'league_id': league_id,
                    'season': season or row.get('season') or '',
                    'goals': int(row.get('goals') or 0),
                    'assists': int(row.get('assists') or 0),
                    'games_played': int(row.get('games_played') or 0),
                    'rank': int(row.get('rank') or 0),
                    'update_date': row.get('update_date') or date.today(),
                })
            if not cleaned:
                return 0
            return ScorerService.replace_for_league_season(
                db, league_id, cleaned[0]['season'], cleaned
            )
        finally:
            db.close()

    def enrich_priority_leagues(
        self,
        include_history: bool = True,
        seasons_back: int = 2,
        crawl_type: str = 'manual',
    ) -> List[Dict]:
        """批量补齐五大联赛 + 欧冠的全部真实数据。"""
        from services.real_team_crawler import get_priority_leagues
        results = []
        for lid in get_priority_leagues():
            results.append(self.enrich_league(
                lid,
                include_history=include_history,
                seasons_back=seasons_back,
                crawl_type=crawl_type,
            ))
        return results

    def crawl_priority_and_train(self, crawl_type: str = 'scheduled') -> Dict:
        """重点联赛赛程/赛果增量采集后自动训练（供定时任务调用）。

        仅拉当前赛季赛程（include_history=False 的 crawl_league），
        用比分回写完赛场次，再触发 train_all 更新 ELO/泊松/分联赛融合权重。

        若对应专项定时任务已启用，则跳过该步骤，避免与独立调度双跑：
        match_player_stats_crawl / standings_crawl / scorers_crawl / environment_crawl。
        """
        from services.real_team_crawler import get_priority_leagues
        from services.training_service import training_service
        from services.scheduler_service import scheduler

        start_time = datetime.now()
        logger.info("Starting priority fixture crawl + train (type: %s)", crawl_type)

        skip_stats = scheduler.is_task_enabled("match_player_stats_crawl")
        skip_standings = scheduler.is_task_enabled("standings_crawl")
        skip_scorers = scheduler.is_task_enabled("scorers_crawl")
        skip_env = scheduler.is_task_enabled("environment_crawl")
        if any((skip_stats, skip_standings, skip_scorers, skip_env)):
            logger.info(
                "priority_train dedupe: skip stats=%s standings=%s scorers=%s env=%s",
                skip_stats, skip_standings, skip_scorers, skip_env,
            )

        crawl_results = []
        for lid in get_priority_leagues():
            try:
                crawl_results.append(self.crawl_league(lid, days_ahead=7, crawl_type=crawl_type))
            except Exception as e:
                logger.error("Priority crawl failed for %s: %s", lid, e)
                crawl_results.append({
                    "league_id": lid,
                    "found_count": 0,
                    "saved_count": 0,
                    "updated_count": 0,
                    "status": "failed",
                    "error": str(e),
                })

        stale_removed = 0
        try:
            stale_removed = self.cleanup_stale_upcoming()
        except Exception as e:
            logger.warning("cleanup_stale_upcoming failed: %s", e)

        total_found = sum(int(r.get("found_count") or 0) for r in crawl_results)
        total_saved = sum(int(r.get("saved_count") or 0) for r in crawl_results)
        total_updated = sum(int(r.get("updated_count") or 0) for r in crawl_results)
        crawl_ok = all(r.get("status") == "success" for r in crawl_results) if crawl_results else False

        # 增量补逐场球员统计：SLA 配额按联赛拆成历史+近期；关闭 SLA 时沿用定额+UCL extra
        player_stats_result = []
        half = int(_crawler_cfg().get("priority_stats_limit") or 50)
        sla_plan = None
        if skip_stats:
            logger.info("priority_train: skip match_player_stats (match_player_stats_crawl enabled)")
        else:
            try:
                from services.crawler_sla import sla_enabled

                db = SessionLocal()
                try:
                    if sla_enabled():
                        limits, sla_plan = self._resolve_stats_limits(
                            db,
                            list(get_priority_leagues()),
                            explicit_limit=None,
                            budget_key="priority_budget",
                        )
                    else:
                        limits = {lid: self._stats_limit_for_league(lid, half) for lid in get_priority_leagues()}
                finally:
                    db.close()
                for lid in get_priority_leagues():
                    total = int(limits.get(lid) or half)
                    if sla_plan:
                        older = max(10, (total + 1) // 2)
                        recent = max(10, total - older)
                    else:
                        older = total
                        recent = half
                    player_stats_result.append(
                        self.crawl_match_player_stats(
                            league_id=lid,
                            limit=older,
                            crawl_type=crawl_type,
                            prioritize_mappable=True,
                            prefer_older=True,
                        )
                    )
                    player_stats_result.append(
                        self.crawl_match_player_stats(
                            league_id=lid,
                            limit=recent,
                            crawl_type=crawl_type,
                            prioritize_mappable=True,
                            prefer_older=False,
                        )
                    )
            except Exception as e:
                logger.warning("priority match_player_stats crawl failed: %s", e)

        # 积分榜 / 射手榜：交叉先验与首页展示
        standings_result = {"saved_count": 0, "status": "skipped"}
        scorers_result = {"saved_count": 0, "status": "skipped"}
        if skip_standings:
            standings_result = {"saved_count": 0, "status": "skipped", "reason": "standings_crawl enabled"}
        else:
            try:
                standings_result = self.crawl_standings(crawl_type=crawl_type)
            except Exception as e:
                logger.warning("priority standings crawl failed: %s", e)
                standings_result = {"status": "failed", "error": str(e)}
        if skip_scorers:
            scorers_result = {"saved_count": 0, "status": "skipped", "reason": "scorers_crawl enabled"}
        else:
            try:
                scorers_result = self.crawl_scorers(crawl_type=crawl_type)
            except Exception as e:
                logger.warning("priority scorers crawl failed: %s", e)
                scorers_result = {"status": "failed", "error": str(e)}

        # 补全天气 / 气温 / 草坪，供临场修正与风控（优先重点联赛+未赛）
        env_result = {"scanned": 0, "updated": 0, "risk_alerts": 0, "status": "ok"}
        if skip_env:
            env_result = {"scanned": 0, "updated": 0, "risk_alerts": 0, "status": "skipped", "reason": "environment_crawl enabled"}
        else:
            try:
                env_result = self.crawl_environment(
                    limit=int(_crawler_cfg().get("env_limit") or 1000),
                    only_missing=True,
                    upcoming_only=False,
                    crawl_type=crawl_type,
                )
            except Exception as e:
                logger.warning("environment backfill failed: %s", e)

        stats_saved = sum(int(r.get("saved_matches") or 0) for r in player_stats_result)
        should_train, train_reason = self._should_run_train_after_crawl(stats_saved)
        if skip_stats and not should_train:
            train_reason = f"逐场统计由 match_player_stats_crawl 负责；{train_reason}"
        if not should_train:
            train_result = {
                "status": "skipped",
                "message": train_reason,
            }
        else:
            try:
                train_result = training_service.run_train_or_skip()
                if isinstance(train_result, dict):
                    train_result["skip_reason"] = train_reason
            except Exception as e:
                logger.error("Auto train after priority crawl failed: %s", e)
                train_result = {"status": "failed", "message": str(e)}

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        train_status = (train_result or {}).get("status")
        overall = "success" if crawl_ok and train_status in ("success", "skipped") else (
            "success" if train_status == "success" else "failed"
        )

        summary = {
            "leagues": [r.get("league_id") for r in crawl_results],
            "crawl_found": total_found,
            "crawl_saved": total_saved,
            "crawl_updated": total_updated,
            "stale_removed": stale_removed,
            "player_stats_matches": sum(int(r.get("saved_matches") or 0) for r in player_stats_result),
            "player_stats_rows": sum(int(r.get("saved_stats") or 0) for r in player_stats_result),
            "standings_saved": standings_result.get("saved_count"),
            "standings_status": standings_result.get("status"),
            "scorers_saved": scorers_result.get("saved_count"),
            "scorers_status": scorers_result.get("status"),
            "env_scanned": env_result.get("scanned"),
            "env_updated": env_result.get("updated"),
            "env_risk_alerts": env_result.get("risk_alerts"),
            "env_coverage": env_result.get("coverage"),
            "dedupe_skipped": {
                "match_player_stats": skip_stats,
                "standings": skip_standings,
                "scorers": skip_scorers,
                "environment": skip_env,
            },
            "train_status": train_status,
            "train_reason": (train_result or {}).get("skip_reason") or (train_result or {}).get("message"),
            "model_version": (train_result or {}).get("model_version"),
            "prediction_refresh": (train_result or {}).get("prediction_refresh"),
            "validation_accuracy": ((train_result or {}).get("results") or {})
                .get("ensemble", {})
                .get("validation_accuracy"),
            "leagues_optimized": ((train_result or {}).get("results") or {})
                .get("ensemble", {})
                .get("leagues_optimized"),
        }
        if sla_plan:
            summary["sla"] = {
                "budget": sla_plan.get("budget"),
                "allocated": sla_plan.get("allocated"),
                "limits": sla_plan.get("limits"),
            }
        self._save_crawl_log(
            crawl_type=crawl_type,
            crawl_category="train",
            league_id=None,
            league_name="重点联赛增量采集+训练",
            found_count=total_found,
            saved_count=total_saved,
            updated_count=total_updated,
            status=overall,
            crawled_data=json.dumps(summary, default=str, ensure_ascii=False),
            started_at=start_time,
            finished_at=end_time,
            duration_ms=duration_ms,
            error_message=(train_result or {}).get("message") if train_status == "failed" else None,
        )

        logger.info(
            "Priority crawl+train done: found=%s saved=%s updated=%s train=%s version=%s (%sms)",
            total_found, total_saved, total_updated, train_status,
            summary.get("model_version"), duration_ms,
        )
        try:
            self.check_quality_alerts(crawl_type=crawl_type, full=False)
        except Exception as e:
            logger.warning("quality alerts after priority train failed: %s", e)
        return {
            "status": overall,
            "crawl_results": crawl_results,
            "stale_removed": stale_removed,
            "player_stats": player_stats_result,
            "train": train_result,
            "summary": summary,
            "duration_ms": duration_ms,
        }

    def _save_leagues(self, raw_leagues: List[Dict]) -> tuple:
        """保存联赛数据。已知的 500.com 联赛归并到规范 ID，避免英超同时出现 EPL 与 LS19906。"""
        from services.real_team_crawler import FIVE00_TO_CANONICAL
        db = SessionLocal()
        saved_count = 0
        updated_count = 0
        try:
            for league_data in raw_leagues:
                src_id = league_data.get('id')
                canonical_id = FIVE00_TO_CANONICAL.get(src_id)
                if canonical_id:
                    canonical = LeagueService.get_by_id(db, canonical_id)
                    if canonical:
                        update_fields = {
                            'source_url': league_data.get('source_url') or canonical.source_url,
                        }
                        if not canonical.country and league_data.get('country'):
                            update_fields['country'] = league_data['country']
                        if not canonical.flag and league_data.get('flag'):
                            update_fields['flag'] = league_data['flag']
                        if not canonical.category and league_data.get('category'):
                            update_fields['category'] = league_data['category']
                        LeagueService.update(db, canonical_id, update_fields)
                        dup = LeagueService.get_by_id(db, src_id)
                        if dup and src_id != canonical_id:
                            dup.is_active = False
                            db.commit()
                        updated_count += 1
                        continue

                existing = LeagueService.get_by_id(db, src_id)
                if existing:
                    update_fields = {
                        'name': league_data.get('name', existing.name),
                        'icon': league_data.get('icon', existing.icon),
                        'region': league_data.get('region', existing.region),
                        'category': league_data.get('category', existing.category),
                        'country': league_data.get('country', existing.country),
                        'flag': league_data.get('flag', existing.flag),
                        'level': league_data.get('level', existing.level),
                        'avg_goals': league_data.get('avg_goals', existing.avg_goals),
                        'source_url': league_data.get('source_url', existing.source_url),
                    }
                    inferred_parent = league_data.get('parent_id')
                    if not inferred_parent and (league_data.get('level') or existing.level or 1) > 1:
                        from services.league_parent import resolve_parent_id
                        inferred_parent = resolve_parent_id(
                            db,
                            update_fields['name'],
                            update_fields.get('country'),
                            update_fields.get('level', 1),
                            update_fields.get('category', 'international'),
                            src_id,
                        )
                    if inferred_parent and not existing.parent_id:
                        update_fields['parent_id'] = inferred_parent
                    LeagueService.update(db, src_id, update_fields)
                    updated_count += 1
                else:
                    LeagueService.create(db, league_data)
                    saved_count += 1
                    logger.info(f"Created new league: {src_id} - {league_data['name']}")
        finally:
            db.close()
        return saved_count, updated_count

    def crawl_images(self, league_id: str = None, include_players: bool = True) -> Dict:
        """采集联赛徽标、球队队徽，并补齐球员头像。

        球队优先走 ESPN+500 合并名单（含 remote_logo），避免只采 500 导致
        ASM/ATL 等规范 ID 队徽永远停在 emoji。
        """
        from datetime import datetime
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from services.media_crawler import (
            MediaCrawler, is_media_path, extract_source_pid, extract_espn_id,
        )
        from services.real_team_crawler import (
            ESPN_LEAGUE_MAP, CANONICAL_FIVE00_URL, FIVE00_TO_CANONICAL, get_priority_leagues,
        )

        start_time = datetime.now()
        media = getattr(getattr(self, '_team_crawler', None), 'media', None) or MediaCrawler()
        stats = {
            'leagues': 0,
            'teams': 0,
            'players': 0,
            'players_pending': 0,
            'players_total': 0,
            'status': 'success',
        }
        db = SessionLocal()
        roster_index = {}
        team_src_map = {}
        try:
            target_ids = []
            if league_id:
                target_ids = [FIVE00_TO_CANONICAL.get(league_id, league_id)]
            else:
                # 重点联赛优先，再补 ESPN 映射联赛
                for lid in list(get_priority_leagues()) + list(ESPN_LEAGUE_MAP.keys()) + list(CANONICAL_FIVE00_URL.keys()):
                    if lid not in target_ids:
                        target_ids.append(lid)

            for lid in target_ids:
                league = LeagueService.get_by_id(db, lid)
                if not league:
                    continue
                logo = media.fetch_league_logo(lid)
                if logo and not is_media_path(league.logo):
                    LeagueService.update(db, lid, {'logo': logo})
                    stats['leagues'] += 1
                    league.logo = logo

                if not getattr(self, '_team_crawler', None):
                    continue

                # ESPN + 500 合并，才能给规范短 ID（ASM/ATL…）挂上 ESPN 队徽
                try:
                    raw_teams = self._team_crawler.crawl_league(lid)
                except Exception as e:
                    logger.warning("Team logo crawl failed for %s: %s", lid, e)
                    raw_teams = []

                if raw_teams:
                    saved, updated = self._save_teams(
                        raw_teams, lid, country=league.country or '',
                    )
                    stats['teams'] += saved + updated
                    for t in raw_teams:
                        if t.get('id') and t.get('source_team_id'):
                            team_src_map[t['id']] = str(t['source_team_id'])

                # 库内仍缺队徽：国家队用国旗，其余用 ESPN/500 再试
                missing_teams = (
                    db.query(Team)
                    .filter(Team.league_id == lid)
                    .all()
                )
                team_updates = 0
                by_id = {t.get('id'): t for t in (raw_teams or []) if t.get('id')}
                for team in missing_teams:
                    if is_media_path(team.logo):
                        continue
                    raw = by_id.get(team.id) or {}
                    logo = media.fetch_team_logo(
                        team.id,
                        source_team_id=raw.get('source_team_id') or team_src_map.get(team.id),
                        remote_url=raw.get('remote_logo'),
                        espn_id=raw.get('espn_id'),
                        country_code=raw.get('country_code'),
                        team_name=team.name or team.short_name,
                    )
                    if logo:
                        team.logo = logo
                        team_updates += 1
                if team_updates:
                    db.commit()
                    stats['teams'] += team_updates

                if include_players:
                    source_url = league.source_url or CANONICAL_FIVE00_URL.get(lid)
                    if source_url:
                        try:
                            raw_players = self._team_crawler.crawl_squads(
                                lid, source_url=source_url, download_photos=True,
                            )
                        except Exception as e:
                            logger.warning("Squad photo crawl failed for %s: %s", lid, e)
                            raw_players = []
                        for p in raw_players:
                            key = (p.get('team_id'), p.get('name'))
                            src = p.get('id', '')
                            if src.startswith('P') and not src.startswith('PE') and key[0] and key[1]:
                                pid = extract_source_pid(src)
                                if pid:
                                    roster_index[key] = pid
                        photo_updates = len([p for p in raw_players if p.get('photo')])
                        self._save_players(raw_players)
                        stats['players'] += photo_updates

            if include_players:
                query = db.query(Player).join(Team)
                if league_id:
                    lid = FIVE00_TO_CANONICAL.get(league_id, league_id)
                    query = query.filter(Team.league_id == lid)
                else:
                    query = query.filter(Team.league_id.in_(target_ids))
                players = query.all()
                stats['players_total'] = len(players)
                pending = [p for p in players if not is_media_path(getattr(p, 'photo', None))]
                stats['players_pending'] = len(pending)

                if pending:
                    # PE* 与 P* 分治：PE 只打 ESPN，避免误打 500
                    updated_photos = 0

                    def _fetch_one(player):
                        if extract_espn_id(player.id):
                            return media.fetch_player_photo(player.id)
                        src_pid = extract_source_pid(player.id)
                        if not src_pid:
                            src_pid = roster_index.get((player.team_id, player.name))
                        team_src = team_src_map.get(player.team_id)
                        return media.fetch_player_photo(
                            player.id,
                            source_pid=src_pid,
                            source_team_id=team_src,
                        )

                    with ThreadPoolExecutor(max_workers=12) as pool:
                        futures = {pool.submit(_fetch_one, player): player for player in pending}
                        for fut in as_completed(futures):
                            player = futures[fut]
                            try:
                                photo = fut.result()
                            except Exception:
                                photo = None
                            if photo:
                                player.photo = photo
                                updated_photos += 1
                                if updated_photos % 50 == 0:
                                    db.commit()
                    db.commit()
                    stats['players'] += updated_photos
                    stats['players_pending'] = sum(
                        1 for p in players if not is_media_path(getattr(p, 'photo', None))
                    )
        except Exception as e:
            db.rollback()
            logger.warning("Image crawl failed: %s", e)
            stats['status'] = 'failed'
            stats['error'] = str(e)
        finally:
            db.close()

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        try:
            self._save_crawl_log(
                crawl_type='manual',
                crawl_category='media',
                league_id=league_id,
                league_name=league_id or '规范联赛图片',
                found_count=stats.get('players_total', 0),
                saved_count=stats.get('leagues', 0) + stats.get('teams', 0) + stats.get('players', 0),
                status=stats.get('status', 'success'),
                error_message=stats.get('error'),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
        except Exception:
            pass
        logger.info(
            "Image crawl done: leagues=%s teams=%s players=%s pending=%s/%s (%sms)",
            stats['leagues'], stats['teams'], stats['players'],
            stats.get('players_pending', 0), stats.get('players_total', 0), duration_ms,
        )
        return stats

    # ===== P0：射门补采 → 环境补全 → 全量训练 =====

    def _ensure_p0_state(self) -> None:
        if not hasattr(self, "_p0_lock"):
            self._p0_lock = threading.Lock()
        if not hasattr(self, "_p0_status") or not isinstance(self._p0_status, dict):
            self._p0_status = self._empty_p0_status()

    def _persist_p0_status(self) -> None:
        """写入 Redis，供 API 与 RQ worker 跨进程读取。"""
        try:
            from services.p0_status_store import save_shared_p0_status
            save_shared_p0_status(dict(self._p0_status))
        except Exception as e:
            logger.debug("persist p0 status skipped: %s", e)

    def get_p0_status(self) -> Dict:
        self._ensure_p0_state()
        with self._p0_lock:
            local = dict(self._p0_status)
        # 本进程未在跑时，优先读共享状态（RQ worker 写入）
        if not local.get("running"):
            try:
                from services.p0_status_store import load_shared_p0_status
                shared = load_shared_p0_status()
                if shared:
                    # 共享侧仍在跑，或更新时间更新，用共享覆盖展示
                    if shared.get("running") or (
                        shared.get("finished_at")
                        and (not local.get("finished_at") or shared.get("finished_at") >= (local.get("finished_at") or ""))
                    ):
                        with self._p0_lock:
                            self._p0_status = {**self._empty_p0_status(), **shared}
                            return dict(self._p0_status)
            except Exception:
                pass
        return local

    def mark_p0_queued(self, job_id: str = None, job_mode: str = None) -> Dict:
        """入队时标记共享状态，避免 /p0/status 在 worker 启动前显示 idle。"""
        self._ensure_p0_state()
        with self._p0_lock:
            if self._p0_status.get("running") and not job_id:
                return dict(self._p0_status)
            self._p0_status = {
                **self._empty_p0_status(),
                "running": True,
                "status": "running",
                "phase": "queued",
                "message": "已入队，等待执行射门补采",
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "job_id": job_id,
                "job_mode": job_mode,
            }
            snapshot = dict(self._p0_status)
        self._persist_p0_status()
        return snapshot

    def _set_p0_phase(self, phase: str, message: str, extra: Optional[Dict] = None) -> None:
        self._ensure_p0_state()
        with self._p0_lock:
            self._p0_status["phase"] = phase
            self._p0_status["message"] = message
            self._p0_status["running"] = True
            self._p0_status["status"] = "running"
            if extra:
                progress = dict(self._p0_status.get("progress") or {})
                progress.update(extra)
                self._p0_status["progress"] = progress
        self._persist_p0_status()

    def _p0_quality_snapshot(self) -> Dict:
        from services.data_quality_service import data_quality_service

        db = SessionLocal()
        try:
            return data_quality_service.summary(db)
        except Exception as e:
            logger.warning("P0 quality snapshot failed: %s", e)
            return {"error": str(e)}
        finally:
            db.close()

    @staticmethod
    def _p0_compact_quality(payload: Dict) -> Dict:
        totals = (payload or {}).get("totals") or {}
        lag = (payload or {}).get("training_lag") or {}
        model = (payload or {}).get("model") or {}
        return {
            "totals": {
                "finished_matches": totals.get("finished_matches"),
                "matches_with_player_stats": totals.get("matches_with_player_stats"),
                "player_stats_coverage_pct": totals.get("player_stats_coverage_pct"),
                "env_finished_pct": totals.get("env_finished_pct"),
                "env_upcoming_pct": totals.get("env_upcoming_pct"),
                "xg_teams_non_default": totals.get("xg_teams_non_default"),
            },
            "training_lag": {
                "is_stale": lag.get("is_stale"),
                "sample_gap": lag.get("sample_gap"),
                "days_behind": lag.get("days_behind"),
            },
            "model": {
                "version": model.get("version"),
                "weights_has_hyperparams": model.get("weights_has_hyperparams"),
            },
        }

    def _ensure_environment_schedule(self) -> Dict:
        from services.scheduler_service import scheduler

        try:
            tasks = scheduler.get_all_tasks() or {}
            info = tasks.get("environment_crawl") or {}
            if info.get("is_enabled"):
                return {"enabled": True, "already": True, "interval": info.get("interval")}
            interval = int(info.get("interval") or 360)
            scheduler.add_interval_task(
                "environment_crawl", self.crawl_environment, interval
            )
            if not scheduler.is_running():
                scheduler.start()
            return {"enabled": True, "already": False, "interval": interval}
        except Exception as e:
            logger.warning("P0 enable environment_crawl failed: %s", e)
            return {"enabled": False, "error": str(e)}

    def start_p0_async(
        self,
        stats_limit_per_league: int = 500,
        env_limit: int = 1000,
        train: bool = True,
        enable_environment_schedule: bool = True,
        crawl_type: str = "manual",
    ) -> Dict:
        """后台启动 P0 流水线，避免占用 FastAPI 事件循环。"""
        self.get_p0_status()
        self._ensure_p0_state()
        with self._p0_lock:
            if self._p0_status.get("running"):
                return {
                    "status": "error",
                    "message": "P0 正在执行中",
                    "running": True,
                    "phase": self._p0_status.get("phase"),
                    "started_at": self._p0_status.get("started_at"),
                }
            self._p0_status = {
                **self._empty_p0_status(),
                "running": True,
                "status": "running",
                "phase": "queued",
                "message": "已排队，即将开始射门补采",
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "job_mode": "thread",
            }
        self._persist_p0_status()

        def _runner():
            try:
                self.run_p0_pipeline(
                    stats_limit_per_league=stats_limit_per_league,
                    env_limit=env_limit,
                    train=train,
                    enable_environment_schedule=enable_environment_schedule,
                    crawl_type=crawl_type,
                )
            except Exception as e:
                logger.exception("P0 pipeline thread failed: %s", e)
                self._ensure_p0_state()
                with self._p0_lock:
                    self._p0_status["running"] = False
                    self._p0_status["status"] = "failed"
                    self._p0_status["error"] = str(e)
                    self._p0_status["finished_at"] = datetime.now().isoformat(timespec="seconds")
                    self._p0_status["message"] = f"P0 失败：{e}"
                self._persist_p0_status()

        threading.Thread(target=_runner, name="traesolo-p0-pipeline", daemon=True).start()
        return {"status": "started", "message": "P0 已在后台启动"}

    def run_uel_catchup(
        self,
        include_history: bool = True,
        seasons_back: int = 2,
        stats_limit: int = 250,
        train: bool = True,
        crawl_type: str = "manual",
    ) -> Dict:
        """UEL 专项补齐：富化 → 射门缺场补采 → 可选全量训练。"""
        start_time = datetime.now()
        errors: List[str] = []
        enrich_result: Dict = {}
        stats_result: Dict = {}
        train_result: Dict = {"status": "skipped", "message": "未执行训练"}

        try:
            enrich_result = self.enrich_league(
                "UEL",
                include_history=include_history,
                seasons_back=seasons_back,
                crawl_type=crawl_type,
            ) or {}
        except Exception as e:
            logger.error("UEL enrich failed: %s", e)
            errors.append(f"enrich: {e}")
            enrich_result = {"status": "failed", "error": str(e)}

        try:
            stats_result = self.crawl_match_player_stats(
                league_id="UEL",
                limit=max(10, min(int(stats_limit or 250), 500)),
                crawl_type=crawl_type,
                prioritize_mappable=True,
            ) or {}
        except Exception as e:
            logger.error("UEL stats crawl failed: %s", e)
            errors.append(f"stats: {e}")
            stats_result = {"status": "failed", "error": str(e)}

        if train:
            try:
                from services.training_service import training_service
                train_result = training_service.run_train_or_skip() or {}
            except Exception as e:
                logger.error("UEL catchup train failed: %s", e)
                errors.append(f"train: {e}")
                train_result = {"status": "failed", "error": str(e)}

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        overall = "failed" if errors and not (enrich_result or stats_result) else (
            "partial" if errors else "success"
        )
        payload = {
            "status": overall,
            "league_id": "UEL",
            "enrich": enrich_result,
            "stats": {
                "status": stats_result.get("status"),
                "espn_hits": stats_result.get("espn_hits"),
                "saved_matches": stats_result.get("saved_matches") or stats_result.get("saved"),
                "found": stats_result.get("found_count") or stats_result.get("found"),
            },
            "train": {
                "status": train_result.get("status"),
                "message": train_result.get("message"),
                "model_version": train_result.get("model_version"),
            },
            "errors": errors,
            "duration_ms": duration_ms,
        }
        try:
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="uel",
                league_id="UEL",
                league_name="欧联杯补齐",
                found_count=int(payload["stats"].get("espn_hits") or 0),
                saved_count=int(payload["stats"].get("saved_matches") or 0),
                status="success" if overall != "failed" else "failed",
                error_message="; ".join(errors[:5]) if errors else None,
                crawled_data=json.dumps(payload, default=str, ensure_ascii=False),
                started_at=start_time,
                finished_at=datetime.now(),
                duration_ms=duration_ms,
            )
        except Exception:
            pass
        return payload

    def run_extended_catchup(
        self,
        include_history: bool = True,
        seasons_back: int = 1,
        stats_limit: int = 120,
        train: bool = False,
        crawl_type: str = "manual",
        league_ids: Optional[List[str]] = None,
    ) -> Dict:
        """P2 扩展联赛补齐：对 MLS/BRA/SWE/FIN（可覆盖）逐个富化 + 射门补采，可选训练。"""
        from services.real_team_crawler import get_extended_leagues, ESPN_LEAGUE_MAP

        start_time = datetime.now()
        targets = [str(x).upper() for x in (league_ids or get_extended_leagues()) if x]
        targets = [lid for lid in targets if lid in ESPN_LEAGUE_MAP]
        if not targets:
            return {"status": "failed", "error": "no extended leagues", "leagues": []}

        per_league: Dict[str, dict] = {}
        errors: List[str] = []
        cfg_limit = int(_crawler_cfg().get("extended_stats_limit") or stats_limit or 80)
        limit = max(10, min(int(stats_limit or cfg_limit), 400))

        for lid in targets:
            entry: Dict = {"league_id": lid}
            try:
                entry["enrich"] = self.enrich_league(
                    lid,
                    include_history=include_history,
                    seasons_back=seasons_back,
                    crawl_type=crawl_type,
                ) or {}
            except Exception as e:
                logger.error("extended enrich %s failed: %s", lid, e)
                errors.append(f"{lid}/enrich: {e}")
                entry["enrich"] = {"status": "failed", "error": str(e)}
            try:
                entry["stats"] = self.crawl_match_player_stats(
                    league_id=lid,
                    limit=limit,
                    crawl_type=crawl_type,
                    prioritize_mappable=True,
                ) or {}
            except Exception as e:
                logger.error("extended stats %s failed: %s", lid, e)
                errors.append(f"{lid}/stats: {e}")
                entry["stats"] = {"status": "failed", "error": str(e)}
            per_league[lid] = entry

        train_result: Dict = {"status": "skipped", "message": "未执行训练"}
        if train:
            try:
                from services.training_service import training_service
                train_result = training_service.run_train_or_skip() or {}
            except Exception as e:
                logger.error("extended catchup train failed: %s", e)
                errors.append(f"train: {e}")
                train_result = {"status": "failed", "error": str(e)}

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        saved = sum(
            int((v.get("stats") or {}).get("saved_matches") or (v.get("stats") or {}).get("saved") or 0)
            for v in per_league.values()
        )
        overall = "failed" if errors and saved <= 0 else ("partial" if errors else "success")
        payload = {
            "status": overall,
            "leagues": targets,
            "per_league": per_league,
            "train": train_result,
            "errors": errors[:12],
            "duration_ms": duration_ms,
            "saved_matches": saved,
        }
        try:
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="extended",
                league_id=None,
                league_name="扩展联赛补齐",
                found_count=len(targets),
                saved_count=saved,
                status="success" if overall != "failed" else "failed",
                error_message="; ".join(errors[:5]) if errors else None,
                crawled_data=json.dumps(payload, default=str, ensure_ascii=False),
                started_at=start_time,
                finished_at=datetime.now(),
                duration_ms=duration_ms,
            )
        except Exception:
            pass
        return payload

    def run_p0_pipeline(
        self,
        stats_limit_per_league: int = 500,
        env_limit: int = 1000,
        train: bool = True,
        enable_environment_schedule: bool = True,
        crawl_type: str = "manual",
    ) -> Dict:
        """P0：重点联赛历史射门补采 → 环境补全 → 启用气象任务 → 全量训练。"""
        self._ensure_p0_state()
        start_time = datetime.now()
        stats_limit_per_league = max(10, min(int(stats_limit_per_league or 500), 500))
        env_limit = max(50, min(int(env_limit or 1000), 2000))

        with self._p0_lock:
            self._p0_status["running"] = True
            self._p0_status["status"] = "running"
            if not self._p0_status.get("started_at"):
                self._p0_status["started_at"] = start_time.isoformat(timespec="seconds")
            self._p0_status["error"] = None
            self._p0_status["result"] = None
        self._persist_p0_status()

        errors: List[str] = []
        snapshot_before = {}
        stats_result: Dict = {}
        env_result: Dict = {}
        schedule_result: Dict = {"enabled": False, "skipped": True}
        train_result: Dict = {"status": "skipped", "message": "未执行训练"}

        try:
            self._set_p0_phase("snapshot", "记录补齐前数据质量")
            snapshot_before = self._p0_compact_quality(self._p0_quality_snapshot())

            self._set_p0_phase(
                "stats",
                f"重点联赛逐场射门补采（每联赛最多 {stats_limit_per_league} 场，优先历史缺口）",
            )
            try:
                stats_result = self.backfill_priority_match_player_stats(
                    limit_per_league=stats_limit_per_league,
                    crawl_type=crawl_type,
                    prefer_older=True,
                ) or {}
            except Exception as e:
                logger.error("P0 stats backfill failed: %s", e)
                errors.append(f"stats: {e}")
                stats_result = {"status": "failed", "error": str(e)}
            self._set_p0_phase(
                "stats",
                f"射门补采完成：命中 {stats_result.get('espn_hits', 0)} · 入库 {stats_result.get('saved_matches', 0)} 场",
                extra={"stats": {
                    "saved_matches": stats_result.get("saved_matches"),
                    "espn_hits": stats_result.get("espn_hits"),
                    "miss_count": stats_result.get("miss_count"),
                    "status": stats_result.get("status"),
                }},
            )

            self._set_p0_phase("environment", f"Open-Meteo 补全环境字段（最多 {env_limit} 场）")
            try:
                env_result = self.crawl_environment(
                    limit=env_limit,
                    only_missing=True,
                    upcoming_only=False,
                    crawl_type=crawl_type,
                ) or {}
            except Exception as e:
                logger.error("P0 environment backfill failed: %s", e)
                errors.append(f"environment: {e}")
                env_result = {"status": "failed", "error": str(e)}
            coverage = env_result.get("coverage") or {}
            self._set_p0_phase(
                "environment",
                f"环境补全：扫描 {env_result.get('scanned', 0)} · 更新 {env_result.get('updated', 0)}",
                extra={"environment": {
                    "scanned": env_result.get("scanned"),
                    "updated": env_result.get("updated"),
                    "env_finished_pct": coverage.get("env_finished_pct"),
                    "status": env_result.get("status"),
                }},
            )

            if enable_environment_schedule:
                self._set_p0_phase("schedule", "启用气象环境定时补全")
                schedule_result = self._ensure_environment_schedule()
            else:
                schedule_result = {"enabled": False, "skipped": True}

            if train:
                from services.training_service import training_service

                self._set_p0_phase("train", "全量训练（ELO / 泊松 / xG / 融合权重）")
                try:
                    train_result = training_service.run_train_or_skip() or {}
                    if train_result.get("status") == "skipped":
                        train_result["message"] = train_result.get("message") or "训练正在进行中，本次跳过；请稍后手动训练"
                except Exception as e:
                    logger.error("P0 train_all failed: %s", e)
                    errors.append(f"train: {e}")
                    train_result = {"status": "failed", "message": str(e)}
            self._set_p0_phase(
                "train",
                train_result.get("message") or f"训练状态 {train_result.get('status')}",
                extra={"train": {
                    "status": train_result.get("status"),
                    "model_version": train_result.get("model_version"),
                    "total_matches": train_result.get("total_matches"),
                }},
            )

            self._set_p0_phase("snapshot", "记录补齐后数据质量")
            snapshot_after = self._p0_compact_quality(self._p0_quality_snapshot())

            train_ok = (train_result.get("status") or "skipped") in ("success", "skipped")
            stats_ok = (stats_result.get("status") or "failed") != "failed" or int(stats_result.get("saved_matches") or 0) > 0
            env_ok = (env_result.get("status") or "failed") != "failed"
            if errors and not (stats_ok or env_ok or train_ok):
                overall = "failed"
            elif errors or not train_ok or (train and train_result.get("status") == "skipped"):
                overall = "partial" if (stats_ok or env_ok or train_result.get("status") == "success") else "failed"
            else:
                overall = "success"

            payload = {
                "status": overall,
                "stats": {
                    "saved_matches": stats_result.get("saved_matches"),
                    "saved_stats": stats_result.get("saved_stats"),
                    "espn_hits": stats_result.get("espn_hits"),
                    "miss_count": stats_result.get("miss_count"),
                    "status": stats_result.get("status"),
                    "limit_per_league": stats_limit_per_league,
                    "prefer_older": True,
                },
                "environment": {
                    "scanned": env_result.get("scanned"),
                    "updated": env_result.get("updated"),
                    "coverage": env_result.get("coverage"),
                    "status": env_result.get("status"),
                    "limit": env_limit,
                },
                "environment_schedule": schedule_result,
                "train": {
                    "status": train_result.get("status"),
                    "message": train_result.get("message"),
                    "model_version": train_result.get("model_version"),
                    "total_matches": train_result.get("total_matches"),
                    "accuracy": train_result.get("accuracy"),
                },
                "quality_before": snapshot_before,
                "quality_after": snapshot_after,
                "errors": errors,
            }

            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            payload["duration_ms"] = duration_ms

            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="p0",
                league_id=None,
                league_name="P0 补齐+训练",
                found_count=int(stats_result.get("espn_hits") or 0),
                saved_count=int(stats_result.get("saved_stats") or 0) + int(env_result.get("updated") or 0),
                updated_count=int(stats_result.get("saved_matches") or 0),
                status="success" if overall != "failed" else "failed",
                error_message="; ".join(errors[:5]) if errors else None,
                crawled_data=json.dumps(payload, default=str, ensure_ascii=False),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )

            done_msg = (
                f"P0 {overall}：射门入库 {payload['stats'].get('saved_matches') or 0} 场"
                f" · 环境更新 {payload['environment'].get('updated') or 0}"
                f" · 训练 {payload['train'].get('status')}"
            )
            self._set_p0_phase("done", done_msg)
            with self._p0_lock:
                self._p0_status["status"] = overall
                self._p0_status["result"] = payload
                self._p0_status["error"] = "; ".join(errors[:5]) if errors else None
            self._persist_p0_status()
            logger.info("P0 pipeline finished: %s (%sms)", overall, duration_ms)
            return payload
        except Exception as e:
            logger.exception("P0 pipeline failed: %s", e)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            self._save_crawl_log(
                crawl_type=crawl_type,
                crawl_category="p0",
                league_id=None,
                league_name="P0 补齐+训练",
                found_count=0,
                saved_count=0,
                status="failed",
                error_message=str(e),
                started_at=start_time,
                finished_at=end_time,
                duration_ms=duration_ms,
            )
            with self._p0_lock:
                self._p0_status["status"] = "failed"
                self._p0_status["error"] = str(e)
                self._p0_status["message"] = f"P0 失败：{e}"
            self._persist_p0_status()
            raise
        finally:
            with self._p0_lock:
                self._p0_status["running"] = False
                self._p0_status["finished_at"] = datetime.now().isoformat(timespec="seconds")
            self._persist_p0_status()


crawler_service = CrawlerService()
