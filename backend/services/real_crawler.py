import logging
import re
from datetime import date, time, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class RealMatchCrawler:
    def __init__(self):
        self.base_url = 'https://live.500.com/jczq.php'
        self.trade_url = 'https://trade.500.com/jczq/'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.team_name_mapping = {
            '曼联': 'MUN', '曼城': 'MCI', '利物浦': 'LIV', '阿森纳': 'ARS',
            '切尔西': 'CHE', '热刺': 'TOT', '纽卡斯尔': 'NEW', '布莱顿': 'BHA',
            '阿斯顿维拉': 'AVL', '埃弗顿': 'EVE', '西汉姆': 'WHU', '富勒姆': 'FUL',
            '水晶宫': 'CRY', '狼队': 'WOL', '伯恩茅斯': 'BOU', '布伦特福德': 'BRE',
            '诺丁汉森林': 'NFO', '南安普顿': 'SOU', '利兹联': 'LEE', '莱斯特': 'LEI',
            '皇马': 'RMA', '巴萨': 'BAR', '马竞': 'ATM', '瓦伦西亚': 'VAL',
            '塞维利亚': 'SEV', '比利亚雷亚尔': 'VIL', '皇家社会': 'REAL_SOC', '毕尔巴鄂': 'BIL',
            '赫塔费': 'GET', '塞尔塔': 'CEL', '加的斯': 'CAD', '奥萨苏纳': 'OSA',
            '马洛卡': 'MLL', '格拉纳达': 'GRA', '艾尔切': 'ELC', '巴列卡诺': 'RVA',
            '拜仁': 'BAY', '多特': 'DOR', '勒沃库森': 'LEV', '沃尔夫斯堡': 'WOB',
            '法兰克福': 'SGE', '霍芬海姆': 'HOF', '斯图加特': 'SCF', '弗赖堡': 'FRE',
            '门兴': 'MG', '柏林联合': 'UNB', '科隆': 'KOL', '奥格斯堡': 'AUG',
            '波鸿': 'BOH', '美因茨': 'MAI', '沙尔克': 'S04', '柏林赫塔': 'BSC',
            '国米': 'INT', '尤文': 'JUV', 'AC米兰': 'MIL', '那不勒斯': 'NAP',
            '拉齐奥': 'LAZ', '罗马': 'ROMA', '亚特兰大': 'ATL', '佛罗伦萨': 'FIO',
            '都灵': 'TOR', '博洛尼亚': 'BOL', '维罗纳': 'VER', '萨索洛': 'SAS',
            '恩波利': 'EMP', '乌迪内斯': 'UDI', '热那亚': 'GEN', '蒙扎': 'MNZ',
            '巴黎': 'PSG', '里尔': 'LIL', '马赛': 'OM', '雷恩': 'REN',
            '里昂': 'LYO', '摩纳哥': 'ASM', '尼斯': 'NIC', '斯特拉斯堡': 'STR',
            '兰斯': 'REI', '南特': 'NTE', '布雷斯特': 'BES', '洛里昂': 'LOR',
            '阿雅克肖': 'AJA', '图卢兹': 'TOU', '昂热': 'ANG', '梅斯': 'MET',
            '巴西': 'BRA', '阿根廷': 'ARG', '德国': 'GER', '法国': 'FRA',
            '西班牙': 'ESP', '葡萄牙': 'POR', '比利时': 'BEL', '荷兰': 'NED',
            '意大利': 'ITA', '英格兰': 'ENG', '克罗地亚': 'CRO', '乌拉圭': 'URU',
            '瑞士': 'SUI', '美国': 'USA', '墨西哥': 'MEX', '哥伦比亚': 'COL',
            '智利': 'CHI', '厄瓜多尔': 'ECU', '日本': 'JPN', '韩国': 'KOR',
            '澳大利亚': 'AUS', '伊朗': 'IRN', '沙特': 'SAU', '卡塔尔': 'QAT',
            '泰国': 'THA', '阿联酋': 'UAE', '中国': 'CHN',
            '南非': 'SAF', '捷克': 'CZE', '加拿大': 'CAN', '波黑': 'BIH',
            '摩洛哥': 'MAR', '苏格兰': 'SCO', '海地': 'HAI', '巴拉圭': 'PAR',
            '土耳其': 'TUR', '科特迪瓦': 'CIV', '库拉索': 'CUR', '瑞典': 'SWE',
            '突尼斯': 'TUN', '埃及': 'EGY', '新西兰': 'NZL', '佛得角': 'CPV',
            '挪威': 'NOR', '塞内加尔': 'SEN', '伊拉克': 'IRQ', '奥地利': 'AUT',
            '阿尔及利亚': 'ALG', '约旦': 'JOR', '民主刚果': 'COD', '乌兹别克斯坦': 'UZB',
            '加纳': 'GHA', '巴拿马': 'PAN',
        }
        self.league_name_mapping = {
            '英超': 'EPL', '西甲': 'LALIGA', '德甲': 'BUNDES', '意甲': 'SERIEA',
            '法甲': 'LIGUE1', '世界杯': 'WC', '欧冠': 'UCL', '欧联': 'UEL',
            '欧洲杯': 'EC', '美洲杯': 'CA', '亚洲杯': 'AFC',
            '解放者杯': 'LIB', '日职': 'J1', '日J': 'J1',
            'K1联赛': 'K1', '瑞典超': 'SWE', '瑞超': 'SWE', '瑞典超级联赛': 'SWE',
            '芬超': 'FIN', '芬兰超级联赛': 'FIN',
            '韩职': 'K1', '挪超': 'NOR', '挪威超级联赛': 'NOR',
            '巴甲': 'BRA', '美职足': 'MLS', '英冠': 'ECH',
            '法乙': 'FL2', '法国乙级联赛': 'FL2',
            '葡超': 'PORL', '葡萄牙超级联赛': 'PORL',
            '亚冠': 'ACL', '亚洲冠军': 'ACL',
        }

    def crawl(self, league_id: str, days_ahead: int = 7) -> List[Dict]:
        if league_id == 'WC':
            matches = self._crawl_world_cup()
        else:
            matches = self._crawl_all_matches(days_ahead=days_ahead)

        filtered_matches = []
        for match in matches:
            mapped_league_id = match.get('league_id', '')
            if league_id == 'all' or mapped_league_id == league_id:
                filtered_matches.append(match)

        logger.info(f"Real crawler generated {len(filtered_matches)} matches for league {league_id}")
        return filtered_matches

    def crawl_historical(self, league_id: str = None, days_back: int = 30, start_date: date = None) -> List[Dict]:
        matches = []
        today = date.today()
        
        if start_date:
            delta_days = (today - start_date).days
        else:
            delta_days = days_back
        
        for day_offset in range(1, delta_days + 1):
            match_date = today - timedelta(days=day_offset)
            day_matches = self._crawl_by_date(match_date.strftime('%Y-%m-%d'))
            matches.extend(day_matches)
        
        filtered_matches = []
        for match in matches:
            if league_id == 'all' or league_id is None or match.get('league_id') == league_id:
                filtered_matches.append(match)
        
        logger.info(f"Real crawler generated {len(filtered_matches)} historical matches for league {league_id}")
        return filtered_matches

    def _crawl_world_cup(self) -> List[Dict]:
        matches = []
        base_url = 'https://liansai.500.com'
        
        stages = [
            ('小组赛', 'group', '/zuqiu-19476/jifen-26226/'),
            ('1/16决赛', 'round_of_16', '/zuqiu-19476/jifen-26220/'),
            ('1/8决赛', 'round_of_16', '/zuqiu-19476/jifen-26221/'),
            ('1/4决赛', 'quarter_final', '/zuqiu-19476/jifen-26222/'),
            ('半决赛', 'semi_final', '/zuqiu-19476/jifen-26223/'),
            ('季军赛', 'third_place', '/zuqiu-19476/jifen-26224/'),
            ('决赛', 'final', '/zuqiu-19476/jifen-26225/'),
        ]
        
        for stage_name, stage_code, stage_url in stages:
            stage_matches = self._crawl_league_stage(base_url + stage_url, stage_code)
            matches.extend(stage_matches)
            logger.info(f"Crawled {len(stage_matches)} matches for {stage_name}")
        
        return matches
    
    def _crawl_league_stage(self, url: str, stage: str) -> List[Dict]:
        matches = []
        try:
            r = self.session.get(url, timeout=30)
            text = r.content.decode('gbk', errors='replace')
            soup = BeautifulSoup(text, 'html.parser')
            
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) < 2:
                    continue
                
                first_row_cells = [c.text.strip() for c in rows[0].find_all(['td', 'th'])]
                if '比赛时间' not in str(first_row_cells):
                    continue
                
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    cell_texts = [c.text.strip() for c in cells]
                    
                    if len(cell_texts) < 5:
                        continue
                    
                    match_time_str = cell_texts[0]
                    home_team_name = cell_texts[1]
                    score = cell_texts[2]
                    away_team_name = cell_texts[3]
                    result = cell_texts[4] if len(cell_texts) > 4 else ''
                    
                    home_team_id = self._map_team_name(home_team_name)
                    away_team_id = self._map_team_name(away_team_name)
                    
                    if not home_team_id or not away_team_id:
                        continue
                    
                    match_date = date.today()
                    match_time = time(15, 0)
                    
                    if match_time_str:
                        try:
                            if ' ' in match_time_str:
                                date_part, time_part = match_time_str.split(' ', 1)
                                date_parts = date_part.split('-')
                                time_parts = time_part.split(':')
                                match_date = date(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
                                match_time = time(int(time_parts[0]), int(time_parts[1]))
                        except:
                            pass
                    
                    home_goals = 0
                    away_goals = 0
                    match_result = None
                    
                    if score and score != '-' and 'vs' not in score:
                        main_score = score.split(' ')[0] if ' ' in score else score
                        if ':' in main_score:
                            score_parts = main_score.split(':')
                            if len(score_parts) == 2:
                                try:
                                    home_goals = int(score_parts[0])
                                    away_goals = int(score_parts[1])
                                    if home_goals > away_goals:
                                        match_result = 'H'
                                    elif home_goals < away_goals:
                                        match_result = 'A'
                                    else:
                                        match_result = 'D'
                                except:
                                    pass
                    
                    match_status = 'upcoming'
                    if match_result:
                        match_status = 'finished'
                    elif result and result != '' and result != '-' and 'vs' not in result:
                        match_status = 'finished'
                    
                    match_id = f"WC-{match_date.strftime('%Y-%m-%d')}-{home_team_id}-{away_team_id}"
                    
                    matches.append({
                        'id': match_id,
                        'league_id': 'WC',
                        'league_name': '世界杯',
                        'home_team_id': home_team_id,
                        'home_team_name': home_team_name,
                        'away_team_id': away_team_id,
                        'away_team_name': away_team_name,
                        'match_date': match_date,
                        'match_time': match_time,
                        'venue': '',
                        'status': match_status,
                        'home_goals': home_goals,
                        'away_goals': away_goals,
                        'result': match_result,
                        'weather': '',
                        'temperature': '',
                        'pitch_condition': '',
                        'stage': stage,
                        'group_name': None,
                        'round_name': stage,
                    })
        
        except Exception as e:
            logger.error(f"Failed to crawl league stage {url}: {str(e)}")
        
        return matches
    
    def _crawl_all_matches(self, days_ahead: int = 7) -> List[Dict]:
        matches = []
        try:
            r = self.session.get(self.base_url, timeout=30)
            r.encoding = 'gb2312'
            soup = BeautifulSoup(r.content, 'html.parser')

            table = soup.find('table', class_='bf_tablelist01')
            if table:
                for tr in table.find_all('tr')[1:]:
                    match_data = self._parse_match_row(tr)
                    if match_data:
                        matches.append(match_data)

            trade = self._crawl_jczq_trade(days_ahead=days_ahead)
            from services.match_dedup import dedup_crawled_matches
            combined = dedup_crawled_matches(matches + trade)
            logger.info("Crawled %s upcoming matches from jingcai", len(combined))
            return combined
        except Exception as e:
            logger.error(f"Failed to crawl matches: {str(e)}")

        return matches

    def _crawl_jczq_trade(self, days_ahead: int = 7, days_back: int = 0) -> List[Dict]:
        """爬取 trade.500.com/jczq 胜平负/让球页：默认页 + 近 N 日 date 参数。

        days_ahead：向前天数（含今日）；days_back：向后历史天数（用于与比分回补对齐）。
        """
        from services.match_dedup import dedup_crawled_matches

        # days_ahead=0 合法（仅今日 + 历史），不能用 `or 7`
        days_a = max(0, min(int(7 if days_ahead is None else days_ahead), 14))
        days_b = max(0, min(int(0 if days_back is None else days_back), 90))
        # 先拉无 date 的默认页（与站内「胜平负/让球」一致），再按日补齐
        buckets: List[Dict] = []
        buckets.extend(self._crawl_jczq_trade_url(self.trade_url))
        for d in [date.today() + timedelta(days=i) for i in range(0, days_a + 1)]:
            buckets.extend(
                self._crawl_jczq_trade_url(
                    f"{self.trade_url}?date={d.strftime('%Y-%m-%d')}",
                    d.strftime('%Y-%m-%d'),
                )
            )
        for d in [date.today() - timedelta(days=i) for i in range(1, days_b + 1)]:
            buckets.extend(
                self._crawl_jczq_trade_url(
                    f"{self.trade_url}?date={d.strftime('%Y-%m-%d')}",
                    d.strftime('%Y-%m-%d'),
                )
            )
        combined = dedup_crawled_matches(buckets)
        logger.info(
            "Crawled %s unique jingcai trade matches (days_ahead=%s, days_back=%s, raw=%s)",
            len(combined), days_a, days_b, len(buckets),
        )
        return combined

    @staticmethod
    def _merge_spf_into_bf(bf_matches: List[Dict], spf_matches: List[Dict]) -> List[Dict]:
        """把胜平负/让球页 SP 合并进比分页场次（同源 fixture_id / 场次 id）。

        比分页（playid=271）不含胜平负投注按钮，列表 UI 需要的 odds_nspf_* / odds_spf_*
        必须从胜平负页补齐；仅覆盖非空字段，不冲掉已有比分投注区。
        """
        odds_keys = (
            'handicap',
            'odds_nspf_win', 'odds_nspf_draw', 'odds_nspf_lose',
            'odds_spf_win', 'odds_spf_draw', 'odds_spf_lose',
        )
        by_fid: Dict[str, Dict] = {}
        by_id: Dict[str, Dict] = {}
        for m in spf_matches or []:
            fid = str(m.get('fixture_id') or '').strip()
            if fid:
                by_fid[fid] = m
            mid = str(m.get('id') or '').strip()
            if mid:
                by_id[mid] = m
        merged = 0
        for m in bf_matches or []:
            src = None
            fid = str(m.get('fixture_id') or '').strip()
            if fid and fid in by_fid:
                src = by_fid[fid]
            else:
                mid = str(m.get('id') or '').strip()
                if mid and mid in by_id:
                    src = by_id[mid]
            if not src:
                continue
            changed = False
            for key in odds_keys:
                val = src.get(key)
                if val is None:
                    continue
                if m.get(key) != val:
                    m[key] = val
                    changed = True
            if src.get('is_single') is not None and m.get('is_single') is None:
                m['is_single'] = src.get('is_single')
                changed = True
            if changed:
                merged += 1
        if merged:
            logger.info("Merged SPF/NSPF odds into %s/%s BF matches", merged, len(bf_matches or []))
        return bf_matches

    def _crawl_jczq_bf(self, days_ahead: int = 7, days_back: int = 0) -> List[Dict]:
        """爬取 trade.500.com/jczq 比分页（playid=271）投注区 SP。

        days_ahead：向前（未来）采集天数；days_back：向后（历史）回补天数。
        历史回补用于「竞彩分析」历史比分列表的数据补齐。
        同窗口另拉胜平负/让球页并按 fixture_id 合并，供列表展示胜平负 SP。
        """
        from services.match_dedup import dedup_crawled_matches

        # 注意：days_ahead=0 合法（仅历史回补），不能用 `or 7`
        days_a = max(0, min(int(7 if days_ahead is None else days_ahead), 14))
        days_b = max(0, min(int(0 if days_back is None else days_back), 90))
        base = f"{self.trade_url}?playid=271&g=2"
        buckets: List[Dict] = []
        # 无 date 的默认页（与站内「比分」一致）
        buckets.extend(self._crawl_jczq_trade_url(base, extract_bf=True))
        # 向前（未来）日期
        for d in [date.today() + timedelta(days=i) for i in range(0, days_a + 1)]:
            buckets.extend(
                self._crawl_jczq_trade_url(
                    f"{base}&date={d.strftime('%Y-%m-%d')}",
                    d.strftime('%Y-%m-%d'),
                    extract_bf=True,
                )
            )
        # 向后（历史）日期：补齐「竞彩分析」历史比分列表
        for d in [date.today() - timedelta(days=i) for i in range(1, days_b + 1)]:
            buckets.extend(
                self._crawl_jczq_trade_url(
                    f"{base}&date={d.strftime('%Y-%m-%d')}",
                    d.strftime('%Y-%m-%d'),
                    extract_bf=True,
                )
            )
        combined = dedup_crawled_matches(buckets)
        # 比分玩法以有 odds_bf_json 为准；去重后丢弃空投注区
        combined = [m for m in combined if m.get('odds_bf_json')]
        # 比分页本身无胜平负按钮；同日期窗口拉 SPF 页合并
        try:
            spf = self._crawl_jczq_trade(days_ahead=days_a, days_back=days_b)
            combined = self._merge_spf_into_bf(combined, spf)
        except Exception as e:
            logger.warning("Merge SPF into BF skipped: %s", e)
        logger.info(
            "Crawled %s unique jingcai BF matches (days_ahead=%s, days_back=%s, raw=%s)",
            len(combined), days_a, days_b, len(buckets),
        )
        return combined

    def _crawl_jczq_trade_url(
        self, url: str, date_str: str = None, extract_bf: bool = False
    ) -> List[Dict]:
        matches = []
        try:
            r = self.session.get(url, timeout=30)
            try:
                text = r.content.decode('gbk', errors='replace')
            except Exception:
                text = r.content.decode('utf-8', errors='replace')
            soup = BeautifulSoup(text, 'html.parser')
            for tr in soup.select('table.bet-tb tr.bet-tb-tr'):
                item = self._parse_trade_match_row(tr, date_str, extract_bf=extract_bf)
                if item:
                    matches.append(item)
            logger.info("Crawled %s matches from %s", len(matches), url)
        except Exception as e:
            logger.warning("Jingcai trade crawl failed (%s): %s", url, e)
        return matches

    def _crawl_by_date(self, date_str: str) -> List[Dict]:
        """赛果回查：胜平负/让球页按销售日拉取（含完赛比分）。"""
        return self._crawl_jczq_trade_url(
            f'{self.trade_url}?playid=269&g=2&date={date_str}',
            date_str,
        )

    def _parse_match_row(self, tr) -> Optional[Dict]:
        try:
            tds = tr.find_all('td')
            if len(tds) < 8:
                return None
            
            match_num = tds[0].text.strip()
            league_name = tds[1].text.strip()
            round_name = tds[2].text.strip()
            match_time_str = tds[3].text.strip()
            status = tds[4].text.strip()
            home_team_raw = tds[5].text.strip()
            score = tds[6].text.strip()
            away_team_raw = tds[7].text.strip()
            
            home_team_name = self._clean_team_name(home_team_raw)
            away_team_name = self._clean_team_name(away_team_raw)
            
            home_team_id = self._map_team_name(home_team_name)
            away_team_id = self._map_team_name(away_team_name)
            
            if not home_team_id or not away_team_id:
                return None
            
            league_id = self._map_league_name(league_name)
            if not league_id or league_id == 'OTHER':
                return None
            
            if match_time_str:
                match_date, match_time = self._parse_md_datetime(match_time_str)
            else:
                match_date = date.today()
                match_time = time(15, 0)
            
            match_id = f"{league_id}-{match_date.strftime('%Y-%m-%d')}-{home_team_id}-{away_team_id}"
            
            home_goals = 0
            away_goals = 0
            result = None
            
            if score and score != '-':
                score_parts = score.split(':')
                if len(score_parts) == 2:
                    home_goals = int(score_parts[0])
                    away_goals = int(score_parts[1])
                    if home_goals > away_goals:
                        result = 'H'
                    elif home_goals < away_goals:
                        result = 'A'
                    else:
                        result = 'D'
            
            match_status = 'upcoming'
            if status == '完' or status == '胜' or status == '负' or status == '平':
                match_status = 'finished'
            elif status == '进' or status == '中':
                match_status = 'live'
            
            stage = self._determine_stage(league_id, round_name)
            
            return {
                'id': match_id,
                'league_id': league_id,
                'league_name': league_name,
                'home_team_id': home_team_id,
                'home_team_name': home_team_name,
                'away_team_id': away_team_id,
                'away_team_name': away_team_name,
                'match_date': match_date,
                'match_time': match_time,
                'venue': '',
                'status': match_status,
                'home_goals': home_goals,
                'away_goals': away_goals,
                'result': result,
                'weather': '',
                'temperature': '',
                'pitch_condition': '',
                'stage': stage,
                'group_name': None,
                'round_name': round_name,
            }
            
        except Exception as e:
            logger.error(f"Failed to parse match row: {str(e)}")
            return None

    def _parse_trade_match_row(self, tr, date_str: str = None, extract_bf: bool = False) -> Optional[Dict]:
        try:
            tds = tr.find_all('td', recursive=False)
            if len(tds) < 4:
                # 畸形嵌套时退回全部 td（仍需能读到对阵列）
                tds = tr.find_all('td')
            if len(tds) < 4:
                return None

            league_name = (tr.get('data-simpleleague') or tds[1].text.strip() or '').strip()
            match_time_str = tr.get('data-matchtime') or tds[2].text.strip()
            vs_text = tds[3].get_text(' ', strip=True)
            if '编号' in (tds[0].text or '') or ('VS' not in vs_text.upper() and 'vs' not in vs_text):
                # 已完赛可能显示比分而非 VS
                home_team_name = (tr.get('data-homesxname') or '').strip()
                away_team_name = (tr.get('data-awaysxname') or '').strip()
                if not home_team_name or not away_team_name:
                    return None
            else:
                home_team_name, away_team_name = self._split_vs(vs_text)
                home_team_name = (tr.get('data-homesxname') or home_team_name or '').strip()
                away_team_name = (tr.get('data-awaysxname') or away_team_name or '').strip()
            if not home_team_name or not away_team_name:
                return None

            league_id = self._map_league_from_trade_row(tr, tds, league_name)
            if not league_id:
                logger.debug("Skip jingcai row: unmapped league %s", league_name)
                return None

            home_team_name = self._clean_team_name(home_team_name)
            away_team_name = self._clean_team_name(away_team_name)
            # 优先 500 team id（T{id}），入库时再 remap 到本库规范 ID；避免「中国女→CHN」等误伤
            home_team_id = self._five00_team_id(tr.get('data-homeid')) or self._map_team_name(home_team_name)
            away_team_id = self._five00_team_id(tr.get('data-awayid')) or self._map_team_name(away_team_name)
            if not home_team_id or not away_team_id:
                logger.debug(
                    "Skip jingcai row: unmapped teams %s vs %s (%s)",
                    home_team_name, away_team_name, league_name,
                )
                return None

            process_date = tr.get('data-processdate') or date_str
            match_date_attr = tr.get('data-matchdate')
            if match_date_attr and match_time_str and ':' in match_time_str and '-' not in match_time_str:
                match_date, match_time = self._parse_md_datetime(
                    f"{match_date_attr} {match_time_str}", process_date
                )
            else:
                match_date, match_time = self._parse_md_datetime(match_time_str, process_date)

            is_end = str(tr.get('data-isend') or '0') == '1'
            score_el = None
            for td in tds:
                score_el = td.select_one('.team-bf, a.team-bf')
                if score_el:
                    break
            home_goals, away_goals, result = None, None, None
            status = 'finished' if is_end else 'upcoming'
            if score_el:
                score_txt = score_el.get_text(strip=True)
                if ':' in score_txt:
                    parts = score_txt.split(':')
                    try:
                        home_goals = int(parts[0])
                        away_goals = int(parts[1])
                        status = 'finished'
                        result = 'H' if home_goals > away_goals else ('A' if home_goals < away_goals else 'D')
                    except ValueError:
                        pass
                elif score_txt in ('VS', 'vs', '-', ''):
                    if not is_end:
                        status = 'upcoming'

            odds = {} if extract_bf else self._extract_trade_odds(tr)
            handicap_raw = tr.get('data-rangqiu')
            handicap = None
            if handicap_raw not in (None, ''):
                try:
                    handicap = int(float(handicap_raw))
                except ValueError:
                    handicap = None

            odds_bf_json = None
            if extract_bf:
                bf_map = self._extract_bf_odds(tr)
                if not bf_map:
                    return None
                import json as _json
                odds_bf_json = _json.dumps(bf_map, ensure_ascii=False, separators=(',', ':'))

            match_id = f"{league_id}-{match_date.strftime('%Y-%m-%d')}-{home_team_id}-{away_team_id}"
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
                'stage': self._determine_stage(league_id, ''),
                'group_name': None,
                'round_name': (tr.get('data-matchnum') or tds[0].text.strip())[:20],
                'fixture_id': tr.get('data-fixtureid') or None,
                'process_id': tr.get('data-processid') or None,
                'handicap': handicap,
                'odds_nspf_win': odds.get('nspf_win'),
                'odds_nspf_draw': odds.get('nspf_draw'),
                'odds_nspf_lose': odds.get('nspf_lose'),
                'odds_spf_win': odds.get('spf_win'),
                'odds_spf_draw': odds.get('spf_draw'),
                'odds_spf_lose': odds.get('spf_lose'),
                'odds_bf_json': odds_bf_json,
                'is_single': str(tr.get('data-kdg') or '') == '1',
                'buy_end_time': tr.get('data-buyendtime') or None,
                'source': '500_trade_bf' if extract_bf else '500_trade',
            }
        except Exception as e:
            logger.error("Failed to parse trade match row: %s", e)
            return None

    def _find_bf_wrap(self, tr):
        """定位本场比分投注区行（源站 HTML 常缺 </tr>，wrap 会被解析为子节点）。"""
        for child in tr.children:
            if getattr(child, 'name', None) != 'tr':
                continue
            classes = child.get('class') or []
            if 'bet-more-wrap' in classes:
                return child
            if 'bet-tb-tr' in classes:
                return None
        nxt = tr.find_next_sibling('tr')
        if nxt and 'bet-more-wrap' in (nxt.get('class') or []):
            return nxt
        return None

    def _extract_bf_odds(self, tr) -> Optional[dict]:
        """从比分页展开区提取 31 项比分 SP。"""
        wrap = self._find_bf_wrap(tr)
        if not wrap:
            return None
        container = wrap.select_one('div.bet-more') or wrap
        out = {}
        for btn in container.select('p.sbetbtn[data-type="bf"]'):
            dval = (btn.get('data-value') or '').strip()
            sp = btn.get('data-sp')
            if not dval or sp in (None, '', '-', '未开售'):
                continue
            try:
                val = float(sp)
            except (TypeError, ValueError):
                continue
            if val <= 0:
                continue
            out[dval] = val
        return out or None

    def _five00_team_id(self, raw_id) -> Optional[str]:
        """500 data-homeid/awayid → 规范 T{id}（可入库的干净 ID）。"""
        if raw_id in (None, ''):
            return None
        digits = re.sub(r'\D', '', str(raw_id))
        if len(digits) < 2:
            return None
        return f"T{digits}"[:20]

    def _map_league_from_trade_row(self, tr, tds, league_name: str) -> Optional[str]:
        """优先 zuqiu-XXXX → FIVE00_TO_CANONICAL / LSXXXX，再回退中文名映射。"""
        href = ''
        try:
            a = tds[1].find('a', href=True) if len(tds) > 1 else None
            if a:
                href = a.get('href') or ''
        except Exception:
            href = ''
        m = re.search(r'zuqiu-(\d+)', href or '')
        if m:
            ls_id = f"LS{m.group(1)}"
            try:
                from services.real_team_crawler import FIVE00_TO_CANONICAL
                return FIVE00_TO_CANONICAL.get(ls_id, ls_id)[:20]
            except Exception:
                return ls_id[:20]
        mapped = self._map_league_name(league_name)
        if mapped and mapped != 'OTHER':
            return mapped[:20]
        return None

    def _extract_trade_odds(self, tr) -> dict:
        """从 betbtn 提取胜平负 / 让球胜平负 SP（未开售则缺对应字段）。"""
        out = {}
        value_map = {'3': 'win', '1': 'draw', '0': 'lose'}
        # 仅扫本行直系单元格，避免嵌套 HTML 把后续场次的按钮算进来
        scope_tds = tr.find_all('td', recursive=False) or tr.find_all('td')
        buttons = []
        for td in scope_tds:
            buttons.extend(td.select('p.betbtn[data-type][data-value]'))
        if not buttons:
            buttons = tr.select('p.betbtn[data-type][data-value]')
        for btn in buttons:
            dtype = (btn.get('data-type') or '').strip()
            dval = (btn.get('data-value') or '').strip()
            sp = btn.get('data-sp')
            if dtype not in ('nspf', 'spf') or dval not in value_map:
                continue
            if sp in (None, '', '-', '未开售'):
                continue
            try:
                val = float(sp)
            except (TypeError, ValueError):
                continue
            if val <= 0:
                continue
            out[f"{dtype}_{value_map[dval]}"] = val
        return out

    def _split_vs(self, vs_text: str) -> tuple:
        text = self._clean_team_name(vs_text or '')
        for sep in (' VS ', ' vs ', 'VS', 'vs'):
            if sep in text:
                home, away = text.split(sep, 1)
                return home.strip(), away.strip()
        parts = [p.strip() for p in text.split() if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[-1]
        return '', ''

    def _parse_md_datetime(self, raw: str, year_hint: str = None) -> tuple:
        raw = (raw or '').strip()
        today = date.today()
        year = today.year
        if year_hint and re.match(r'\d{4}-\d{2}-\d{2}', year_hint):
            year = int(year_hint[:4])
        try:
            if re.match(r'\d{4}-\d{1,2}-\d{1,2}', raw):
                dt_part, tm_part = (raw.split(' ', 1) + ['15:00'])[:2]
                y, mo, da = [int(x) for x in dt_part.split('-')[:3]]
                hh, mm = [int(x) for x in tm_part.split(':')[:2]]
                return date(y, mo, da), time(hh, mm)
            date_part, time_part = (raw.split(' ', 1) + ['15:00'])[:2]
            mo, da = [int(x) for x in date_part.split('-')[:2]]
            hh, mm = [int(x) for x in time_part.split(':')[:2]]
            parsed = date(year, mo, da)
            if parsed < today - timedelta(days=120):
                parsed = date(year + 1, mo, da)
            elif parsed > today + timedelta(days=240):
                parsed = date(year - 1, mo, da)
            return parsed, time(hh, mm)
        except Exception:
            return today, time(15, 0)

    def _clean_team_name(self, raw_name: str) -> str:
        from services.real_team_crawler import normalize_team_display_name
        return normalize_team_display_name(raw_name)

    def _extract_score(self, home_raw: str, away_raw: str) -> Optional[tuple]:
        return None

    def _map_team_name(self, team_name: str) -> Optional[str]:
        """优先 TEAM_ALIASES（与球队采集同源），再回退本地短表；禁止生成中文脏 ID。"""
        if not team_name:
            return None
        from services.real_team_crawler import resolve_team_alias, is_clean_team_id

        cleaned = self._clean_team_name(team_name)
        alias = resolve_team_alias(cleaned) or resolve_team_alias(team_name)
        if alias and is_clean_team_id(alias):
            return alias

        best_tid = None
        best_len = -1
        hay = cleaned or team_name
        for name, tid in self.team_name_mapping.items():
            if name in hay or hay in name:
                if len(name) > best_len:
                    best_len = len(name)
                    best_tid = tid
        if best_tid and is_clean_team_id(best_tid):
            return best_tid
        return None

    def _generate_team_id(self, team_name: str) -> Optional[str]:
        """已废弃：不再用中文名生成球队 ID。保留方法仅返回 None。"""
        return None

    def _map_league_name(self, league_name: str) -> str:
        for name, lid in self.league_name_mapping.items():
            if name in league_name:
                return lid
        return 'OTHER'

    def _determine_stage(self, league_id: str, round_name: str) -> str:
        if league_id == 'WC':
            if '决赛' in round_name:
                return 'final'
            elif '半决赛' in round_name:
                return 'semi_final'
            elif '三四名' in round_name:
                return 'third_place'
            elif '四分之一' in round_name or '1/4' in round_name:
                return 'quarter_final'
            elif '十六强' in round_name or '1/8' in round_name:
                return 'round_of_16'
            elif '小组赛' in round_name:
                return 'group'
            return 'final'
        
        if league_id in ['EC', 'CA', 'AFC']:
            if '决赛' in round_name:
                return 'final'
            elif '半决赛' in round_name:
                return 'semi_final'
            elif '三四名' in round_name:
                return 'third_place'
            elif '四分之一' in round_name or '1/4' in round_name:
                return 'quarter_final'
            elif '十六强' in round_name or '1/8' in round_name:
                return 'round_of_16'
            elif '小组赛' in round_name:
                return 'group'
            return 'league'
        
        return 'league'
