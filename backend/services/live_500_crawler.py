import logging
import re
from datetime import date, time, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class Live500MatchCrawler:
    def __init__(self):
        self.base_url = 'https://live.500.com/2h1.php'
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

        self.team_name_mapping = {
            '曼联': 'MUN', '曼城': 'MCI', '利物浦': 'LIV', '阿森纳': 'ARS',
            '切尔西': 'CHE', '热刺': 'TOT', '纽卡斯尔': 'NEW', '布莱顿': 'BHA',
            '阿斯顿维拉': 'AVL', '埃弗顿': 'EVE', '西汉姆': 'WHU', '富勒姆': 'FUL',
            '水晶宫': 'CRY', '狼队': 'WOL', '伯恩茅斯': 'BOU', '布伦特福德': 'BRE',
            '诺丁汉森林': 'NFO', '南安普顿': 'SOU', '利兹联': 'LEE', '莱斯特': 'LEI',
            '皇马': 'RMA', '巴萨': 'BAR', '马竞': 'ATM', '瓦伦西亚': 'VAL',
            '塞维利亚': 'SEV', '比利亚雷亚尔': 'VIL', '皇家社会': 'REAL_SOC', '毕尔巴鄂': 'BIL',
            '赫塔费': 'GET', '塞尔塔': 'CEL', '加的斯': 'CAD', '奥萨苏纳': 'OSA',
            '马洛卡': 'MLL', '格拉纳达': 'GRA', '巴列卡诺': 'RVA',
            '拜仁': 'BAY', '多特': 'DOR', '勒沃库森': 'LEV', '沃尔夫斯堡': 'WOLF',
            '法兰克福': 'FRA', '霍芬海姆': 'HOF', '斯图加特': 'SCF', '弗赖堡': 'FRE',
            '门兴': 'MG', '柏林联合': 'UNB', '科隆': 'KOL', '奥格斯堡': 'AUG',
            '波鸿': 'BOH', '美因茨': 'MAI', '沙尔克': 'S04', '柏林赫塔': 'BSC',
            '国米': 'INT', '尤文': 'JUV', 'AC米兰': 'MIL', '那不勒斯': 'NAP',
            '拉齐奥': 'LAZ', '罗马': 'ROMA', '亚特兰大': 'ATL', '佛罗伦萨': 'FIO',
            '都灵': 'TOR', '博洛尼亚': 'BOL', '维罗纳': 'VER', '萨索洛': 'SAS',
            '恩波利': 'EMP', '乌迪内斯': 'UDI', '热那亚': 'GEN', '蒙扎': 'MON',
            '巴黎': 'PSG', '里尔': 'LIL', '马赛': 'MAR', '雷恩': 'REN',
            '里昂': 'LYO', '摩纳哥': 'MON', '尼斯': 'NIC', '斯特拉斯堡': 'STR',
            '兰斯': 'REI', '南特': 'NTE', '布雷斯特': 'BES', '洛里昂': 'LOR',
            '巴西': 'BRA', '阿根廷': 'ARG', '德国': 'GER', '法国': 'FRA',
            '西班牙': 'ESP', '葡萄牙': 'POR', '比利时': 'BEL', '荷兰': 'NED',
            '意大利': 'ITA', '英格兰': 'ENG', '克罗地亚': 'CRO', '乌拉圭': 'URU',
            '瑞士': 'SUI', '美国': 'USA', '墨西哥': 'MEX', '哥伦比亚': 'COL',
            '智利': 'CHI', '厄瓜多尔': 'ECU', '日本': 'JPN', '韩国': 'KOR',
            '澳大利亚': 'AUS', '伊朗': 'IRN', '沙特': 'SAU', '卡塔尔': 'QAT',
            '泰国': 'THA', '阿联酋': 'UAE', '中国': 'CHN', '南非': 'RSA',
            '捷克': 'CZE', '加拿大': 'CAN', '波黑': 'BIH', '摩洛哥': 'MAR',
            '苏格兰': 'SCO', '海地': 'HAI', '巴拉圭': 'PAR', '土耳其': 'TUR',
            '科特迪瓦': 'CIV', '库拉索': 'CUR', '瑞典': 'SWE', '突尼斯': 'TUN',
            '埃及': 'EGY', '新西兰': 'NZL', '佛得角': 'CPV', '挪威': 'NOR',
            '塞内加尔': 'SEN', '伊拉克': 'IRQ', '奥地利': 'AUT', '阿尔及利亚': 'ALG',
            '约旦': 'JOR', '民主刚果': 'COD', '乌兹别克斯坦': 'UZB', '加纳': 'GHA',
            '巴拿马': 'PAN',
        }

        self.league_name_mapping = {
            '英超': 'EPL', '西甲': 'LALIGA', '德甲': 'BUNDES', '意甲': 'SERIEA',
            '法甲': 'LIGUE1', '世界杯': 'WC', '欧冠': 'UCL', '欧联': 'UEL',
            '欧洲杯': 'EC', '美洲杯': 'CA', '亚洲杯': 'AFC', 'K1联赛': 'K1',
            'K2联赛': 'K2', '瑞典超': 'SWE', '芬超': 'FIN', '韩职': 'K1',
            '韩女联': 'WK1', '挪超': 'NOR', '巴甲': 'BRA', '美职足': 'MLS',
            '澳超': 'AUS', '澳维超': 'VIC', '澳维甲': 'VIC_A', '澳维U23': 'VIC_U23',
            '澳维女超': 'VIC_W', '澳威超': 'NSW', '澳昆乙': 'QLD_B', '澳南甲': 'SA',
            '俄超': 'RUS', '俄乙': 'RUS_B', '俄乙B': 'RUS_B2', '俄青联': 'RUS_Y',
            '波甲': 'POL', '波乙': 'POL_B', '波兰丙': 'POL_C',
            '捷克杯': 'CZE_CUP', '捷克乙': 'CZE_B',
            '罗甲': 'ROM', '保超': 'BUL', '保乙': 'BUL_B',
            '丹超': 'DEN', '丹甲': 'DEN_A',
            '奥甲': 'AUT', '奥地利杯': 'AUT_CUP',
            '瑞士超': 'SUI', '瑞士挑': 'SUI_CH',
            '匈甲': 'HUN', '马其甲': 'MKD',
            '立陶乙': 'LTU_B', '立甲': 'LTU',
            '爱沙杯': 'EST_CUP', '爱甲': 'IRE_A', '爱超': 'IRE',
            '冰超': 'ISL', '冰甲': 'ISL_A', '冰岛乙': 'ISL_B', '冰女杯': 'ISL_WC', '冰女甲': 'ISL_W',
            '芬乙': 'FIN_B',
            '球会友谊': 'FRIENDLY', '友谊赛': 'FRIENDLY',
            '越女联': 'VIE_W', '乌女超': 'UKR_W',
            '哈甲': 'KAZ', '乌兹甲': 'UZB',
            '东南锦': 'SEA', '澳门甲': 'MAC', '黎巴联': 'LIB', '也门甲': 'YEM',
            '中东非俱': 'CAF_CL', '危地甲': 'GUA',
            '智甲': 'CHI', '智乙': 'CHI_B',
            '墨西乙': 'MEX_B', '尼拉甲': 'NCA', '巴马甲': 'PAN_A', '萨尔超': 'SLV', '哥斯甲': 'CRC',
            '巴拉联': 'PAR', '巴拉乙': 'PAR_B', '厄乙': 'ECU_B',
            '秘鲁甲': 'PER', '秘鲁乙': 'PER_B',
            '哥伦甲': 'COL', '哥伦乙': 'COL_B', '哥伦女足': 'COL_W',
            '阿甲': 'ARG', '阿业余': 'ARG_A',
            '美乙2': 'USL2', '美冠': 'USLC', '美女职': 'NWSL',
            'COTIF杯': 'COTIF',
            '不丹超': 'BHU',
            '乌拉超': 'URU', '玻甲联': 'BOL',
            '秘女联': 'PER_W', '巴女甲': 'BRA_W', '巴女乙': 'BRA_WB',
            '美青杯': 'CONCACAF_Y', '加拿职': 'CPL',
        }

    def crawl(self, league_id: str = None, days_ahead: int = 7) -> List[Dict]:
        matches = self._crawl_live_data()
        filtered_matches = []
        for match in matches:
            mapped_league_id = match.get('league_id', '')
            if league_id is None or league_id == 'all' or mapped_league_id == league_id:
                filtered_matches.append(match)
        logger.info(f"Live500 crawler generated {len(filtered_matches)} matches")
        return filtered_matches

    def crawl_historical(self, league_id: str = None, days_back: int = 30, start_date: date = None) -> List[Dict]:
        matches = self._crawl_live_data()
        today = date.today()
        filtered_matches = []
        for match in matches:
            match_date = match.get('match_date')
            if match_date and match_date < today:
                if league_id is None or league_id == 'all' or match.get('league_id') == league_id:
                    filtered_matches.append(match)
        logger.info(f"Live500 crawler generated {len(filtered_matches)} historical matches")
        return filtered_matches

    def _crawl_live_data(self) -> List[Dict]:
        matches = []
        try:
            r = self.session.get(self.base_url, timeout=30)
            try:
                text = r.content.decode('gbk', errors='replace')
            except:
                text = r.content.decode('utf-8', errors='replace')

            soup = BeautifulSoup(text, 'html.parser')
            table = soup.find('table', class_='bf_tablelist01')
            if not table:
                logger.warning("No table found with class 'bf_tablelist01'")
                return matches

            all_rows = table.find_all('tr')
            if len(all_rows) <= 1:
                logger.warning("No data rows found")
                return matches

            match_rows = all_rows[1:]

            for row in match_rows:
                match_data = self._parse_match_row(row)
                if match_data:
                    matches.append(match_data)

            logger.info(f"Crawled {len(matches)} matches from live.500.com/2h1.php")
        except Exception as e:
            logger.error(f"Failed to crawl live.500.com/2h1.php: {str(e)}")

        return matches

    def _parse_match_row(self, row) -> Optional[Dict]:
        try:
            tds = row.find_all('td')
            if len(tds) < 8:
                return None

            league_name = tds[1].text.strip() if len(tds) > 1 else ''

            round_td = tds[2].text.strip() if len(tds) > 2 else ''

            time_td = tds[3].text.strip() if len(tds) > 3 else ''

            status_td = tds[4].text.strip() if len(tds) > 4 else ''

            home_team_raw = tds[5].text.strip() if len(tds) > 5 else ''
            score_text = tds[6].text.strip() if len(tds) > 6 else ''
            away_team_raw = tds[7].text.strip() if len(tds) > 7 else ''
            half_score = tds[8].text.strip() if len(tds) > 8 else ''

            home_team_name = self._clean_team_name(home_team_raw)
            away_team_name = self._clean_team_name(away_team_raw)

            home_team_id = self._map_team_name(home_team_name)
            away_team_id = self._map_team_name(away_team_name)

            if not home_team_id:
                home_team_id = self._generate_team_id(home_team_name)
            if not away_team_id:
                away_team_id = self._generate_team_id(away_team_name)

            league_id = self._map_league_name(league_name)

            match_date, match_time = self._parse_match_time(time_td)

            home_goals, away_goals, result = self._parse_score(score_text)

            match_status = self._determine_status(status_td, score_text)

            stage = self._determine_stage(league_id, round_td)

            match_id = f"LIVE500-{league_id}-{match_date.strftime('%Y-%m-%d')}-{home_team_id}-{away_team_id}"

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
                'round_name': round_td,
                'half_score': half_score,
            }

        except Exception as e:
            logger.error(f"Failed to parse match row: {str(e)}")
            return None

    def _clean_team_name(self, raw_name: str) -> str:
        name = re.sub(r'\[\d+\]', '', raw_name)
        name = re.sub(r'\(\+\d+\)', '', name)
        name = re.sub(r'\(-\d+\)', '', name)
        name = re.sub(r'\d+\s*', '', name)
        name = name.strip()
        return name

    def _parse_match_time(self, time_str: str) -> tuple:
        today = date.today()
        default_time = time(15, 0)

        if not time_str:
            return today, default_time

        try:
            if re.match(r'\d{2}-\d{2}\s+\d{2}:\d{2}', time_str):
                date_part, time_part = time_str.split()
                month, day = date_part.split('-')
                hour, minute = time_part.split(':')
                year = today.year
                if int(month) > today.month:
                    year = today.year - 1
                match_date = date(year, int(month), int(day))
                match_time = time(int(hour), int(minute))
                return match_date, match_time
        except Exception:
            pass

        return today, default_time

    def _parse_score(self, score_text: str) -> tuple:
        home_goals = 0
        away_goals = 0
        result = None

        if not score_text or score_text == '-' or score_text == '--':
            return home_goals, away_goals, result

        score_text = score_text.strip()

        score_match = re.search(r'(\d+)-(\d+)', score_text)
        if score_match:
            try:
                home_goals = int(score_match.group(1))
                away_goals = int(score_match.group(2))
                if home_goals > away_goals:
                    result = 'H'
                elif home_goals < away_goals:
                    result = 'A'
                else:
                    result = 'D'
            except ValueError:
                pass

        return home_goals, away_goals, result

    def _determine_status(self, status_text: str, score_text: str) -> str:
        status_text = status_text.strip()
        if status_text in ['完', '已完场', '结束', '完场']:
            return 'finished'
        elif status_text in ['进行中', '中', '进', 'LIVE']:
            return 'live'
        elif score_text and '-' in score_text and not score_text.startswith('-'):
            return 'finished'
        else:
            return 'upcoming'

    def _map_team_name(self, team_name: str) -> Optional[str]:
        try:
            from services.team_resolver import TeamResolver
            resolved = TeamResolver.resolve_clean(team_name)
            if resolved:
                return resolved
        except Exception:
            pass
        for name, tid in self.team_name_mapping.items():
            if name in team_name or team_name in name:
                return tid
        return None

    def _generate_team_id(self, team_name: str) -> str:
        clean = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '', team_name)
        if len(clean) >= 2:
            return clean[:6].upper()
        return 'T' + str(abs(hash(team_name)))[:6].upper()

    def _map_league_name(self, league_name: str) -> str:
        for name, lid in self.league_name_mapping.items():
            if name in league_name:
                return lid
        return 'OTHER'

    def _determine_stage(self, league_id: str, round_name: str) -> str:
        round_name = round_name or ''

        if league_id in ['WC', 'EC', 'CA', 'AFC']:
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
            elif '小组赛' in round_name or '分组赛' in round_name:
                return 'group'
            return 'league'

        if '杯' in league_id or 'CUP' in league_id:
            if '决赛' in round_name:
                return 'final'
            elif '半决赛' in round_name:
                return 'semi_final'
            elif '四分之一' in round_name or '1/4' in round_name:
                return 'quarter_final'
            elif '十六强' in round_name or '1/8' in round_name:
                return 'round_of_16'
            return 'group'

        return 'league'


live_500_crawler = Live500MatchCrawler()
