"""live.500.com/jczq.php 竞彩比分列表采集器。

对齐 live.500.com「竞彩比分」标签页（https://live.500.com/jczq.php）的列布局：
场次 / 赛事 / 轮次 / 比赛时间 / 状态 / 主队 / 比分 / 客队 / 半场 / 胜负奖金 / 胜负 / 直播 / 分析 / 置顶。

要点：
- 胜平负/让球 SP 内嵌在页面 JS 变量 liveOddsList 中（按 fid 索引，sp=胜平负、rqsp=让球）。
- <tr> 属性携带 fid（= fixture_id）、status（0=未开赛 / 1=完赛）、lid（500 联赛 id）。
- 球队 ID 取自 //liansai.500.com/team/NNN/ 链接 → T{NNN}（规范可入库 ID）。
- 完赛比分在 .pk 内 .clt1（主）/ .clt3（客）；竞彩让球整数在 home 的 sp_rq / sp_sr；
  亚盘盘口文案（平手/球半/受一球等）在比分列 .pk 中间链的 data-pb / data-ao。

产物 dict 与 CrawlerService._save_matches 白名单对齐（fixture_id 优先只更新赔率/比分）。
"""
import json
import logging
import re
from datetime import date, time, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class LiveJingcaiCrawler:
    def __init__(self):
        self.base_url = 'https://live.500.com/jczq.php'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://live.500.com/',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    # ---- 公开入口 ----

    def crawl(self, days_ahead: int = 1) -> List[Dict]:
        """采集 live.500.com/jczq.php 今日竞彩比分列表。

        页面服务端只渲染当日（含未开赛与已完赛），date/e 参数不影响服务端输出，
        因此仅抓取默认页。返回按 fid 去重后的列表。
        """
        matches = self._crawl_once()
        logger.info("LiveJingcai crawler generated %s matches", len(matches))
        return matches

    def crawl_historical(self, days_back: int = 30) -> List[Dict]:
        """历史回补：站点无稳定历史入口，仅能拉当日快照；保留接口供调用方统一处理。"""
        return self.crawl(days_ahead=0)

    # ---- 主抓取 ----

    def _crawl_once(self) -> List[Dict]:
        matches: List[Dict] = []
        try:
            r = self.session.get(self.base_url, timeout=30)
            try:
                text = r.content.decode('gbk', errors='replace')
            except Exception:
                text = r.content.decode('utf-8', errors='replace')

            soup = BeautifulSoup(text, 'html.parser')
            odds_map = self._parse_live_odds(text)

            table = soup.find('table', class_='bf_tablelist01')
            if not table:
                logger.warning("LiveJingcai: no table with class 'bf_tablelist01'")
                return matches

            for row in table.find_all('tr'):
                if not row.get('id') or not str(row.get('id', '')).startswith('a'):
                    continue
                item = self._parse_match_row(row, odds_map)
                if item:
                    matches.append(item)

            logger.info("LiveJingcai: crawled %s matches from %s", len(matches), self.base_url)
        except Exception as e:
            logger.error("LiveJingcai crawl failed: %s", e)
        return matches

    @staticmethod
    def _parse_live_odds(text: str) -> Dict[str, Dict[str, List[str]]]:
        """解析内嵌 JS var liveOddsList = {...}; → {fid: {'sp': [w,d,l], 'rqsp': [w,d,l]}}。"""
        m = re.search(r'var\s+liveOddsList\s*=\s*(\{.*?\});', text, re.S)
        if not m:
            return {}
        try:
            data = json.loads(m.group(1))
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.debug("LiveJingcai: liveOddsList parse failed: %s", e)
            return {}

    # ---- 行解析 ----

    def _parse_match_row(self, row, odds_map: Dict) -> Optional[Dict]:
        try:
            tds = row.find_all('td')
            if len(tds) < 9:
                return None

            match_no = self._clean_text(tds[0].get_text(' ', strip=True))
            league_name = self._clean_text(tds[1].get_text(' ', strip=True))
            round_name = self._clean_text(tds[2].get_text(' ', strip=True))
            time_text = self._clean_text(tds[3].get_text(' ', strip=True))
            status_text = self._clean_text(tds[4].get_text(' ', strip=True))
            home_td = tds[5]
            away_td = tds[7]
            half_score = self._clean_text(tds[8].get_text(' ', strip=True))

            home_team_name = self._extract_team_name(home_td)
            away_team_name = self._extract_team_name(away_td)
            home_team_id = self._extract_team_id(home_td)
            away_team_id = self._extract_team_id(away_td)
            if not home_team_name or not away_team_name:
                return None

            league_id = self._map_league_name(league_name) or self._map_league_id_from_td(tds[1])
            if not league_id:
                return None

            match_date, match_time = self._parse_match_time(time_text)

            score_text = self._clean_text(tds[6].get_text(' ', strip=True))
            home_goals, away_goals, result, status = self._parse_score_status(
                row, tds[6], score_text, status_text
            )

            handicap = self._extract_handicap(home_td)
            handicap_line = self._extract_handicap_line(tds[6])

            fixture_id = str(row.get('fid') or '').strip() or None

            odds = self._pick_odds(odds_map, fixture_id)
            spf = odds.get('sp') or []
            nspf = odds.get('rqsp') or []

            match_id = (
                f"JC-{league_id}-{match_date.strftime('%Y-%m-%d')}"
                f"-{home_team_id}-{away_team_id}"
            )

            return {
                'id': match_id[:50],
                'league_id': league_id[:20],
                'league_name': league_name,
                'home_team_id': home_team_id[:20],
                'home_team_name': home_team_name,
                'away_team_id': away_team_id[:20],
                'away_team_name': away_team_name,
                'match_date': match_date,
                'match_time': match_time,
                'venue': '',
                'status': status,
                'home_goals': home_goals,
                'away_goals': away_goals,
                'result': result,
                'weather': '',
                'temperature': '',
                'pitch_condition': '',
                'stage': self._determine_stage(league_id, round_name),
                'group_name': None,
                'round_name': round_name or match_no,
                'fixture_id': fixture_id,
                'process_id': None,
                'handicap': handicap,
                'handicap_line': handicap_line,
                'odds_spf_win': self._to_float(spf, 0),
                'odds_spf_draw': self._to_float(spf, 1),
                'odds_spf_lose': self._to_float(spf, 2),
                'odds_nspf_win': self._to_float(nspf, 0),
                'odds_nspf_draw': self._to_float(nspf, 1),
                'odds_nspf_lose': self._to_float(nspf, 2),
                'odds_bf_json': None,
                'is_single': False,
                'buy_end_time': None,
                'half_score': half_score,
                'match_no': match_no,
                'source': 'live_jingcai',
            }
        except Exception as e:
            logger.error("LiveJingcai parse row failed: %s", e)
            return None

    # ---- 子解析 ----

    @staticmethod
    def _clean_text(raw) -> str:
        return re.sub(r'\s+', ' ', (raw or '')).strip()

    @staticmethod
    def _extract_team_name(td) -> str:
        a = td.find('a', href=True)
        if a:
            return LiveJingcaiCrawler._clean_text(a.get_text(' ', strip=True))
        return LiveJingcaiCrawler._clean_text(td.get_text(' ', strip=True))

    @staticmethod
    def _extract_team_id(td) -> Optional[str]:
        a = td.find('a', href=True)
        if not a:
            return None
        href = a.get('href') or ''
        m = re.search(r'/team/(\d+)', href)
        if m:
            return f"T{m.group(1)}"[:20]
        return None

    @staticmethod
    def _extract_handicap(home_td) -> Optional[int]:
        for span in home_td.find_all('span'):
            cls = ' '.join(span.get('class') or [])
            txt = LiveJingcaiCrawler._clean_text(span.get_text(' ', strip=True))
            if ('sp_rq' in cls or 'sp_sr' in cls) and txt:
                m = re.search(r'[+-]?\d+(?:\.\d+)?', txt)
                if m:
                    try:
                        return int(float(m.group(0)))
                    except ValueError:
                        return None
        return None

    @staticmethod
    def _extract_handicap_line(score_td) -> Optional[str]:
        """比分列中间亚盘文案：优先 data-pb（即时），其次可见文本，再次 data-ao（初盘）。"""
        pk = score_td.find('div', class_='pk') if score_td else None
        if not pk:
            return None
        for a in pk.find_all('a'):
            cls = ' '.join(a.get('class') or [])
            if 'clt1' in cls or 'clt3' in cls:
                continue
            pb = LiveJingcaiCrawler._clean_text(a.get('data-pb') or '')
            txt = LiveJingcaiCrawler._clean_text(a.get_text(' ', strip=True))
            ao = LiveJingcaiCrawler._clean_text(a.get('data-ao') or '')
            line = pb or txt or ao
            if line:
                return line[:30]
        return None

    @staticmethod
    def _pick_odds(odds_map: Dict, fixture_id: Optional[str]) -> Dict:
        if not fixture_id:
            return {}
        return odds_map.get(fixture_id) or {}

    @staticmethod
    def _to_float(arr: List, idx: int) -> Optional[float]:
        try:
            if idx < len(arr) and arr[idx] not in (None, '', '-', '未开售'):
                val = float(arr[idx])
                return val if val > 0 else None
        except (TypeError, ValueError):
            pass
        return None

    @staticmethod
    def _parse_score_status(row, score_td, score_text: str, status_text: str):
        """完赛比分取自 .pk 内 .clt1/.clt3；状态由 tr.status + 状态列推断。"""
        status = 'upcoming'
        raw_status = str(row.get('status') or '0')
        is_end = raw_status == '1'

        home_goals = away_goals = None
        result = None

        if is_end or status_text in ('完', '完场', '已完场', '结束', '胜', '平', '负'):
            status = 'finished'
            home_goals, away_goals, result = LiveJingcaiCrawler._extract_pk_score(score_td)
            if home_goals is None:
                home_goals, away_goals, result = LiveJingcaiCrawler._parse_plain_score(score_text)
        elif status_text in ('中', '进', '进行中', 'LIVE'):
            status = 'live'
            home_goals, away_goals, result = LiveJingcaiCrawler._extract_pk_score(score_td)
        else:
            status = 'upcoming'

        return home_goals, away_goals, result, status

    @staticmethod
    def _extract_pk_score(score_td):
        pk = score_td.find('div', class_='pk')
        if not pk:
            return None, None, None
        home = LiveJingcaiCrawler._clean_text(
            pk.select_one('a.clt1').get_text(' ', strip=True) if pk.select_one('a.clt1') else ''
        )
        away = LiveJingcaiCrawler._clean_text(
            pk.select_one('a.clt3').get_text(' ', strip=True) if pk.select_one('a.clt3') else ''
        )
        return LiveJingcaiCrawler._goals_from(home, away)

    @staticmethod
    def _parse_plain_score(score_text: str):
        m = re.search(r'(\d+)\s*[-:]\s*(\d+)', score_text or '')
        if m:
            return LiveJingcaiCrawler._goals_from(m.group(1), m.group(2))
        return None, None, None

    @staticmethod
    def _goals_from(home: str, away: str):
        if not home or not away:
            return None, None, None
        try:
            h, a = int(home), int(away)
        except (TypeError, ValueError):
            return None, None, None
        result = 'H' if h > a else ('A' if h < a else 'D')
        return h, a, result

    @staticmethod
    def _parse_match_time(time_text: str):
        today = date.today()
        default_time = time(15, 0)
        if not time_text:
            return today, default_time
        m = re.search(r'(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})', time_text)
        if m:
            month, day, hour, minute = (int(x) for x in m.groups())
            year = today.year
            try:
                parsed = date(year, month, day)
            except ValueError:
                return today, default_time
            # 跨年启发式：明显偏早→次年；明显偏晚→上一年
            if parsed < today - timedelta(days=120):
                parsed = date(year + 1, month, day)
            elif parsed > today + timedelta(days=240):
                parsed = date(year - 1, month, day)
            try:
                return parsed, time(hour, minute)
            except ValueError:
                return today, default_time
        return today, default_time

    @staticmethod
    def _map_league_name(league_name: str) -> Optional[str]:
        if not league_name:
            return None
        from services.live_500_crawler import live_500_crawler
        try:
            mapped = live_500_crawler._map_league_name(league_name)
            if mapped and mapped != 'OTHER':
                return mapped
        except Exception:
            pass
        return None

    @staticmethod
    def _map_league_id_from_td(league_td) -> Optional[str]:
        a = league_td.find('a', href=True)
        if not a:
            return None
        href = a.get('href') or ''
        m = re.search(r'zuqiu-(\d+)', href)
        if not m:
            return None
        ls_id = f"LS{m.group(1)}"
        try:
            from services.real_team_crawler import FIVE00_TO_CANONICAL
            return FIVE00_TO_CANONICAL.get(ls_id, ls_id)[:20]
        except Exception:
            return ls_id[:20]

    @staticmethod
    def _determine_stage(league_id: str, round_name: str) -> str:
        round_name = round_name or ''
        if league_id in ('WC', 'EC', 'CA', 'AFC'):
            if '决赛' in round_name:
                return 'final'
            if '半决赛' in round_name:
                return 'semi_final'
            if '三四名' in round_name:
                return 'third_place'
            if '四分之一' in round_name or '1/4' in round_name:
                return 'quarter_final'
            if '十六强' in round_name or '1/8' in round_name:
                return 'round_of_16'
            if '小组赛' in round_name or '分组赛' in round_name:
                return 'group'
            return 'league'
        if '杯' in league_id or 'CUP' in league_id:
            if '决赛' in round_name:
                return 'final'
            if '半决赛' in round_name:
                return 'semi_final'
            if '四分之一' in round_name or '1/4' in round_name:
                return 'quarter_final'
            if '十六强' in round_name or '1/8' in round_name:
                return 'round_of_16'
            return 'group'
        return 'league'


live_jingcai_crawler = LiveJingcaiCrawler()
