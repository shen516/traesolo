"""真实球队采集

数据源（均为真实公开数据，不含模拟）：
1. 500.com 联赛站（赛程/联赛骨架主源；中文队名、fixture_id、阵容）
   https://liansai.500.com/zuqiu-{id}/…
2. ESPN Soccer API（无 500 URL 或 500 空结果时赛程兜底；球队英文/队徽、射门/伤病等）
   https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/…

赛程策略：有 `source_url` / `CANONICAL_FIVE00_URL` 主用 500 轮次；500 空且在 `ESPN_LEAGUE_MAP` 时软兜底 ESPN scoreboard。
"""
import json
import logging
import re
import time
from datetime import date, datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from services.media_crawler import MediaCrawler

logger = logging.getLogger(__name__)


# 系统内已有 ID 与中英文别名对齐，避免曼城被写成 MNC、重复建队
TEAM_ALIASES = {
    "manchester city": "MCI", "man city": "MCI", "mnc": "MCI",
    "曼城": "MCI", "曼彻斯特城": "MCI",
    "manchester united": "MUN", "man united": "MUN", "man utd": "MUN",
    "曼联": "MUN", "曼彻斯特联": "MUN",
    "arsenal": "ARS", "阿森纳": "ARS",
    "liverpool": "LIV", "利物浦": "LIV",
    "chelsea": "CHE", "切尔西": "CHE",
    "tottenham": "TOT", "热刺": "TOT", "托特纳姆热刺": "TOT",
    "aston villa": "AVL", "阿斯顿维拉": "AVL",
    "newcastle": "NEW", "纽卡斯尔": "NEW", "纽卡斯尔联": "NEW",
    "brighton": "BHA", "布莱顿": "BHA", "布赖顿": "BHA",
    "everton": "EVE", "埃弗顿": "EVE",
    "fulham": "FUL", "富勒姆": "FUL",
    "crystal palace": "CRY", "水晶宫": "CRY",
    "brentford": "BRE", "布伦特福德": "BRE",
    "bournemouth": "BOU", "伯恩茅斯": "BOU",
    "nottingham forest": "NFO", "诺丁汉森林": "NFO", "诺丁汉": "NFO",
    "west ham": "WHU", "西汉姆": "WHU",
    "wolves": "WOL", "wolverhampton": "WOL", "狼队": "WOL",
    "leeds": "LEE", "利兹联": "LEE",
    "leicester": "LEI", "莱斯特": "LEI",
    "southampton": "SOU", "南安普顿": "SOU",
    "ipswich": "IPS", "伊普斯维奇": "IPS",
    "sunderland": "SUN", "桑德兰": "SUN",
    "coventry": "COV", "考文垂": "COV",
    "hull": "HUL", "赫尔城": "HUL",
    "real madrid": "RMA", "皇马": "RMA", "皇家马德里": "RMA",
    "barcelona": "BAR", "巴萨": "BAR", "巴塞罗那": "BAR",
    "atlético madrid": "ATM", "atletico madrid": "ATM", "马竞": "ATM", "马德里竞技": "ATM",
    "athletic bilbao": "BIL", "athletic club": "BIL", "毕尔巴鄂": "BIL", "毕尔巴鄂竞技": "BIL",
    "real sociedad": "REAL_SOC", "皇家社会": "REAL_SOC",
    "rayo vallecano": "RVA", "巴列卡诺": "RVA",
    "sevilla": "SEV", "塞维利亚": "SEV",
    "celta": "CEL", "塞尔塔": "CEL",
    "getafe": "GET", "赫塔费": "GET",
    "osasuna": "OSA", "奥萨苏纳": "OSA",
    "bayern": "BAY", "拜仁": "BAY", "拜仁慕尼黑": "BAY",
    "dortmund": "DOR", "多特": "DOR", "多特蒙德": "DOR",
    "leverkusen": "LEV", "bayer leverkusen": "LEV", "勒沃库森": "LEV",
    "augsburg": "AUG", "奥格斯堡": "AUG",
    "freiburg": "FRE", "弗赖堡": "FRE",
    "hoffenheim": "HOF", "霍芬海姆": "HOF",
    "cologne": "KOL", "koln": "KOL", "köln": "KOL", "科隆": "KOL",
    "mainz": "MAI", "美因茨": "MAI",
    "gladbach": "MG", "门兴": "MG", "门兴格拉德巴赫": "MG",
    "frankfurt": "SGE", "法兰克福": "SGE",
    "union berlin": "UNB", "柏林联合": "UNB",
    "schalke": "S04", "沙尔克04": "S04",
    # 德甲升班 / 竞彩常用简称 → 库内规范 ID（勿用中文 ID）
    "hamburg": "T860", "hamburger sv": "T860", "hsv": "T860", "汉堡": "T860",
    "werder bremen": "T1334", "bremen": "T1334", "svw": "T1334",
    "不来梅": "T1334", "云达不莱梅": "T1334", "云达不来梅": "T1334",
    "paderborn": "T1922", "scp": "T1922", "帕德博恩": "T1922",
    "elversberg": "T1862", "elv": "T1862", "埃沃斯堡": "T1862", "艾禾斯堡": "T1862",
    "heidenheim": "T5315", "hdh": "T5315", "海登海姆": "T5315",
    "st pauli": "T495", "st. pauli": "T495", "stp": "T495", "圣保利": "T495",
    "bochum": "T695", "boc": "T695", "波鸿": "T695",
    "leipzig": "RBL", "rb leipzig": "RBL", "rb莱比锡": "RBL", "莱比锡": "RBL",
    "莱比锡红牛": "RBL", "莱红牛": "RBL",
    "wolfsburg": "WOB", "沃尔夫斯堡": "WOB",
    "stuttgart": "VFB", "斯图加特": "VFB",
    "ipswich": "IPS", "伊普斯维奇": "IPS", "伊普斯": "IPS",
    "sunderland": "SUN", "桑德兰": "SUN",
    "coventry": "COV", "考文垂": "COV",
    "hull": "HUL", "赫尔城": "HUL",
    "juventus": "JUV", "尤文": "JUV", "尤文图斯": "JUV",
    "inter": "INT", "internazionale": "INT", "国米": "INT", "国际米兰": "INT",
    "ac milan": "MIL", "milan": "MIL", "ac米兰": "MIL", "米兰": "MIL",
    "napoli": "NAP", "那不勒斯": "NAP",
    "roma": "ROMA", "as roma": "ROMA", "罗马": "ROMA",
    "lazio": "LAZ", "拉齐奥": "LAZ",
    "atalanta": "ATL", "亚特兰大": "ATL",
    "atlanta united": "ATLUTD", "atlanta": "ATLUTD", "亚特兰大联": "ATLUTD",
    "fiorentina": "FIO", "佛罗伦萨": "FIO",
    "bologna": "BOL", "博洛尼亚": "BOL",
    "genoa": "GEN", "热那亚": "GEN",
    "udinese": "UDI", "乌迪内斯": "UDI",
    "monza": "MNZ", "蒙扎": "MNZ",
    "sassuolo": "SAS", "萨索洛": "SAS",
    "paris saint germain": "PSG", "paris saint-germain": "PSG",
    "psg": "PSG", "巴黎": "PSG", "巴黎圣日耳曼": "PSG",
    "monaco": "ASM", "as monaco": "ASM", "摩纳哥": "ASM",
    "marseille": "OM", "马赛": "OM",
    "strasbourg": "STR", "斯特拉斯": "STR", "斯特拉斯堡": "STR",
    "lyon": "T997", "olympique lyonnais": "T997", "里昂": "T997",
    "lille": "T998", "里尔": "T998",
    "nice": "T1134", "尼斯": "T1134",
    "brest": "T1593", "布雷斯特": "T1593",
    "lens": "RCL", "朗斯": "RCL",
    "leipzig": "RBL", "rb leipzig": "RBL", "莱比锡": "RBL", "rb莱比锡": "RBL",
    "stuttgart": "VFB", "斯图加特": "VFB",
    # 欧冠常见中坚（映射到库内 T* / 规范 ID，供归并；ESPN abbr 见 ESPN_MATCH_ALIASES）
    "sporting cp": "T1000", "sporting lisbon": "T1000", "里斯本竞技": "T1000",
    "benfica": "T678", "本菲卡": "T678",
    "porto": "FCP", "fc porto": "FCP", "波尔图": "FCP",
    "ajax": "AJA", "阿贾克斯": "AJA",
    "psv": "T378", "psv eindhoven": "T378", "psv埃因霍温": "T378", "埃因霍温": "T378",
    "feyenoord": "T801", "费耶诺德": "T801",
    "club brugge": "T729", "brugge": "T729", "布鲁日": "T729",
    "celtic": "T926", "凯尔特人": "T926",
    "rangers": "T827", "格拉斯哥流浪者": "T827",
    "galatasaray": "T896", "加拉塔萨雷": "T896",
    "fenerbahce": "T797", "fenerbahçe": "T797", "费内巴切": "T797",
    "bodo/glimt": "T703", "bodo glimt": "T703", "bodø/glimt": "T703", "博德闪耀": "T703",
    "red star belgrade": "T2553", "crvena zvezda": "T2553", "贝尔格莱德红星": "T2553",
    "shakhtar": "SHK", "shakhtar donetsk": "SHK", "顿涅茨克矿工": "SHK",
    "salzburg": "T446", "rb salzburg": "T446", "萨尔茨堡红牛": "T446", "萨尔茨堡": "T446",
    "dinamo zagreb": "T448", "萨格勒布迪纳摩": "T448",
    "slavia prague": "T718", "布拉格斯拉维亚": "T718",
    "sparta prague": "T717", "布拉格斯巴达": "T717",
    "young boys": "T1177", "年轻人": "T1177",
    "olympiacos": "T616", "olympiakos": "T616", "奥林匹亚科斯": "T616",
    "lask": "T334", "lask linz": "T334", "lask林茨": "T334",
    "sturm graz": "T825", "格拉茨风暴": "T825",
    "pafos": "T2504", "帕佛斯fc": "T2504", "帕佛斯": "T2504",
    "slovan bratislava": "T1474", "布拉迪斯拉发": "T1474",
    "qarabag": "T1546", "karabakh": "T1546", "卡拉巴赫": "T1546",
    "malmo": "T1051", "malmö": "T1051", "马尔默": "T1051",
    "copenhagen": "T819", "fc copenhagen": "T819", "哥本哈根": "T819",
    "basel": "T652", "巴塞尔": "T652",
    "ferencvaros": "T798", "ferencváros": "T798", "费伦茨瓦罗斯": "T798",
    "ludogorets": "T6591", "卢多戈雷茨": "T6591",
    "dynamo kyiv": "T890", "基辅迪纳摩": "T890",
    "brazil": "BRA", "巴西": "BRA",
    "argentina": "ARG", "阿根廷": "ARG",
    "france": "FRA", "法国": "FRA",
    "england": "ENG", "英格兰": "ENG",
    "spain": "ESP", "西班牙": "ESP",
    "germany": "GER", "德国": "GER",
    "netherlands": "NED", "荷兰": "NED",
    "portugal": "POR", "葡萄牙": "POR",
    "italy": "ITA", "意大利": "ITA",
    "belgium": "BEL", "比利时": "BEL",
    "uruguay": "URU", "乌拉圭": "URU",
    "croatia": "CRO", "克罗地亚": "CRO",
    "japan": "JPN", "日本": "JPN",
    "south korea": "KOR", "korea": "KOR", "韩国": "KOR",
    "united states": "USA", "usa": "USA", "美国": "USA",
    "mexico": "MEX", "墨西哥": "MEX",
    "morocco": "MAR", "摩洛哥": "MAR",
    "senegal": "SEN", "塞内加尔": "SEN",
    "denmark": "DEN", "丹麦": "DEN",
    "switzerland": "SUI", "瑞士": "SUI",
    "deportivo": "DEP", "deportivo la coruna": "DEP", "la coruna": "DEP",
    "拉科": "DEP", "拉科鲁尼亚": "DEP",
    "cagliari": "CAG", "卡利亚里": "CAG",
    "lecce": "LEC", "莱切": "LEC",
    "como": "COM", "科莫": "COM",
    "botafogo": "BOT", "博塔弗戈": "BOT",
    "flamengo": "FLA", "弗拉门戈": "FLA",
    "st louis city": "STL", "st. louis city": "STL", "圣路易斯城": "STL",
    "fc dallas": "DAL", "dallas": "DAL", "达拉斯": "DAL",
    "valencia": "VAL", "巴伦西亚": "VAL",
    "malaga": "MAL", "马拉加": "MAL",
}


def normalize_team_display_name(name: str) -> str:
    """去掉竞彩/积分榜前缀噪声：[1]、(+0)、行首轮次数字等。"""
    if not name:
        return ""
    s = str(name).strip()
    s = re.sub(r"\[\d+\]", "", s)
    s = re.sub(r"\[\w+\]", "", s)
    s = re.sub(r"\(\+\d+\)", "", s)
    s = re.sub(r"\(-\d+\)", "", s)
    s = re.sub(r"^\d+", "", s)
    s = re.sub(r"\s+", "", s)
    return s.strip()


def is_clean_team_id(team_id: Optional[str]) -> bool:
    """规范球队 ID：ASCII 字母数字下划线，或 T/ESPN/PE + 数字；禁止中文/行首数字脏 ID。"""
    if not team_id:
        return False
    s = str(team_id).strip()
    if any("\u4e00" <= c <= "\u9fff" for c in s):
        return False
    if s[:1].isdigit():
        return False
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,19}", s):
        return True
    if re.fullmatch(r"T\d{2,}", s):
        return True
    if re.fullmatch(r"ESPN\d+", s):
        return True
    if re.fullmatch(r"PE\d+", s):
        return True
    return False


def resolve_team_alias(name: str) -> Optional[str]:
    """中英文队名 → 系统规范球队 ID（TEAM_ALIASES + 已确认 DB 别名）。"""
    if not name:
        return None
    raw = str(name).strip()
    cleaned = normalize_team_display_name(raw)
    for candidate in (raw, cleaned):
        if not candidate:
            continue
        key = candidate.lower()
        if key in TEAM_ALIASES:
            return TEAM_ALIASES[key]
        compact = re.sub(r"[\s\-\.·]", "", key)
        if compact in TEAM_ALIASES:
            return TEAM_ALIASES[compact]
    try:
        from services.team_alias_service import lookup_confirmed_team_id
        db_hit = lookup_confirmed_team_id(raw) or lookup_confirmed_team_id(cleaned)
        if db_hit:
            return db_hit
    except Exception:
        pass
    # 最长子串匹配（避免「法」误伤）
    best_tid = None
    best_len = 0
    hay = cleaned.lower() if cleaned else raw.lower()
    for alias, tid in TEAM_ALIASES.items():
        if len(alias) < 2:
            continue
        if alias in hay or hay in alias:
            if len(alias) > best_len:
                best_len = len(alias)
                best_tid = tid
    return best_tid


# 仅用于 ESPN 对阵匹配的名称 → ESPN abbreviation（可与系统球队 ID 不同，如曼联 MUN→MAN、拜仁 BAY→MUN）
ESPN_MATCH_ALIASES = {
    # EPL 差异
    "mun": "MAN", "manchester united": "MAN", "man united": "MAN", "man utd": "MAN",
    "曼联": "MAN", "曼彻斯特联": "MAN",
    "mci": "MNC", "manchester city": "MNC", "man city": "MNC", "曼城": "MNC", "曼彻斯特城": "MNC",
    # 德甲
    "bay": "MUN", "bayern": "MUN", "bayern munich": "MUN", "拜仁": "MUN", "拜仁慕尼黑": "MUN",
    "dor": "DOR", "dortmund": "DOR", "多特": "DOR", "多特蒙德": "DOR",
    "lev": "B04", "leverkusen": "B04", "bayer leverkusen": "B04", "勒沃库森": "B04",
    "rbl": "RBL", "leipzig": "RBL", "rb leipzig": "RBL", "rb莱比锡": "RBL", "莱红牛": "RBL", "莱比锡": "RBL",
    "vfb": "VFB", "stuttgart": "VFB", "斯图加特": "VFB",
    "wob": "WOB", "wolfsburg": "WOB", "沃尔夫斯堡": "WOB",
    "sge": "SGE", "frankfurt": "SGE", "eintracht frankfurt": "SGE", "法兰克福": "SGE",
    "scf": "SCF", "fre": "SCF", "freiburg": "SCF", "弗赖堡": "SCF",
    "tsg": "TSG", "hof": "TSG", "hoffenheim": "TSG", "霍芬海姆": "TSG",
    "m05": "M05", "mai": "M05", "mainz": "M05", "美因茨": "M05",
    "bmg": "BMG", "mg": "BMG", "gladbach": "BMG", "门兴": "BMG", "门兴格拉德巴赫": "BMG",
    "fcu": "FCU", "unb": "FCU", "union berlin": "FCU", "柏林联合": "FCU",
    "fca": "FCA", "aug": "FCA", "augsburg": "FCA", "奥格斯堡": "FCA",
    "svw": "SVW", "bremen": "SVW", "werder bremen": "SVW", "不来梅": "SVW", "云达不莱梅": "SVW",
    "koe": "KOE", "kol": "KOE", "cologne": "KOE", "科隆": "KOE",
    "s04": "S04", "schalke": "S04", "沙尔克04": "S04",
    "hsv": "HSV", "hamburg": "HSV", "汉堡": "HSV",
    "boc": "BOC", "bochum": "BOC", "波鸿": "BOC",
    "hdh": "HDH", "heidenheim": "HDH", "海登海姆": "HDH",
    "stp": "STP", "st pauli": "STP", "圣保利": "STP",
    "scp": "SCP", "paderborn": "SCP", "帕德博恩": "SCP",
    "elv": "ELV", "elversberg": "ELV", "艾禾斯堡": "ELV", "埃沃斯堡": "ELV",
    # 西甲
    "ala": "ALA", "alaves": "ALA", "alavés": "ALA", "阿拉维斯": "ALA",
    "ath": "ATH", "bil": "ATH", "bilbao": "ATH", "athletic": "ATH", "athletic club": "ATH",
    "毕尔巴鄂": "ATH", "毕尔巴鄂竞技": "ATH",
    "atm": "ATM", "马竞": "ATM", "马德里竞技": "ATM",
    "bar": "BAR", "barcelona": "BAR", "巴萨": "BAR", "巴塞罗那": "BAR",
    "cel": "CEL", "celta": "CEL", "塞尔塔": "CEL", "维戈塞尔塔": "CEL",
    "get": "GET", "getafe": "GET", "赫塔费": "GET", "赫塔菲": "GET",
    "gir": "GIR", "girona": "GIR", "赫罗纳": "GIR",
    "levante": "LEV", "莱万特": "LEV",
    "mll": "MLL", "mallorca": "MLL", "马洛卡": "MLL", "马略卡": "MLL",
    "osa": "OSA", "osasuna": "OSA", "奥萨苏纳": "OSA",
    "ray": "RAY", "rva": "RAY", "rayo": "RAY", "巴列卡诺": "RAY",
    "bet": "BET", "betis": "BET", "real betis": "BET", "皇家贝蒂斯": "BET", "贝蒂斯": "BET",
    "rma": "RMA", "real madrid": "RMA", "皇马": "RMA", "皇家马德里": "RMA",
    "rso": "RSO", "real_soc": "RSO", "real sociedad": "RSO", "皇家社会": "RSO",
    "sev": "SEV", "sevilla": "SEV", "塞维利亚": "SEV",
    "val": "VAL", "valencia": "VAL", "瓦伦西亚": "VAL", "巴伦西亚": "VAL",
    "vil": "VIL", "villarreal": "VIL", "比利亚雷亚尔": "VIL",
    "espanyol": "ESP", "西班牙人": "ESP",
    "elc": "ELC", "elche": "ELC", "埃尔切": "ELC",
    "mcf": "MCF", "malaga": "MCF", "马拉加": "MCF",
    "vll": "VLL", "valladolid": "VLL", "巴利亚多利德": "VLL",
    "lpa": "LPA", "las palmas": "LPA", "拉斯帕尔马斯": "LPA",
    "leg": "LEG", "leganes": "LEG", "莱加内斯": "LEG",
    "rov": "ROV", "oviedo": "ROV", "皇家奥维耶多": "ROV",
    "rac": "RAC", "racing santander": "RAC", "桑坦德竞技": "RAC",
    "dep": "DEP", "deportivo": "DEP", "拉科鲁尼亚": "DEP", "拉科": "DEP",
    # 意甲
    "nap": "NAP", "napoli": "NAP", "那不勒斯": "NAP",
    "roma": "ROMA", "as roma": "ROMA", "罗马": "ROMA",
    "laz": "LAZ", "lazio": "LAZ", "拉齐奥": "LAZ",
    "ata": "ATA", "atl": "ATA", "atalanta": "ATA", "亚特兰大": "ATA",
    "fio": "FIO", "fiorentina": "FIO", "佛罗伦萨": "FIO",
    "bol": "BOL", "bologna": "BOL", "博洛尼亚": "BOL",
    "tor": "TOR", "torino": "TOR", "都灵": "TOR",
    "gen": "GEN", "genoa": "GEN", "热那亚": "GEN",
    "udi": "UDI", "udinese": "UDI", "乌迪内斯": "UDI",
    "cag": "CAG", "cagliari": "CAG", "卡利亚里": "CAG",
    "emp": "EMP", "empoli": "EMP", "恩波利": "EMP",
    "mnz": "MON", "monza": "MON", "蒙扎": "MON",
    "lec": "LEC", "lecce": "LEC", "莱切": "LEC",
    "hel": "HEL", "verona": "HEL", "维罗纳": "HEL",
    "par": "PAR", "parma": "PAR", "帕尔马": "PAR",
    "como": "COMO", "科莫": "COMO",
    "ven": "VEN", "venezia": "VEN", "威尼斯": "VEN",
    "sas": "SAS", "sassuolo": "SAS", "萨索洛": "SAS",
    "cre": "CRE", "cremonese": "CRE", "克雷莫纳": "CRE",
    "pis": "PIS", "pisa": "PIS", "比萨": "PIS",
    "int": "INT", "inter": "INT", "国米": "INT", "国际米兰": "INT",
    "juv": "JUV", "juventus": "JUV", "尤文": "JUV", "尤文图斯": "JUV",
    "mil": "MIL", "ac milan": "MIL", "ac米兰": "MIL", "米兰": "MIL",
    # 法甲
    "olm": "OLM", "om": "OLM", "marseille": "OLM", "马赛": "OLM",
    "asm": "MON", "monaco": "MON", "摩纳哥": "MON",
    "lyon": "LYON", "里昂": "LYON",
    "lil": "LILL", "lille": "LILL", "里尔": "LILL",
    "ren": "REN", "rennes": "REN", "雷恩": "REN",
    "nic": "NICE", "nice": "NICE", "尼斯": "NICE",
    "rcl": "RCL", "lens": "RCL", "朗斯": "RCL",
    "str": "STR", "strasbourg": "STR", "斯特拉斯堡": "STR", "斯特拉斯": "STR",
    "nan": "NAN", "nantes": "NAN", "南特": "NAN",
    "tou": "TOU", "toulouse": "TOU", "图卢兹": "TOU",
    "bre": "BRE", "brest": "BRE", "布雷斯特": "BRE",
    "rei": "REI", "reims": "REI", "兰斯": "REI",
    "montpellier": "MPL", "蒙彼利埃": "MPL",
    "ang": "ANG", "angers": "ANG", "昂热": "ANG",
    "aux": "AUX", "auxerre": "AUX", "欧塞尔": "AUX",
    "hac": "HAC", "le havre": "HAC", "勒阿弗尔": "HAC",
    "lor": "LOR", "lorient": "LOR", "洛里昂": "LOR",
    "met": "MET", "metz": "MET", "梅斯": "MET",
    "ste": "STE", "saint etienne": "STE", "圣埃蒂安": "STE",
    "paris fc": "PAR", "巴黎fc": "PAR",
    "psg": "PSG", "巴黎": "PSG", "巴黎圣日耳曼": "PSG",
    # 欧冠中坚（中文 / 系统 ID → ESPN abbr；本菲卡历史 abbr 为 SLB）
    "sporting cp": "SCP", "sporting lisbon": "SCP", "里斯本竞技": "SCP", "t1000": "SCP",
    "benfica": "SLB", "本菲卡": "SLB", "t678": "SLB",
    "porto": "FCP", "fc porto": "FCP", "波尔图": "FCP",
    "ajax": "AJA", "阿贾克斯": "AJA",
    "psv eindhoven": "PSV", "psv埃因霍温": "PSV", "埃因霍温": "PSV", "t378": "PSV",
    "feyenoord": "FEY", "费耶诺德": "FEY", "t801": "FEY",
    "club brugge": "BRU", "brugge": "BRU", "布鲁日": "BRU", "t729": "BRU",
    "celtic": "CEL", "凯尔特人": "CEL", "t926": "CEL",
    "galatasaray": "GAL", "加拉塔萨雷": "GAL", "t896": "GAL",
    "fenerbahce": "FEN", "fenerbahçe": "FEN", "费内巴切": "FEN", "t797": "FEN",
    "bodo/glimt": "BODO", "bodo glimt": "BODO", "bodø/glimt": "BODO", "博德闪耀": "BODO", "t703": "BODO",
    "red star belgrade": "RSB", "crvena zvezda": "RSB", "贝尔格莱德红星": "RSB", "t2553": "RSB",
    "shakhtar": "SHK", "shakhtar donetsk": "SHK", "顿涅茨克矿工": "SHK",
    "rb salzburg": "SLZ", "salzburg": "SLZ", "萨尔茨堡红牛": "SLZ", "萨尔茨堡": "SLZ", "t446": "SLZ",
    "dinamo zagreb": "DZG", "萨格勒布迪纳摩": "DZG", "t448": "DZG",
    "slavia prague": "SLP", "布拉格斯拉维亚": "SLP", "t718": "SLP",
    "sparta prague": "SPP", "布拉格斯巴达": "SPP", "t717": "SPP",
    "young boys": "YB", "年轻人": "YB", "t1177": "YB",
    "olympiacos": "OLY", "olympiakos": "OLY", "奥林匹亚科斯": "OLY", "t616": "OLY",
    "lask": "LAS", "lask linz": "LAS", "lask林茨": "LAS", "t334": "LAS",
    "sturm graz": "STG", "格拉茨风暴": "STG", "t825": "STG",
    "pafos": "PAF", "帕佛斯fc": "PAF", "帕佛斯": "PAF", "t2504": "PAF",
    "sabah": "SAB", "沙巴巴库": "SAB", "t10810": "SAB",
    "viking": "VIK", "维京": "VIK", "t1259": "VIK",
    "aek athens": "AEK", "雅典aek": "AEK", "t213": "AEK",
    "t986": "B04", "t1308": "ATA", "t997": "LYON", "t998": "LILL",
    "t1105": "MON", "t1593": "BRE", "t1134": "NICE",
}

# 中文/系统 ID → 英文检索词（解决 abbr 撞车，如本菲卡与布拉迪斯拉发都曾用 SLB）
ESPN_NAME_HINTS = {
    "本菲卡": ["benfica"],
    "t678": ["benfica"],
    "slb": ["benfica"],
    "布拉迪斯拉发": ["slovan bratislava", "bratislava", "s bratislava"],
    "t1474": ["slovan bratislava", "bratislava"],
    "brat": ["slovan bratislava", "bratislava"],
    "里斯本竞技": ["sporting cp", "sporting"],
    "t1000": ["sporting cp", "sporting"],
    "scp": ["sporting cp", "sporting"],
    "凯尔特人": ["celtic"],
    "t926": ["celtic"],
    "塞尔塔": ["celta", "celta vigo"],
    "曼城": ["manchester city", "man city"],
    "mci": ["manchester city", "man city", "mnc"],
    "拜仁": ["bayern", "bayern munich"],
    "bay": ["bayern", "bayern munich", "mun"],
    "亚特兰大": ["atalanta"],
    "atl": ["atalanta", "ata"],
    "t1308": ["atalanta"],
    "勒沃库森": ["leverkusen", "bayer leverkusen"],
    "t986": ["leverkusen"],
    "里昂": ["lyon"],
    "t997": ["lyon"],
    "里尔": ["lille"],
    "t998": ["lille"],
    "摩纳哥": ["monaco"],
    "t1105": ["monaco", "asm"],
    "asm": ["monaco", "mon"],
    "博德闪耀": ["bodo/glimt", "bodo glimt"],
    "t703": ["bodo/glimt", "bodo glimt"],
    "费内巴切": ["fenerbahce"],
    "t797": ["fenerbahce"],
    "加拉塔萨雷": ["galatasaray"],
    "t896": ["galatasaray"],
    "布鲁日": ["club brugge", "brugge"],
    "t729": ["club brugge", "brugge"],
    "年轻人": ["young boys"],
    "t1177": ["young boys"],
    "萨尔茨堡红牛": ["rb salzburg", "salzburg"],
    "t446": ["rb salzburg", "salzburg"],
    "萨格勒布迪纳摩": ["dinamo zagreb"],
    "t448": ["dinamo zagreb"],
    "贝尔格莱德红星": ["red star belgrade", "crvena zvezda"],
    "t2553": ["red star belgrade"],
    "布拉格斯拉维亚": ["slavia prague"],
    "t718": ["slavia prague"],
    "布拉格斯巴达": ["sparta prague"],
    "t717": ["sparta prague"],
    "奥林匹亚科斯": ["olympiacos", "olympiakos"],
    "t616": ["olympiacos"],
    "费耶诺德": ["feyenoord"],
    "t801": ["feyenoord"],
    "psv埃因霍温": ["psv eindhoven", "psv"],
    "t378": ["psv eindhoven", "psv"],
    "lask林茨": ["lask", "lask linz"],
    "t334": ["lask", "lask linz"],
    "格拉茨风暴": ["sturm graz"],
    "t825": ["sturm graz"],
    "帕佛斯": ["pafos"],
    "t2504": ["pafos"],
    "沙巴巴库": ["sabah"],
    "t10810": ["sabah"],
    "维京": ["viking"],
    "t1259": ["viking"],
    "雅典aek": ["aek athens", "aek"],
    "t213": ["aek athens", "aek"],
    "格拉斯哥流浪者": ["rangers", "glasgow rangers"],
    "t827": ["rangers"],
    "基辅迪纳摩": ["dynamo kyiv"],
    "t890": ["dynamo kyiv"],
    "费伦茨瓦罗斯": ["ferencvaros"],
    "t798": ["ferencvaros"],
    "卢多戈雷茨": ["ludogorets"],
    "t6591": ["ludogorets"],
    "马尔默": ["malmo", "malmö"],
    "t1051": ["malmo"],
    "哥本哈根": ["copenhagen"],
    "t819": ["copenhagen"],
    "卡拉巴赫": ["qarabag", "karabakh"],
    "t1546": ["qarabag"],
}


# 规范联赛 -> ESPN soccer 联赛代码
ESPN_LEAGUE_MAP = {
    "EPL": "eng.1",
    "LALIGA": "esp.1",
    "BUNDES": "ger.1",
    "SERIEA": "ita.1",
    "LIGUE1": "fra.1",
    "UCL": "uefa.champions",
    "UEL": "uefa.europa",
    "WC": "fifa.world",
    "EC": "uefa.euro",
    "ECH": "eng.2",  # 英冠（EFL Championship）；勿与 EC 欧洲杯混淆
    "MLS": "usa.1",
    "BRA": "bra.1",
    "SWE": "swe.1",
    "NOR": "nor.1",
    "FIN": "fin.1",
    "K1": "kor.1",  # P3：韩职
}

# 500.com 联赛页（LS*）归并到系统规范联赛，避免同一联赛两套球队
FIVE00_TO_CANONICAL = {
    "LS19906": "EPL",
    "LS19947": "LALIGA",
    "LS9124": "LALIGA",
    "LS19951": "BUNDES",
    "LS9117": "BUNDES",
    "LS19826": "SERIEA",
    "LS19835": "LIGUE1",
    "LS19943": "UCL",
    "LS19476": "WC",
    "LS19471": "MLS",
    "LS19498": "BRA",
    "LS19501": "SWE",
    "LS19506": "FIN",
    "LS19507": "NOR",
    "LS19554": "K1",
    "LS20000": "UEL",
    "LS9116": "ECH",  # 英冠 2025/26
    "LS19935": "ECH",  # 英冠 2026/27（当前赛季）
}

CANONICAL_FIVE00_URL = {
    "EPL": "https://liansai.500.com/zuqiu-19906/",
    "LALIGA": "https://liansai.500.com/zuqiu-19947/",
    "BUNDES": "https://liansai.500.com/zuqiu-19951/",
    "SERIEA": "https://liansai.500.com/zuqiu-19826/",
    "LIGUE1": "https://liansai.500.com/zuqiu-19835/",
    "UCL": "https://liansai.500.com/zuqiu-19943/",
    "UEL": "https://liansai.500.com/zuqiu-20000/",
    "WC": "https://liansai.500.com/zuqiu-19476/",
    "MLS": "https://liansai.500.com/zuqiu-19471/",
    "BRA": "https://liansai.500.com/zuqiu-19498/",
    "SWE": "https://liansai.500.com/zuqiu-19501/",
    "FIN": "https://liansai.500.com/zuqiu-19506/",
    "NOR": "https://liansai.500.com/zuqiu-19507/",  # P3：2026 挪超
    "K1": "https://liansai.500.com/zuqiu-19554/",  # P3：2026 韩职
    "ECH": "https://liansai.500.com/zuqiu-19935/",  # 英冠 2026/27（当前）；历史季见 FIVE00_TO_CANONICAL
    # EC：届次制，无常驻赛季页；赛程以 ESPN uefa.euro 为主
}

# 重点完善的五大联赛 + 欧冠 + 欧联（核心）
PRIORITY_LEAGUES_DEFAULT = ("EPL", "LALIGA", "BUNDES", "SERIEA", "LIGUE1", "UCL", "UEL")

# P2：已有双源映射、默认扩围采集（低于核心 SLA，不进默认 priority_train 重点名）
EXTENDED_LEAGUES_DEFAULT = ("MLS", "BRA", "SWE", "FIN")


def get_priority_leagues() -> tuple:
    """重点联赛列表；可用 config.yaml → crawler.priority_leagues 覆盖。"""
    try:
        from db.database import config as app_config
        raw = ((app_config or {}).get("crawler") or {}).get("priority_leagues")
        if isinstance(raw, (list, tuple)) and raw:
            return tuple(str(x).upper() for x in raw if x)
    except Exception:
        pass
    return PRIORITY_LEAGUES_DEFAULT


def get_extended_leagues() -> tuple:
    """P2 扩展双源联赛；config.yaml → crawler.extended_leagues。"""
    try:
        from db.database import config as app_config
        raw = ((app_config or {}).get("crawler") or {}).get("extended_leagues")
        if isinstance(raw, (list, tuple)) and raw:
            return tuple(str(x).upper() for x in raw if x)
    except Exception:
        pass
    return EXTENDED_LEAGUES_DEFAULT


def get_p3_dual_leagues() -> tuple:
    """P3 新激活双源联赛（NOR/K1/ECH）；EC 仍为 ESPN-only，不进此列表。"""
    return ("NOR", "K1", "ECH")


def get_stats_leagues() -> tuple:
    """射门统计 / 伤病 / 质量看板：重点 + 扩展 + P3 双源（去重保序）。"""
    seen = set()
    out = []
    for lid in (*get_priority_leagues(), *get_extended_leagues(), *get_p3_dual_leagues()):
        if lid and lid not in seen:
            seen.add(lid)
            out.append(lid)
    return tuple(out)


def league_pipeline_tier(league_id: Optional[str]) -> str:
    """联赛数据管线分档：core | extended | dual_mapped | espn_only | five00_only | unknown。"""
    lid = str(league_id or "").upper()
    if not lid:
        return "unknown"
    if lid in get_priority_leagues():
        return "core"
    if lid in get_extended_leagues():
        return "extended"
    has_espn = lid in ESPN_LEAGUE_MAP
    has_500 = lid in CANONICAL_FIVE00_URL
    if has_espn and has_500:
        return "dual_mapped"
    if has_espn:
        return "espn_only"
    if has_500 or lid.startswith("LS"):
        return "five00_only"
    return "unknown"


# 兼容旧代码：模块加载时取一次；运行期变更请用 get_priority_leagues()
PRIORITY_LEAGUES = get_priority_leagues()

ESPN_STANDING_STAT_MAP = {
    "gamesPlayed": "played",
    "wins": "won",
    "ties": "drawn",
    "losses": "lost",
    "pointsFor": "goals_for",
    "pointsAgainst": "goals_against",
    "pointDifferential": "goal_diff",
    "points": "points",
    "rank": "rank",
}


class RealTeamCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self.media = MediaCrawler(session=self.session)
        # 同批补采时复用 scoreboard，避免同日/同月重复打 ESPN
        self._espn_scoreboard_cache: Dict[Tuple[str, str], dict] = {}
        self._espn_scoreboard_cache_max = 256
        # 进程内熔断：某联赛 ESPN 持续 403 时跳过后续请求（改走 500 fenxi）
        self._espn_blocked_codes: set = set()

    def clear_espn_scoreboard_cache(self):
        self._espn_scoreboard_cache.clear()

    def _espn_code_blocked(self, espn_code: Optional[str]) -> bool:
        return bool(espn_code) and espn_code in self._espn_blocked_codes

    def _mark_espn_blocked(self, espn_code: Optional[str], reason: str = "403") -> None:
        if not espn_code or espn_code in self._espn_blocked_codes:
            return
        self._espn_blocked_codes.add(espn_code)
        logger.warning(
            "ESPN league code %s blocked for this process (%s); skip further ESPN calls",
            espn_code,
            reason,
        )

    @staticmethod
    def _espn_code_from_url(url: str) -> Optional[str]:
        m = re.search(r"/sports/soccer/([^/]+)/", str(url or ""))
        return m.group(1) if m else None

    def _espn_scoreboard_json(self, espn_code: str, dates_param: str) -> Optional[dict]:
        """带缓存的 ESPN scoreboard JSON（dates 可为 YYYYMMDD 或区间）。"""
        if self._espn_code_blocked(espn_code):
            return None
        key = (espn_code, dates_param)
        cached = self._espn_scoreboard_cache.get(key)
        if cached is not None:
            return cached
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}/scoreboard"
        try:
            r = self._espn_get(url, params={"dates": dates_param})
            if r is not None and r.status_code == 403:
                self._mark_espn_blocked(espn_code, "scoreboard 403")
                return None
            if r is None or r.status_code != 200:
                return None
            payload = r.json() or {}
        except Exception as e:
            logger.warning("ESPN scoreboard lookup failed (%s %s): %s", espn_code, dates_param, e)
            return None
        cache = self._espn_scoreboard_cache
        if len(cache) >= self._espn_scoreboard_cache_max:
            # 简单 FIFO：丢掉最早一半键
            for old_key in list(cache.keys())[: max(1, self._espn_scoreboard_cache_max // 2)]:
                cache.pop(old_key, None)
        cache[key] = payload
        return payload

    def crawl_league(self, league_id: str, source_url: Optional[str] = None) -> List[Dict]:
        """采集单个联赛球队名单：有 500 URL 主用 500，ESPN 补 espn_id/队徽；无 500 时纯 ESPN。"""
        canonical = FIVE00_TO_CANONICAL.get(league_id, league_id)
        five00_url = source_url or CANONICAL_FIVE00_URL.get(canonical)
        espn_code = ESPN_LEAGUE_MAP.get(canonical)
        teams: List[Dict] = []

        if five00_url:
            try:
                teams = self._crawl_500(canonical, five00_url)
                logger.info("500.com crawled %s teams for %s", len(teams), canonical)
            except Exception as e:
                logger.warning("500 teams failed for %s: %s", canonical, e)
                teams = []

        if espn_code:
            try:
                espn_teams = self._crawl_espn(canonical, espn_code)
                logger.info("ESPN crawled %s teams for %s (%s)", len(espn_teams), canonical, espn_code)
            except Exception as e:
                logger.warning("ESPN crawl failed for %s: %s", canonical, e)
                espn_teams = []
            if teams and espn_teams:
                teams = self._merge_espn_onto_500(teams, espn_teams)
            elif not teams:
                teams = espn_teams

        self._attach_team_logos(teams)
        return teams

    def crawl_fixtures(
        self,
        league_id: str,
        source_url: Optional[str] = None,
        include_history: bool = False,
        seasons_back: int = 0,
        max_rounds: int = 40,
    ) -> List[Dict]:
        """采集真实赛程/赛果：有 500 URL 主用 500；空结果或仅 ESPN 映射时软兜底 ESPN。"""
        canonical = FIVE00_TO_CANONICAL.get(league_id, league_id)
        five00_url = source_url or CANONICAL_FIVE00_URL.get(canonical)
        espn_code = ESPN_LEAGUE_MAP.get(canonical)

        if five00_url:
            try:
                matches = self._crawl_500_fixtures(
                    canonical,
                    five00_url,
                    include_history=include_history,
                    seasons_back=seasons_back,
                    max_rounds=max_rounds,
                )
            except Exception as e:
                logger.warning("500 fixtures failed for %s: %s", canonical, e)
                matches = []
            if matches:
                if espn_code:
                    matches = self._maybe_enrich_fixtures_espn(
                        matches,
                        canonical,
                        espn_code,
                        include_history=include_history,
                        seasons_back=seasons_back,
                    )
                return matches
            if espn_code:
                logger.info(
                    "500 fixtures empty for %s; falling back to ESPN (%s)",
                    canonical, espn_code,
                )
            else:
                logger.warning(
                    "500 fixtures empty for %s and no ESPN map",
                    canonical,
                )
                return []

        if not espn_code:
            logger.warning("No 500.com URL and no ESPN map for league %s", league_id)
            return []
        try:
            matches = self._crawl_espn_fixtures(
                canonical,
                espn_code,
                include_history=include_history,
                seasons_back=seasons_back,
            )
        except Exception as e:
            logger.warning("ESPN fixtures failed for %s: %s", canonical, e)
            return []
        if matches:
            logger.info(
                "Crawled %s fixtures for %s via ESPN (%s)%s",
                len(matches),
                canonical,
                espn_code,
                "" if five00_url else " (no 500 URL)",
            )
        return matches or []

    def _maybe_enrich_fixtures_espn(
        self,
        base_matches: List[Dict],
        league_id: str,
        espn_code: str,
        include_history: bool = False,
        seasons_back: int = 0,
    ) -> List[Dict]:
        """500 骨架上用 ESPN 轻量补 venue/process_id/完赛比分；永不覆盖 fixture_id。"""
        if not base_matches:
            return base_matches
        try:
            dates = []
            for m in base_matches:
                d = m.get("match_date")
                if isinstance(d, date):
                    dates.append(d)
                elif d:
                    try:
                        dates.append(date.fromisoformat(str(d)[:10]))
                    except Exception:
                        pass
            windows = self._espn_windows_covering_dates(dates)
            if not windows and include_history:
                windows = self._espn_fixture_date_windows(True, seasons_back)
            espn_matches: List[Dict] = []
            seen = set()
            for start_d, end_d in windows:
                if start_d == end_d:
                    dates_param = start_d.strftime("%Y%m%d")
                else:
                    dates_param = f"{start_d.strftime('%Y%m%d')}-{end_d.strftime('%Y%m%d')}"
                data = self._espn_scoreboard_json(espn_code, dates_param)
                if not data:
                    time.sleep(0.05)
                    continue
                for em in self._convert_espn_events(data.get("events") or [], league_id):
                    key = (em.get("match_date"), em.get("home_team_id"), em.get("away_team_id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    espn_matches.append(em)
                time.sleep(0.05)
            if not espn_matches:
                return base_matches
            enriched = self._enrich_fixtures_from_espn(base_matches, espn_matches)
            logger.info(
                "ESPN enrich for %s: base=%s espn=%s",
                league_id, len(base_matches), len(espn_matches),
            )
            return enriched
        except Exception as e:
            logger.warning("ESPN enrich skipped for %s: %s", league_id, e)
            return base_matches

    @staticmethod
    def _espn_windows_covering_dates(dates: List[date]) -> List[Tuple[date, date]]:
        """按出现过的年月生成 ESPN 月窗口。"""
        if not dates:
            return []
        months = sorted({(d.year, d.month) for d in dates})
        windows: List[Tuple[date, date]] = []
        for y, m in months:
            start = date(y, m, 1)
            if m == 12:
                end = date(y + 1, 1, 1) - timedelta(days=1)
            else:
                end = date(y, m + 1, 1) - timedelta(days=1)
            windows.append((start, end))
        return windows

    def _enrich_fixtures_from_espn(
        self, base_matches: List[Dict], espn_matches: List[Dict]
    ) -> List[Dict]:
        """按 (home, away, date±1) 对齐；只填空字段，保留 fixture_id。"""
        index: Dict[Tuple[str, str, date], Dict] = {}
        for em in espn_matches or []:
            d = em.get("match_date")
            if not isinstance(d, date):
                try:
                    d = date.fromisoformat(str(d)[:10])
                except Exception:
                    continue
            hid = str(em.get("home_team_id") or "")
            aid = str(em.get("away_team_id") or "")
            if not hid or not aid:
                continue
            index[(hid, aid, d)] = em

        def _lookup(hid: str, aid: str, d: date) -> Optional[Dict]:
            for off in (0, -1, 1):
                hit = index.get((hid, aid, d + timedelta(days=off)))
                if hit:
                    return hit
            return None

        out: List[Dict] = []
        for m in base_matches:
            row = dict(m)
            d = row.get("match_date")
            if not isinstance(d, date):
                try:
                    d = date.fromisoformat(str(d)[:10])
                except Exception:
                    out.append(row)
                    continue
            em = _lookup(str(row.get("home_team_id") or ""), str(row.get("away_team_id") or ""), d)
            if not em:
                out.append(row)
                continue
            if not row.get("venue") and em.get("venue"):
                row["venue"] = em["venue"]
            if not row.get("process_id") and em.get("process_id"):
                row["process_id"] = em["process_id"]
            if row.get("status") != "finished" and em.get("status") == "finished":
                row["status"] = "finished"
                row["home_goals"] = em.get("home_goals", 0)
                row["away_goals"] = em.get("away_goals", 0)
                row["result"] = em.get("result")
            out.append(row)
        return out

    def _crawl_500_fixtures(
        self,
        league_id: str,
        five00_url: str,
        include_history: bool = False,
        seasons_back: int = 0,
        max_rounds: int = 40,
    ) -> List[Dict]:
        """从 500.com 积分榜轮次接口采集赛程/赛果。"""
        back = seasons_back
        if include_history and back <= 0:
            back = 2

        urls = [five00_url]
        try:
            html = self._get_html(five00_url)
            soup = BeautifulSoup(html, "html.parser")
            if back > 0:
                urls.extend(self._find_season_urls(soup, five00_url, back))
        except Exception as e:
            logger.error("Failed to fetch league page %s: %s", five00_url, e)
            return []

        matches: List[Dict] = []
        seen = set()
        for page_url in urls:
            try:
                if league_id == "UCL":
                    page_matches = self._crawl_ucl_fixtures(league_id, page_url, max_rounds)
                else:
                    page_matches = self._crawl_fixtures_from_url(league_id, page_url, max_rounds)
            except Exception as e:
                logger.error("Failed to crawl fixtures %s: %s", page_url, e)
                continue
            for m in page_matches:
                if m["id"] in seen:
                    continue
                seen.add(m["id"])
                matches.append(m)
            time.sleep(0.2)
        logger.info("Crawled %s fixtures for %s via 500.com", len(matches), league_id)
        return matches

    @staticmethod
    def _espn_season_start_year(ref: Optional[date] = None) -> int:
        """欧洲赛季按 7 月切分：7 月及以后属新赛季起始年。"""
        ref = ref or date.today()
        return ref.year if ref.month >= 7 else ref.year - 1

    def _espn_fixture_date_windows(
        self,
        include_history: bool = False,
        seasons_back: int = 0,
    ) -> List[Tuple[date, date]]:
        """按月切分 ESPN scoreboard 日期窗口。"""
        today = date.today()
        cur_year = self._espn_season_start_year(today)
        if include_history:
            back = seasons_back if seasons_back > 0 else 2
            start = date(cur_year - back, 7, 1)
        else:
            start = date(cur_year, 7, 1)
        end = today + timedelta(days=60)
        if end < start:
            return []

        windows: List[Tuple[date, date]] = []
        cursor = date(start.year, start.month, 1)
        while cursor <= end:
            if cursor.month == 12:
                next_month = date(cursor.year + 1, 1, 1)
            else:
                next_month = date(cursor.year, cursor.month + 1, 1)
            chunk_end = min(next_month - timedelta(days=1), end)
            chunk_start = max(cursor, start)
            if chunk_start <= chunk_end:
                windows.append((chunk_start, chunk_end))
            cursor = next_month
        return windows

    def _crawl_espn_fixtures(
        self,
        league_id: str,
        espn_code: str,
        include_history: bool = False,
        seasons_back: int = 0,
    ) -> List[Dict]:
        """按日期窗口拉取 ESPN scoreboard 并转为系统赛程结构。"""
        windows = self._espn_fixture_date_windows(include_history, seasons_back)
        matches: List[Dict] = []
        seen = set()
        for start_d, end_d in windows:
            if start_d == end_d:
                dates_param = start_d.strftime("%Y%m%d")
            else:
                dates_param = f"{start_d.strftime('%Y%m%d')}-{end_d.strftime('%Y%m%d')}"
            data = self._espn_scoreboard_json(espn_code, dates_param)
            if not data:
                time.sleep(0.08)
                continue
            for m in self._convert_espn_events(data.get("events") or [], league_id):
                key = (m.get("match_date"), m.get("home_team_id"), m.get("away_team_id"))
                if key in seen:
                    continue
                seen.add(key)
                matches.append(m)
            time.sleep(0.08)
        return matches

    def _convert_espn_events(self, events: List[Dict], league_id: str) -> List[Dict]:
        """将 ESPN scoreboard events 转为与 500 路径一致的 match dict。"""
        used_ids: set = set()
        matches: List[Dict] = []
        for event in events or []:
            comp = (event.get("competitions") or [{}])[0]
            home = away = None
            for c in comp.get("competitors") or []:
                side = c.get("homeAway")
                if side == "home":
                    home = c
                elif side == "away":
                    away = c
            if not home or not away:
                continue
            ht = home.get("team") or {}
            at = away.get("team") or {}
            hname = (ht.get("displayName") or ht.get("name") or "").strip()
            aname = (at.get("displayName") or at.get("name") or "").strip()
            if not hname or not aname:
                continue
            habbr = (ht.get("abbreviation") or "").strip().upper()
            aabbr = (at.get("abbreviation") or "").strip().upper()
            hid = str(ht.get("id") or "")
            aid = str(at.get("id") or "")
            home_id = self._resolve_id(
                hname, ht.get("shortDisplayName") or hname, habbr, hid, used_ids
            )
            away_id = self._resolve_id(
                aname, at.get("shortDisplayName") or aname, aabbr, aid, used_ids
            )
            used_ids.add(home_id)
            used_ids.add(away_id)

            match_date, match_time = self._parse_espn_event_datetime(event.get("date") or "")
            status = self._espn_event_status(event)
            home_goals = self._to_int(home.get("score"))
            away_goals = self._to_int(away.get("score"))
            if status == "upcoming":
                home_goals = 0
                away_goals = 0
                result = None
            elif status == "live":
                result = None
            else:
                if home_goals > away_goals:
                    result = "H"
                elif home_goals < away_goals:
                    result = "A"
                else:
                    result = "D"

            venue = ""
            venue_obj = comp.get("venue") or event.get("venue") or {}
            if isinstance(venue_obj, dict):
                venue = (venue_obj.get("fullName") or venue_obj.get("name") or "").strip()

            round_name = self._espn_event_round_name(event, comp)
            stage_info = self._resolve_stage_info(league_id, round_name or "联赛")
            espn_eid = str(event.get("id") or "").strip()
            match_id = (
                f"E{espn_eid}" if espn_eid else f"{league_id}-{match_date}-{home_id}-{away_id}"
            )
            matches.append({
                "id": match_id[:50],
                "league_id": league_id,
                "home_team_id": home_id[:20],
                "home_team_name": hname,
                "away_team_id": away_id[:20],
                "away_team_name": aname,
                "match_date": match_date,
                "match_time": match_time,
                "venue": venue[:100] if venue else "",
                "status": status,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "result": result,
                "weather": "",
                "temperature": "",
                "pitch_condition": "",
                "stage": stage_info.get("stage", "league"),
                "group_name": stage_info.get("group_name"),
                "round_name": str(round_name or stage_info.get("round_name") or "联赛")[:20],
                "process_id": espn_eid[:30] if espn_eid else None,
            })
        return matches

    @staticmethod
    def _parse_espn_event_datetime(raw: str) -> Tuple[date, dt_time]:
        """解析 ESPN ISO 日期（按本地/naive 截断到日+时分）。"""
        text = (raw or "").strip()
        if not text:
            return date.today(), dt_time(15, 0)
        try:
            # 2024-08-16T19:00Z / 2024-08-16T19:00:00Z / with offset
            normalized = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            # 转近似北京时间便于与既有 500 赛程对齐
            if dt.tzinfo is not None:
                from datetime import timezone
                dt = dt.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
            return dt.date(), dt_time(dt.hour, dt.minute)
        except Exception:
            try:
                return date.fromisoformat(text[:10]), dt_time(15, 0)
            except Exception:
                return date.today(), dt_time(15, 0)

    @staticmethod
    def _espn_event_status(event: Dict) -> str:
        st = ((event.get("status") or {}).get("type") or {})
        state = (st.get("state") or "").lower()
        name = (st.get("name") or st.get("description") or "").upper()
        if state == "post" or "FINAL" in name or "FT" == name:
            return "finished"
        if state == "in" or "PROGRESS" in name or "HALF" in name:
            return "live"
        return "upcoming"

    @staticmethod
    def _espn_event_round_name(event: Dict, comp: Dict) -> str:
        for note in comp.get("notes") or []:
            if isinstance(note, dict):
                headline = (note.get("headline") or "").strip()
                if headline:
                    return headline[:20]
            elif isinstance(note, str) and note.strip():
                return note.strip()[:20]
        detail = ((event.get("status") or {}).get("type") or {}).get("detail") or ""
        if detail and not any(x in detail.upper() for x in ("FT", "FINAL", "SCHEDULED", "GMT", ":")):
            return str(detail)[:20]
        week = event.get("week") or {}
        if isinstance(week, dict) and week.get("number") is not None:
            return f"第{week.get('number')}轮"
        return "联赛"

    def _crawl_ucl_fixtures(self, league_id: str, league_url: str, max_rounds: int) -> List[Dict]:
        """欧冠含资格赛/联赛阶段等多个积分榜页，需逐阶段采集。"""
        html = self._get_html(league_url)
        soup = BeautifulSoup(html, "html.parser")
        jifen_url = self._find_jifen_url(soup, league_url)
        if not jifen_url:
            return self._crawl_fixtures_from_url(league_id, league_url, max_rounds)

        jifen_full = urljoin(league_url, jifen_url)
        jifen_html = self._get_html(jifen_full)
        jifen_soup = BeautifulSoup(jifen_html, "html.parser")
        stage_urls = self._find_stage_jifen_urls(jifen_soup, league_url)
        if not stage_urls:
            stage_urls = [("联赛", jifen_full)]

        matches: List[Dict] = []
        for label, stage_url in stage_urls:
            stage_matches = self._crawl_fixtures_from_url(
                league_id, stage_url, max_rounds, stage_label=label, direct_jifen=True
            )
            matches.extend(stage_matches)
            time.sleep(0.12)
        return matches

    def _crawl_fixtures_from_url(
        self,
        league_id: str,
        league_url: str,
        max_rounds: int,
        stage_label: str = "联赛",
        direct_jifen: bool = False,
    ) -> List[Dict]:
        stage_info = self._resolve_stage_info(league_id, stage_label)
        if direct_jifen:
            html = self._get_html(league_url)
            soup = BeautifulSoup(html, "html.parser")
        else:
            html = self._get_html(league_url)
            soup = BeautifulSoup(html, "html.parser")
            jifen_url = self._find_jifen_url(soup, league_url)
            if jifen_url:
                html = self._get_html(urljoin(league_url, jifen_url))
                soup = BeautifulSoup(html, "html.parser")

        stage_id, rounds = self._parse_stage_meta(html)
        matches: List[Dict] = []
        if stage_id and rounds:
            for rnd in rounds[:max_rounds]:
                raw = self._get_round_matches(stage_id, rnd)
                matches.extend(self._convert_500_matches(raw, league_id, stage_info))
                time.sleep(0.12)
        if not matches:
            matches = self._parse_saiguo_table(soup, league_id, stage_info)
        return matches

    def _parse_stage_meta(self, html: str) -> Tuple[Optional[str], List[int]]:
        stage_m = re.search(r"stageId\s*=\s*(\d+)", html)
        rounds_m = re.search(r"allRounds\s*=\s*(\[[^\]]+\])", html)
        stage_id = stage_m.group(1) if stage_m else None
        rounds: List[int] = []
        if rounds_m:
            try:
                parsed = json.loads(rounds_m.group(1))
                rounds = [int(x) for x in parsed if str(x).isdigit() or isinstance(x, int)]
            except Exception:
                rounds = []
        if not rounds:
            round_m = re.search(r"\bround\s*=\s*(\d+)", html)
            if round_m:
                rounds = [int(round_m.group(1))]
        return stage_id, rounds

    def _get_round_matches(self, stage_id: str, round_no: int) -> List[Dict]:
        url = "https://liansai.500.com/index.php"
        params = {"c": "score", "a": "getmatch", "stid": stage_id, "round": round_no}
        headers = {
            "Accept": "application/json, text/javascript, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://liansai.500.com/",
        }
        r = self.session.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        try:
            data = r.json()
        except Exception:
            data = json.loads(r.content.decode("utf-8", errors="replace"))
        if isinstance(data, dict):
            data = data.get("list") or data.get("data") or []
        return data if isinstance(data, list) else []

    def _convert_500_matches(
        self, raw_list: List[Dict], league_id: str, stage_info: Optional[Dict] = None
    ) -> List[Dict]:
        stage_info = stage_info or {"stage": "league", "group_name": None}
        used_ids: set = set()
        matches = []
        for item in raw_list or []:
            fid = str(item.get("fid") or "").strip()
            hname = (item.get("hname") or item.get("hsxname") or "").strip()
            gname = (item.get("gname") or item.get("gsxname") or "").strip()
            if not hname or not gname:
                continue
            hid = str(item.get("hid") or "")
            gid = str(item.get("gid") or "")
            home_id = self._resolve_id(hname, item.get("hsxname") or hname, "", hid, used_ids, fallback_prefix="T")
            away_id = self._resolve_id(gname, item.get("gsxname") or gname, "", gid, used_ids, fallback_prefix="T")
            used_ids.add(home_id)
            used_ids.add(away_id)

            match_date, match_time = self._parse_stime(item.get("stime") or "")
            status_code = int(item.get("status") or 0)
            home_goals = self._to_int(item.get("hscore"))
            away_goals = self._to_int(item.get("gscore"))
            if status_code >= 5:
                status = "finished"
            elif status_code >= 2:
                status = "live"
            else:
                status = "upcoming"
                home_goals = home_goals if status_code else 0
                away_goals = away_goals if status_code else 0
            if status != "finished":
                result = None
                if status == "upcoming":
                    home_goals = 0
                    away_goals = 0
            else:
                if home_goals > away_goals:
                    result = "H"
                elif home_goals < away_goals:
                    result = "A"
                else:
                    result = "D"

            round_no = item.get("round") or 0
            bout = item.get("matchbout") or round_no
            round_name = f"第{round_no}轮" if round_no else (item.get("matchbout") or stage_info.get("round_name") or "联赛")
            if stage_info.get("round_name") and league_id == "UCL":
                round_name = stage_info["round_name"]
            match_id = f"F{fid}" if fid else f"{league_id}-{match_date}-{home_id}-{away_id}"
            matches.append({
                "id": match_id[:50],
                "league_id": league_id,
                "home_team_id": home_id[:20],
                "home_team_name": hname,
                "away_team_id": away_id[:20],
                "away_team_name": gname,
                "match_date": match_date,
                "match_time": match_time,
                "venue": "",
                "status": status,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "result": result,
                "weather": "",
                "temperature": "",
                "pitch_condition": "",
                "stage": stage_info.get("stage", "league"),
                "group_name": stage_info.get("group_name"),
                "round_name": str(round_name)[:20],
                "fixture_id": fid[:30] if fid else None,
            })
        return matches

    def _parse_saiguo_table(
        self, soup: BeautifulSoup, league_id: str, stage_info: Optional[Dict] = None
    ) -> List[Dict]:
        stage_info = stage_info or {"stage": "league", "group_name": None}
        table = soup.find("table", class_="lsaiguo_list")
        if not table:
            return []
        used_ids: set = set()
        matches = []
        for row in table.find_all("tr")[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 5:
                continue
            round_no = cells[0]
            stime = cells[1]
            home_name = re.sub(r"^\[\d+\]", "", cells[2]).strip()
            score = cells[3]
            away_name = re.sub(r"\[\d+\]$", "", cells[4]).strip()
            if not home_name or not away_name:
                continue
            home_id = self._resolve_id(home_name, home_name, "", "", used_ids, fallback_prefix="T")
            away_id = self._resolve_id(away_name, away_name, "", "", used_ids, fallback_prefix="T")
            used_ids.add(home_id)
            used_ids.add(away_id)
            match_date, match_time = self._parse_stime(stime)
            home_goals, away_goals, result, status = 0, 0, None, "upcoming"
            main = score.split("(")[0] if score else ""
            if ":" in main and "vs" not in main.lower():
                parts = main.split(":")
                try:
                    home_goals = int(parts[0])
                    away_goals = int(parts[1])
                    status = "finished"
                    result = "H" if home_goals > away_goals else ("A" if home_goals < away_goals else "D")
                except ValueError:
                    pass
            match_id = f"{league_id}-{match_date}-{home_id}-{away_id}"
            matches.append({
                "id": match_id[:50],
                "league_id": league_id,
                "home_team_id": home_id[:20],
                "home_team_name": home_name,
                "away_team_id": away_id[:20],
                "away_team_name": away_name,
                "match_date": match_date,
                "match_time": match_time,
                "venue": "",
                "status": status,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "result": result,
                "weather": "",
                "temperature": "",
                "pitch_condition": "",
                "stage": stage_info.get("stage", "league"),
                "group_name": stage_info.get("group_name"),
                "round_name": f"第{round_no}轮"[:20] if str(round_no).isdigit() else str(round_no)[:20],
            })
        return matches

    def _find_season_urls(self, soup: BeautifulSoup, current_url: str, seasons_back: int) -> List[str]:
        """返回若干历史赛季首页 URL（不含当前赛季）。"""
        current_id = None
        m = re.search(r"zuqiu-(\d+)", current_url)
        if m:
            current_id = m.group(1)
        candidates: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            mm = re.search(r"/zuqiu-(\d+)/?", href)
            if not mm:
                continue
            if current_id and mm.group(1) == current_id:
                continue
            text = a.get_text(strip=True)
            if "赛季" in text or re.match(r"\d{4}", text or ""):
                full = urljoin(current_url, href)
                if full not in candidates:
                    candidates.append(full)
        return candidates[:seasons_back]

    def _find_previous_season_url(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        urls = self._find_season_urls(soup, current_url, 1)
        return urls[0] if urls else None

    def _find_stage_jifen_urls(self, soup: BeautifulSoup, base_url: str) -> List[Tuple[str, str]]:
        """解析欧冠等赛事的多阶段积分榜链接。"""
        stages: List[Tuple[str, str]] = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/jifen-" not in href:
                continue
            full = urljoin(base_url, href)
            if full in seen:
                continue
            label = (a.get_text(strip=True) or "联赛").replace(">>", "").strip()
            if not label or label in ("赛程积分榜", "查看完整赛程>>"):
                continue
            seen.add(full)
            stages.append((label, full))
        return stages

    def _resolve_stage_info(self, league_id: str, stage_label: str) -> Dict:
        label = (stage_label or "").strip()
        if league_id != "UCL":
            return {"stage": "league", "group_name": None, "round_name": label or "联赛"}

        if any(k in label for k in ("联赛阶段", "小组赛")):
            return {"stage": "league", "group_name": None, "round_name": label}
        if "联赛" in label and "附加" not in label and "资格" not in label:
            return {"stage": "league", "group_name": None, "round_name": label}
        if "十六强" in label or "1/8" in label:
            return {"stage": "round_of_16", "group_name": None, "round_name": label}
        if any(k in label for k in ("八强", "四分之一", "1/4", "半准决赛")):
            return {"stage": "quarter_final", "group_name": None, "round_name": label}
        if "半决赛" in label or "1/2" in label:
            return {"stage": "semi_final", "group_name": None, "round_name": label}
        if "决赛" in label and "半" not in label and "准" not in label:
            return {"stage": "final", "group_name": None, "round_name": label}
        if "资格" in label:
            return {"stage": "qualifying", "group_name": None, "round_name": label}
        if "附加赛" in label:
            return {"stage": "playoff", "group_name": None, "round_name": label}
        if any(k in label for k in ("第一圈", "第二圈", "第三圈")):
            return {"stage": "play_in", "group_name": None, "round_name": label}
        return {"stage": "knockout", "group_name": None, "round_name": label or "淘汰赛"}

    @staticmethod
    def normalize_season(raw: str) -> str:
        """将 2026-27 / 2025/2026 等格式统一为 2026-2027。"""
        text = (raw or "").strip()
        m = re.search(r"(\d{4})\s*[-/]\s*(\d{2,4})", text)
        if not m:
            y = date.today().year
            return f"{y}-{y + 1}"
        start = int(m.group(1))
        end_raw = m.group(2)
        end = int(end_raw) if len(end_raw) == 4 else (start // 100) * 100 + int(end_raw)
        if end <= start:
            end = start + 1
        return f"{start}-{end}"

    def crawl_standings(
        self, league_id: str, source_url: Optional[str] = None
    ) -> Tuple[List[Dict], str]:
        """采集积分榜：有 500 URL 主用 500，空则 ESPN 兜底。返回 (rows, season)。"""
        canonical = FIVE00_TO_CANONICAL.get(league_id, league_id)
        five00_url = source_url or CANONICAL_FIVE00_URL.get(canonical)
        espn_code = ESPN_LEAGUE_MAP.get(canonical)

        if five00_url:
            try:
                rows, season = self._crawl_500_standings(canonical, five00_url)
                if rows:
                    return rows, season
                logger.warning("500 standings empty for %s, trying ESPN", canonical)
            except Exception as e:
                logger.warning("500 standings failed for %s: %s", canonical, e)

        if espn_code:
            rows, season = self._crawl_espn_standings(canonical, espn_code)
            if rows:
                return rows, season
            logger.warning("ESPN standings empty for %s", canonical)

        return [], self.normalize_season("")

    def _crawl_espn_standings(self, league_id: str, espn_code: str) -> Tuple[List[Dict], str]:
        url = f"https://site.api.espn.com/apis/v2/sports/soccer/{espn_code}/standings"
        try:
            r = self._espn_get(url)
            if r.status_code != 200:
                return [], self.normalize_season("")
            payload = r.json()
        except Exception as e:
            logger.warning("ESPN standings failed for %s: %s", espn_code, e)
            return [], self.normalize_season("")

        season = self.normalize_season("")
        rows: List[Dict] = []
        used_ids: set = set()
        for child in payload.get("children") or []:
            standings = child.get("standings") or {}
            season = self.normalize_season(standings.get("seasonDisplayName") or season)
            for entry in standings.get("entries") or []:
                team = entry.get("team") or {}
                display = (team.get("displayName") or team.get("name") or "").strip()
                short = (team.get("shortDisplayName") or team.get("abbreviation") or display).strip()
                abbr = (team.get("abbreviation") or "").strip().upper()
                espn_id = str(team.get("id") or "")
                team_id = self._resolve_id(display, short, abbr, espn_id, used_ids)
                used_ids.add(team_id)

                stat_map = {}
                for st in entry.get("stats") or []:
                    stat_map[st.get("name")] = st.get("value")

                row = {
                    "league_id": league_id,
                    "team_id": team_id[:20],
                    "team_name": display[:80],
                    "team_short": short[:40],
                    "season": season,
                    "rank": int(stat_map.get("rank") or len(rows) + 1),
                    "played": int(stat_map.get("gamesPlayed") or 0),
                    "won": int(stat_map.get("wins") or 0),
                    "drawn": int(stat_map.get("ties") or 0),
                    "lost": int(stat_map.get("losses") or 0),
                    "goals_for": int(stat_map.get("pointsFor") or 0),
                    "goals_against": int(stat_map.get("pointsAgainst") or 0),
                    "goal_diff": int(stat_map.get("pointDifferential") or 0),
                    "points": int(stat_map.get("points") or 0),
                    "update_date": date.today(),
                }
                rows.append(row)
        rows.sort(key=lambda x: x["rank"])
        return rows, season

    def _crawl_500_standings(self, league_id: str, league_url: str) -> Tuple[List[Dict], str]:
        html = self._get_html(league_url)
        soup = BeautifulSoup(html, "html.parser")
        season = self.normalize_season("")
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if "赛季" in text and re.search(r"\d{4}", text):
                season = self.normalize_season(text)
                break

        jifen_url = self._find_jifen_url(soup, league_url)
        if not jifen_url:
            return [], season
        html = self._get_html(urljoin(league_url, jifen_url))
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_=lambda c: c and "ljifen_top_list" in c)
        if not table:
            return [], season

        used_ids: set = set()
        rows: List[Dict] = []
        for row in table.find_all("tr")[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 10:
                continue
            team_a = row.find("a", href=re.compile(r"/team/"))
            team_name = team_a.get_text(strip=True) if team_a else (cells[2] if len(cells) > 2 else "")
            if not team_name:
                continue
            team_id = self._resolve_id(team_name, team_name, "", "", used_ids, fallback_prefix="T")
            used_ids.add(team_id)
            try:
                rank = int(cells[1]) if cells[1].isdigit() else len(rows) + 1
                played = int(cells[3]) if len(cells) > 3 and cells[3].isdigit() else 0
                won = int(cells[4]) if len(cells) > 4 and cells[4].isdigit() else 0
                drawn = int(cells[5]) if len(cells) > 5 and cells[5].isdigit() else 0
                lost = int(cells[6]) if len(cells) > 6 and cells[6].isdigit() else 0
                goals_for = int(cells[7]) if len(cells) > 7 and cells[7].isdigit() else 0
                goals_against = int(cells[8]) if len(cells) > 8 and cells[8].isdigit() else 0
                goal_diff = int(cells[9]) if len(cells) > 9 and re.fullmatch(r"-?\d+", cells[9] or "") else goals_for - goals_against
                points = int(cells[15]) if len(cells) > 15 and cells[15].isdigit() else won * 3 + drawn
            except (ValueError, IndexError):
                continue
            rows.append({
                "league_id": league_id,
                "team_id": team_id[:20],
                "team_name": team_name[:80],
                "team_short": team_name[:40],
                "season": season,
                "rank": rank,
                "played": played,
                "won": won,
                "drawn": drawn,
                "lost": lost,
                "goals_for": goals_for,
                "goals_against": goals_against,
                "goal_diff": goal_diff,
                "points": points,
                "update_date": date.today(),
            })
        return rows, season

    def crawl_top_scorers(
        self, league_id: str, source_url: Optional[str] = None, limit: int = 20
    ) -> Tuple[List[Dict], str]:
        """采集射手榜：优先 ESPN statistics（goalsLeaders），阵容聚合兜底。"""
        canonical = FIVE00_TO_CANONICAL.get(league_id, league_id)
        espn_code = ESPN_LEAGUE_MAP.get(canonical)
        if espn_code:
            rows, season = self._crawl_espn_scorers(canonical, espn_code, limit=limit)
            if rows:
                return rows, season
            logger.warning("ESPN scorers empty for %s, fallback to squad aggregation", canonical)

        stats = self.crawl_squad_stats(canonical, source_url=source_url)
        season = self.normalize_season("")
        if not stats:
            return [], season

        ranked = sorted(stats, key=lambda x: (x.get("goals") or 0, x.get("assists") or 0), reverse=True)
        rows: List[Dict] = []
        for idx, item in enumerate(ranked[:limit], start=1):
            if (item.get("goals") or 0) <= 0:
                continue
            rows.append({
                "player_name": item.get("name") or "",
                "team_id": item.get("team_id"),
                "league_id": canonical,
                "season": season,
                "goals": item.get("goals") or 0,
                "assists": item.get("assists") or 0,
                "games_played": item.get("appearances") or 0,
                "rank": idx,
                "update_date": date.today(),
            })
        return rows, season

    def _crawl_espn_scorers(
        self, league_id: str, espn_code: str, limit: int = 20
    ) -> Tuple[List[Dict], str]:
        """ESPN /statistics → goalsLeaders（一次请求拿全联盟射手）。"""
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}/statistics"
        try:
            r = self.session.get(
                url,
                timeout=25,
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.espn.com/",
                },
            )
            if r.status_code != 200:
                logger.warning("ESPN scorers HTTP %s for %s", r.status_code, espn_code)
                return [], self.normalize_season("")
            payload = r.json()
        except Exception as e:
            logger.warning("ESPN scorers failed for %s: %s", espn_code, e)
            return [], self.normalize_season("")

        season_obj = payload.get("season") or {}
        season = self.normalize_season(
            season_obj.get("displayName") or season_obj.get("name") or ""
        )

        goals_block = next(
            (b for b in (payload.get("stats") or []) if b.get("name") == "goalsLeaders"),
            None,
        )
        assists_block = next(
            (b for b in (payload.get("stats") or []) if b.get("name") == "assistsLeaders"),
            None,
        )
        if not goals_block:
            return [], season

        assist_map: Dict[str, int] = {}
        for entry in (assists_block or {}).get("leaders") or []:
            ath = entry.get("athlete") or {}
            aid = str(ath.get("id") or "")
            if not aid:
                continue
            stats = {s.get("name"): s.get("value") for s in (ath.get("statistics") or [])}
            assist_map[aid] = int(stats.get("goalAssists") or entry.get("value") or 0)

        used_ids: set = set()
        rows: List[Dict] = []
        for entry in goals_block.get("leaders") or []:
            ath = entry.get("athlete") or {}
            name = (ath.get("displayName") or ath.get("shortName") or "").strip()
            if not name:
                continue
            team = ath.get("team") or {}
            display = (team.get("displayName") or team.get("name") or "").strip()
            short = (team.get("shortDisplayName") or team.get("abbreviation") or display).strip()
            abbr = (team.get("abbreviation") or "").strip().upper()
            espn_tid = str(team.get("id") or "")
            team_id = self._resolve_id(display, short, abbr, espn_tid, used_ids) if display else None
            if team_id:
                used_ids.add(team_id)

            stats = {s.get("name"): s.get("value") for s in (ath.get("statistics") or [])}
            goals = int(stats.get("totalGoals") or entry.get("value") or 0)
            if goals <= 0:
                continue
            apps = int(stats.get("appearances") or 0)
            assists = int(stats.get("goalAssists") or assist_map.get(str(ath.get("id") or ""), 0) or 0)

            rows.append({
                "player_name": name[:100],
                "team_id": (team_id[:20] if team_id else None),
                "team_name": display[:80] if display else None,
                "team_short": short[:40] if short else None,
                "league_id": league_id,
                "season": season,
                "goals": goals,
                "assists": assists,
                "games_played": apps,
                "rank": len(rows) + 1,
                "update_date": date.today(),
            })
            if len(rows) >= limit:
                break

        for i, row in enumerate(rows, start=1):
            row["rank"] = i
        return rows, season

    def _parse_stime(self, stime: str) -> Tuple[date, dt_time]:
        stime = (stime or "").strip()
        try:
            if " " in stime:
                d, t = stime.split(" ", 1)
                y, mo, da = [int(x) for x in d.split("-")[:3]]
                hh, mm = [int(x) for x in t.split(":")[:2]]
                return date(y, mo, da), dt_time(hh, mm)
            if "-" in stime:
                y, mo, da = [int(x) for x in stime.split("-")[:3]]
                return date(y, mo, da), dt_time(15, 0)
        except Exception:
            pass
        return date.today(), dt_time(15, 0)

    @staticmethod
    def _to_int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def crawl_espn_leagues(self) -> Dict[str, List[Dict]]:
        """采集所有 ESPN 覆盖的规范联赛。"""
        result = {}
        for league_id, code in ESPN_LEAGUE_MAP.items():
            try:
                teams = self.crawl_league(league_id)
                result[league_id] = teams
                time.sleep(0.3)
            except Exception as e:
                logger.error("Failed to crawl teams for %s: %s", league_id, e)
                result[league_id] = []
        return result

    def _crawl_espn(self, league_id: str, espn_code: str) -> List[Dict]:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}/teams?limit=100"
        r = self._espn_get(url)
        if r is None or r.status_code != 200:
            logger.warning("ESPN %s returned %s", espn_code, getattr(r, "status_code", None))
            return []
        data = r.json()
        teams = []
        used_ids = set()
        for sport in data.get("sports") or []:
            for lg in sport.get("leagues") or []:
                for item in lg.get("teams") or []:
                    tm = item.get("team") or item
                    display = (tm.get("displayName") or tm.get("name") or "").strip()
                    short = (tm.get("shortDisplayName") or tm.get("abbreviation") or display).strip()
                    abbr = (tm.get("abbreviation") or "").strip().upper()
                    espn_id = str(tm.get("id") or "")
                    team_id = self._resolve_id(display, short, abbr, espn_id, used_ids)
                    used_ids.add(team_id)
                    espn_logo = ""
                    logos = tm.get("logos") or []
                    if logos and isinstance(logos, list):
                        espn_logo = (logos[0] or {}).get("href") or ""
                    teams.append({
                        "id": team_id,
                        "name": display or short,
                        "short_name": short[:20] if short else team_id,
                        "logo": espn_logo or "⚽",
                        "remote_logo": espn_logo,
                        "league_id": league_id,
                        "country": "",
                        "elo_rating": 1500,
                        "attack_strength": 1.0,
                        "defense_strength": 1.0,
                        "home_ground": "",
                        "source": "espn",
                        "espn_id": espn_id,
                    })
        return teams

    def _crawl_500(self, league_id: str, league_url: str) -> List[Dict]:
        try:
            html = self._get_html(league_url)
        except Exception as e:
            logger.error("Failed to fetch 500.com %s: %s", league_url, e)
            return []

        soup = BeautifulSoup(html, "html.parser")
        jifen_url = self._find_jifen_url(soup, league_url)
        if jifen_url:
            try:
                html = self._get_html(jifen_url)
                soup = BeautifulSoup(html, "html.parser")
            except Exception as e:
                logger.warning("Failed to fetch jifen page %s: %s", jifen_url, e)

        by_src: Dict[str, Dict] = {}
        for a in soup.select('a[href*="/team/"]'):
            href = a.get("href") or ""
            name = a.get_text(strip=True)
            m = re.search(r"/team/(\d+)/?", href)
            if not m or not name or len(name) > 30:
                continue
            src_id = m.group(1)
            if src_id not in by_src:
                by_src[src_id] = {"name": name, "src_id": src_id}
            else:
                old = by_src[src_id]["name"]
                if len(name) > len(old):
                    by_src[src_id]["name"] = name

        used_ids = set()
        teams = []
        for src_id, item in by_src.items():
            name = item["name"]
            team_id = self._resolve_id(name, name, "", src_id, used_ids, fallback_prefix="T")
            used_ids.add(team_id)
            teams.append({
                "id": team_id,
                "name": name,
                "short_name": name[:20],
                "logo": "⚽",
                "league_id": league_id,
                "country": "",
                "elo_rating": 1500,
                "attack_strength": 1.0,
                "defense_strength": 1.0,
                "home_ground": "",
                "source": "500.com",
                "source_team_id": src_id,
            })
        return teams

    def _get_html(self, url: str) -> str:
        r = self.session.get(url, timeout=20)
        r.raise_for_status()
        try:
            return r.content.decode("gbk", errors="replace")
        except Exception:
            return r.content.decode("utf-8", errors="replace")

    def _find_jifen_url(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/jifen-" in href:
                return urljoin(base_url, href)
        return None

    def _resolve_id(
        self,
        display: str,
        short: str,
        abbr: str,
        raw_id: str,
        used_ids: set,
        fallback_prefix: str = "",
    ) -> str:
        for candidate in (display, short, abbr):
            alias = self._alias_lookup(candidate)
            if alias:
                return alias[:20]

        if abbr and re.fullmatch(r"[A-Z0-9]{2,8}", abbr):
            tid = abbr[:20]
            if tid not in used_ids:
                return tid

        if fallback_prefix and raw_id:
            return f"{fallback_prefix}{raw_id}"[:20]
        if raw_id:
            return f"ESPN{raw_id}"[:20]

        cleaned = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", display or short or "TEAM")
        return (cleaned[:8] or "TEAM").upper()[:20]

    def _alias_lookup(self, name: str) -> Optional[str]:
        if not name:
            return None
        return resolve_team_alias(name)

    def _merge_chinese_names(self, espn_teams: List[Dict], zh_teams: List[Dict]) -> List[Dict]:
        by_id = {t["id"]: t for t in espn_teams}
        for zh in zh_teams:
            existing = by_id.get(zh["id"])
            if existing:
                existing["name"] = zh["name"]
                existing["short_name"] = zh["short_name"]
                existing["source_team_id"] = zh.get("source_team_id")
                if zh.get("logo") and str(zh.get("logo")).startswith("/static/"):
                    existing["logo"] = zh["logo"]
            else:
                by_id[zh["id"]] = zh
        return list(by_id.values())

    def _merge_espn_onto_500(self, zh_teams: List[Dict], espn_teams: List[Dict]) -> List[Dict]:
        """以 500 名单为底，补 ESPN 的 espn_id / remote_logo；保留中文名。"""
        by_id = {t["id"]: dict(t) for t in zh_teams}
        for et in espn_teams or []:
            tid = et.get("id")
            if not tid:
                continue
            existing = by_id.get(tid)
            if existing:
                if et.get("espn_id"):
                    existing["espn_id"] = et["espn_id"]
                if et.get("remote_logo"):
                    existing["remote_logo"] = et["remote_logo"]
                existing["source"] = "500+espn"
            else:
                by_id[tid] = et
        return list(by_id.values())

    def _attach_team_logos(self, teams: List[Dict]) -> None:
        for team in teams or []:
            logo = self.media.fetch_team_logo(
                team.get("id"),
                team.get("source_team_id"),
                team.get("remote_logo"),
                espn_id=team.get("espn_id"),
                country_code=team.get("country_code"),
                team_name=team.get("name") or team.get("short_name"),
            )
            if logo:
                team["logo"] = logo

    GROUP_POSITION = {
        "守门员": "GK", "门将": "GK",
        "后卫": "CB", "中后卫": "CB", "右后卫": "RB", "左后卫": "LB",
        "中场": "CM", "后腰": "DM", "前腰": "AM", "右前卫": "RM", "左前卫": "LM",
        "前锋": "ST", "中锋": "ST", "右边锋": "RW", "左边锋": "LW", "边锋": "ST",
    }

    def crawl_squads(
        self,
        league_id: str,
        source_url: Optional[str] = None,
        team_id: Optional[str] = None,
        download_photos: bool = False,
    ) -> List[Dict]:
        """从 500.com 球队页采集真实阵容（球员名单），无模拟数据。"""
        canonical = FIVE00_TO_CANONICAL.get(league_id, league_id)
        five00_url = source_url or CANONICAL_FIVE00_URL.get(canonical)
        if not five00_url:
            logger.warning("No 500.com URL for squad crawl %s", league_id)
            return []

        raw_teams = self._crawl_500(canonical, five00_url)
        if not raw_teams:
            logger.warning("No 500.com teams found for squad crawl %s", canonical)
            return []

        targets = raw_teams
        if team_id:
            targets = [t for t in raw_teams if t.get("id") == team_id]
            if not targets:
                logger.warning("Team %s not found in 500.com league %s", team_id, canonical)
                return []

        players: List[Dict] = []
        for t in targets:
            src_id = t.get("source_team_id")
            sys_id = t.get("id")
            if not src_id or not sys_id:
                continue
            try:
                squad = self._crawl_team_squad(
                    str(src_id), sys_id, download_photos=download_photos
                )
                players.extend(squad)
                logger.info("Squad %s (%s): %s players", sys_id, src_id, len(squad))
            except Exception as e:
                logger.warning("Squad crawl failed for %s: %s", sys_id, e)
            time.sleep(0.15)
        return players

    def _attach_player_photos(self, players: Dict[str, Dict], source_team_id: str = None) -> None:
        from services.media_crawler import public_url
        for src_pid, item in (players or {}).items():
            player_id = item.get("id")
            if not player_id:
                continue
            photo = None
            img = item.pop("_img_src", None)
            if img:
                dest = self.media.dest("players", player_id)
                if self.media.download(img, dest):
                    photo = public_url("players", player_id)
            if not photo:
                photo = self.media.fetch_player_photo(
                    player_id,
                    source_pid=str(src_pid),
                    source_team_id=source_team_id,
                )
            if photo:
                item["photo"] = photo

    def _crawl_team_squad(
        self, source_team_id: str, system_team_id: str, download_photos: bool = False
    ) -> List[Dict]:
        players: Dict[str, Dict] = {}
        try:
            html = self._get_html(f"https://liansai.500.com/team/{source_team_id}/")
            soup = BeautifulSoup(html, "html.parser")
            players.update(self._parse_homepage_roster(soup, system_team_id))
        except Exception as e:
            logger.warning("Failed to fetch team page %s: %s", source_team_id, e)

        try:
            html = self._get_html(f"https://liansai.500.com/team/{source_team_id}/teamlineup/")
            soup = BeautifulSoup(html, "html.parser")
            lineup = self._parse_lineup_table(soup, system_team_id)
            for pid, item in lineup.items():
                if pid in players:
                    players[pid].update({k: v for k, v in item.items() if v not in (None, "", 0)})
                    players[pid]["id"] = item["id"]
                    players[pid]["team_id"] = system_team_id
                    players[pid]["name"] = item.get("name") or players[pid].get("name")
                else:
                    players[pid] = item
        except Exception as e:
            logger.warning("Failed to fetch lineup page %s: %s", source_team_id, e)

        if download_photos:
            self._attach_player_photos(players, source_team_id=source_team_id)
        return list(players.values())

    def crawl_squad_stats(
        self,
        league_id: str,
        source_url: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> List[Dict]:
        """采集球员进球/助攻/出场数据。优先 ESPN roster API，500.com 阵容页作兜底。"""
        canonical = FIVE00_TO_CANONICAL.get(league_id, league_id)
        espn_code = ESPN_LEAGUE_MAP.get(canonical)
        if espn_code:
            espn_stats = self._crawl_espn_squad_stats(canonical, espn_code, team_id=team_id)
            if espn_stats:
                return espn_stats
            logger.warning("ESPN stats empty for %s, fallback to 500.com", canonical)

        five00_url = source_url or CANONICAL_FIVE00_URL.get(canonical)
        if not five00_url:
            logger.warning("No 500.com URL for stats crawl %s", league_id)
            return []

        raw_teams = self._crawl_500(canonical, five00_url)
        if not raw_teams:
            logger.warning("No 500.com teams found for stats crawl %s", canonical)
            return []

        targets = raw_teams
        if team_id:
            targets = [t for t in raw_teams if t.get("id") == team_id]
            if not targets:
                logger.warning("Team %s not found in 500.com league %s", team_id, canonical)
                return []

        stats: List[Dict] = []
        for t in targets:
            src_id = t.get("source_team_id")
            sys_id = t.get("id")
            if not src_id or not sys_id:
                continue
            try:
                rows = self._crawl_team_lineup_stats(str(src_id), sys_id)
                stats.extend(rows)
                logger.info("Stats %s (%s): %s players", sys_id, src_id, len(rows))
            except Exception as e:
                logger.warning("Stats crawl failed for %s: %s", sys_id, e)
            time.sleep(0.12)
        return stats

    ESPN_POSITION_MAP = {
        "G": "GK", "GK": "GK",
        "D": "CB", "CB": "CB", "RB": "RB", "LB": "LB",
        "M": "CM", "CM": "CM", "DM": "DM", "AM": "AM", "RM": "RM", "LM": "LM",
        "F": "ST", "ST": "ST", "RW": "RW", "LW": "LW",
    }

    def _espn_get(self, url: str, retries: int = 3, params: Optional[Dict] = None):
        """ESPN API 使用独立请求，避免 500.com session 污染导致 403。"""
        code = self._espn_code_from_url(url)
        if self._espn_code_blocked(code):
            class _Blocked:
                status_code = 403
                def json(self):
                    return {}
            return _Blocked()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.espn.com/",
            "Origin": "https://www.espn.com",
        }
        last = None
        for attempt in range(retries):
            last = requests.get(url, headers=headers, params=params, timeout=20)
            if last.status_code != 403 or attempt >= retries - 1:
                if last.status_code == 403:
                    self._mark_espn_blocked(code, "http 403")
                return last
            time.sleep(1.5 * (attempt + 1))
        return last

    def _crawl_espn_squad_stats(
        self, league_id: str, espn_code: str, team_id: Optional[str] = None
    ) -> List[Dict]:
        """从 ESPN roster API 采集球员赛季统计。"""
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}/teams?limit=100"
        try:
            r = self._espn_get(url)
            if r.status_code != 200:
                logger.warning("ESPN teams %s returned %s", espn_code, r.status_code)
                return []
            payload = r.json()
        except Exception as e:
            logger.warning("ESPN teams fetch failed for %s: %s", espn_code, e)
            return []

        espn_teams = []
        used_ids: set = set()
        for sport in payload.get("sports") or []:
            for lg in sport.get("leagues") or []:
                for item in lg.get("teams") or []:
                    tm = item.get("team") or item
                    display = (tm.get("displayName") or tm.get("name") or "").strip()
                    short = (tm.get("shortDisplayName") or tm.get("abbreviation") or display).strip()
                    abbr = (tm.get("abbreviation") or "").strip().upper()
                    espn_tid = str(tm.get("id") or "")
                    if not espn_tid:
                        continue
                    sys_id = self._resolve_id(display, short, abbr, espn_tid, used_ids)
                    used_ids.add(sys_id)
                    espn_teams.append({"espn_id": espn_tid, "system_id": sys_id, "name": display})

        if team_id:
            espn_teams = [t for t in espn_teams if t["system_id"] == team_id]
            if not espn_teams:
                logger.warning("Team %s not found in ESPN league %s", team_id, espn_code)
                return []

        stats: List[Dict] = []
        for t in espn_teams:
            roster_url = (
                f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}"
                f"/teams/{t['espn_id']}/roster"
            )
            try:
                rr = self._espn_get(roster_url)
                if rr.status_code != 200:
                    logger.warning("ESPN roster %s returned %s", t["system_id"], rr.status_code)
                    continue
                team_stats = self._parse_espn_roster_stats(rr.json(), t["system_id"])
                stats.extend(team_stats)
                logger.info("ESPN stats %s: %s players", t["system_id"], len(team_stats))
            except Exception as e:
                logger.warning("ESPN roster failed for %s: %s", t["system_id"], e)
            time.sleep(0.25)
        return stats

    def _parse_espn_roster_stats(self, roster_data: Dict, system_team_id: str) -> List[Dict]:
        rows: List[Dict] = []
        for athlete in roster_data.get("athletes") or []:
            parsed = self._parse_espn_athlete_stats(athlete, system_team_id)
            if parsed:
                rows.append(parsed)
        return rows

    def _parse_espn_athlete_stats(self, athlete: Dict, system_team_id: str) -> Optional[Dict]:
        name = (athlete.get("displayName") or athlete.get("fullName") or "").strip()
        if not name:
            return None

        stats_map: Dict[str, int] = {}
        splits = (athlete.get("statistics") or {}).get("splits") or {}
        for cat in splits.get("categories") or []:
            for st in cat.get("stats") or []:
                try:
                    stats_map[st.get("name") or ""] = int(st.get("value") or 0)
                except (TypeError, ValueError):
                    stats_map[st.get("name") or ""] = 0

        pos = athlete.get("position") or {}
        pos_abbr = (pos.get("abbreviation") or pos.get("name") or "M").upper()
        position = self.ESPN_POSITION_MAP.get(pos_abbr, "CM")

        jersey = athlete.get("jersey")
        try:
            jersey_number = int(jersey) if jersey not in (None, "") else None
        except (TypeError, ValueError):
            jersey_number = None

        espn_id = str(athlete.get("id") or "")
        return {
            "id": f"PE{espn_id}"[:30] if espn_id else None,
            "name": name,
            "short_name": (athlete.get("shortName") or name)[:20],
            "jersey_number": jersey_number,
            "position": position,
            "team_id": system_team_id,
            "goals": stats_map.get("totalGoals", 0),
            "assists": stats_map.get("goalAssists", 0),
            "appearances": stats_map.get("appearances", 0),
            "yellow_cards": stats_map.get("yellowCards", 0),
            "red_cards": stats_map.get("redCards", 0),
        }

    def _crawl_team_lineup_stats(self, source_team_id: str, system_team_id: str) -> List[Dict]:
        html = self._get_html(f"https://liansai.500.com/team/{source_team_id}/teamlineup/")
        soup = BeautifulSoup(html, "html.parser")
        lineup = self._parse_lineup_table(soup, system_team_id)
        return list(lineup.values())

    def _parse_homepage_roster(self, soup: BeautifulSoup, system_team_id: str) -> Dict[str, Dict]:
        result = {}
        for dl in soup.select("div.lqiudmd dl.itm, dl.itm_smy, dl.itm_hw, dl.itm_zc, dl.itm_qf"):
            dt = dl.find("dt")
            group = dt.get_text(strip=True) if dt else ""
            pos = self.GROUP_POSITION.get(group, "CM")
            for dd in dl.find_all("dd"):
                player = self._player_from_dd(dd, system_team_id, pos)
                if player:
                    result[player["_src_pid"]] = player
        if not result:
            for a in soup.select('a[href*="/player/"]'):
                player = self._player_from_anchor(a, system_team_id, "CM")
                if player:
                    result[player["_src_pid"]] = player
        for item in result.values():
            item.pop("_src_pid", None)
        return result

    def _parse_lineup_table(self, soup: BeautifulSoup, system_team_id: str) -> Dict[str, Dict]:
        result = {}
        for row in soup.select("table.lqiuy_list tr"):
            a = row.find("a", href=re.compile(r"/player/"))
            if not a:
                continue
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            pos_text = ""
            for cell in cells:
                if cell in self.GROUP_POSITION:
                    pos_text = cell
                    break
            player = self._player_from_anchor(
                a, system_team_id, self.GROUP_POSITION.get(pos_text, "CM")
            )
            if not player:
                continue
            jersey = self._extract_jersey(cells)
            if jersey:
                player["jersey_number"] = jersey
            height = self._extract_int(r"(\d+)\s*cm", " ".join(cells))
            weight = self._extract_int(r"(\d+)\s*kg", " ".join(cells))
            if height:
                player["height"] = height
            if weight:
                player["weight"] = weight
            goals, assists, apps = self._extract_lineup_stats(cells)
            if apps:
                player["appearances"] = apps
            if goals:
                player["goals"] = goals
            if assists:
                player["assists"] = assists
            pid = player.pop("_src_pid")
            result[pid] = player
        return result

    def _player_from_dd(self, dd, system_team_id: str, position: str) -> Optional[Dict]:
        a = dd.find("a", href=True)
        if not a:
            return None
        player = self._player_from_anchor(a, system_team_id, position)
        if not player:
            return None
        em = dd.find("em")
        if em:
            jersey = self._extract_int(r"(\d+)", em.get_text())
            if jersey:
                player["jersey_number"] = jersey
        img = dd.find("img")
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            if src and "CharacterPic" in src:
                player["_img_src"] = src if src.startswith("http") else f"https:{src}" if src.startswith("//") else src
        return player

    def _player_from_anchor(self, a, system_team_id: str, position: str) -> Optional[Dict]:
        href = a.get("href") or ""
        m = re.search(r"/player/(\d+)-(\d+)/?", href)
        if not m:
            return None
        src_pid = m.group(2)
        name = (a.get("title") or a.get_text(strip=True) or "").strip()
        if not name or len(name) > 40:
            return None
        pos = position if position in {
            "GK", "CB", "RB", "LB", "DM", "CM", "AM", "RM", "LM", "RW", "LW", "ST"
        } else "CM"
        return {
            "id": f"P{src_pid}"[:30],
            "name": name,
            "short_name": name[:20],
            "jersey_number": None,
            "position": pos,
            "team_id": system_team_id,
            "nationality": "",
            "goals": 0,
            "assists": 0,
            "appearances": 0,
            "yellow_cards": 0,
            "red_cards": 0,
            "_src_pid": src_pid,
        }

    @staticmethod
    def _extract_jersey(cells: List[str]) -> Optional[int]:
        for cell in cells[:4]:
            if re.fullmatch(r"\d{1,2}", cell or ""):
                return int(cell)
        return None

    @staticmethod
    def _extract_int(pattern: str, text: str) -> Optional[int]:
        m = re.search(pattern, text or "", re.I)
        if not m:
            return None
        try:
            return int(m.group(1))
        except ValueError:
            return None

    @staticmethod
    def _extract_lineup_stats(cells: List[str]) -> Tuple[int, int, int]:
        nums = []
        for cell in cells:
            if re.fullmatch(r"\d+", cell or ""):
                nums.append(int(cell))
        goals = assists = apps = 0
        if len(nums) >= 4:
            apps = nums[-4] if nums[-4] < 80 else 0
            goals = nums[-3] if nums[-3] < 80 else 0
            assists = nums[-2] if nums[-2] < 80 else 0
        return goals, assists, apps

    # ===== 逐场球员统计（ESPN 单场 summary） =====

    def crawl_match_player_stats(
        self,
        league_id: str,
        home_team: Dict,
        away_team: Dict,
        match_date,
        home_goals: Optional[int] = None,
        away_goals: Optional[int] = None,
    ) -> List[Dict]:
        """从 ESPN 单场 summary 采集逐场球员统计。"""
        players, _teams = self.crawl_match_stats_bundle(
            league_id, home_team, away_team, match_date,
            home_goals=home_goals, away_goals=away_goals,
        )
        return players

    def crawl_match_stats_bundle(
        self,
        league_id: str,
        home_team: Dict,
        away_team: Dict,
        match_date,
        home_goals: Optional[int] = None,
        away_goals: Optional[int] = None,
    ) -> Tuple[List[Dict], List[Dict]]:
        """一次 summary：球员行 + 球队射门（boxscore 或球员聚合）。"""
        espn_code = ESPN_LEAGUE_MAP.get(league_id)
        if not espn_code or self._espn_code_blocked(espn_code):
            return [], []

        event_id = self._find_espn_event_id(
            espn_code,
            home_team,
            away_team,
            match_date,
            home_goals=home_goals,
            away_goals=away_goals,
        )
        if not event_id:
            return [], []

        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}/summary"
        try:
            r = self._espn_get(url, params={"event": event_id})
            if r.status_code != 200:
                logger.warning("ESPN summary %s returned %s", event_id, r.status_code)
                return [], []
            summary = r.json()
            players = self._parse_espn_match_summary(summary, home_team, away_team)
            teams = self._parse_espn_team_boxscore(summary, home_team, away_team)
            if not teams and players:
                teams = self.aggregate_team_shots_from_players(players, home_team, away_team)
            return players, teams
        except Exception as e:
            logger.warning("ESPN match summary failed for %s: %s", event_id, e)
            return [], []

    @staticmethod
    def aggregate_team_shots_from_players(
        players: List[Dict], home_team: Dict, away_team: Dict
    ) -> List[Dict]:
        home_id = (home_team or {}).get("id")
        away_id = (away_team or {}).get("id")
        buckets = {
            True: {"shots": 0, "sot": 0, "team_id": home_id},
            False: {"shots": 0, "sot": 0, "team_id": away_id},
        }
        for row in players or []:
            side = bool(row.get("is_home"))
            buckets[side]["shots"] += int(row.get("shots") or 0)
            buckets[side]["sot"] += int(row.get("shots_on_target") or 0)
            if row.get("team_id"):
                buckets[side]["team_id"] = row.get("team_id")
        out = []
        for is_home, b in buckets.items():
            if not b.get("team_id"):
                continue
            out.append({
                "team_id": b["team_id"],
                "is_home": is_home,
                "shots": b["shots"],
                "shots_on_target": b["sot"],
                "possession": None,
                "corners": None,
                "source": "espn_agg",
            })
        return out

    def _parse_espn_team_boxscore(
        self, summary: Dict, home_team: Dict, away_team: Dict
    ) -> List[Dict]:
        team_map = {"home": home_team, "away": away_team}
        box = (summary or {}).get("boxscore") or {}
        rows = []
        for block in box.get("teams") or []:
            side = block.get("homeAway")
            info = team_map.get(side)
            if not info or not info.get("id"):
                continue
            stats_map: Dict[str, float] = {}
            for st in block.get("statistics") or []:
                key = st.get("name") or st.get("abbreviation") or ""
                raw = st.get("value")
                if raw is None:
                    raw = st.get("displayValue")
                try:
                    stats_map[str(key)] = float(str(raw).replace("%", "").strip() or 0)
                except (TypeError, ValueError):
                    continue
            shots = int(
                stats_map.get("totalShots")
                or stats_map.get("shotsTotal")
                or stats_map.get("shots")
                or 0
            )
            sot = int(
                stats_map.get("shotsOnTarget")
                or stats_map.get("shotsOnGoal")
                or 0
            )
            possession = stats_map.get("possessionPct") or stats_map.get("possession")
            corners = stats_map.get("cornerKicks") or stats_map.get("corners")
            if shots <= 0 and sot <= 0 and possession is None:
                continue
            rows.append({
                "team_id": info["id"],
                "is_home": side == "home",
                "shots": shots,
                "shots_on_target": sot,
                "possession": round(float(possession), 2) if possession is not None else None,
                "corners": int(corners) if corners is not None else None,
                "source": "espn_box",
            })
        return rows

    def _find_espn_event_id(
        self,
        espn_code: str,
        home_team: Dict,
        away_team: Dict,
        match_date,
        home_goals: Optional[int] = None,
        away_goals: Optional[int] = None,
    ) -> Optional[str]:
        from datetime import timedelta

        if hasattr(match_date, "strftime"):
            base = match_date
            if hasattr(base, "date") and callable(base.date):
                try:
                    base = base.date()
                except Exception:
                    pass
        else:
            from datetime import datetime as _dt
            base = _dt.strptime(str(match_date)[:10], "%Y-%m-%d").date()

        # 赛程日可能与 ESPN 差 1~2 天（时区/延期）
        day_offsets = (0, -1, 1, -2, 2)
        candidates = []
        for off in day_offsets:
            day = base + timedelta(days=off)
            if day not in candidates:
                candidates.append(day)

        score_fallback: List[Tuple[str, int]] = []

        def _scan_events(events) -> Optional[str]:
            nonlocal score_fallback
            for event in events or []:
                comp = (event.get("competitions") or [{}])[0]
                espn_home = espn_away = None
                home_score = away_score = None
                for c in comp.get("competitors") or []:
                    side = c.get("homeAway")
                    team = c.get("team") or {}
                    try:
                        sc = int(float(c.get("score"))) if c.get("score") not in (None, "") else None
                    except (TypeError, ValueError):
                        sc = None
                    if side == "home":
                        espn_home = team
                        home_score = sc
                    elif side == "away":
                        espn_away = team
                        away_score = sc
                if self._espn_team_matches(home_team, espn_home) and self._espn_team_matches(
                    away_team, espn_away
                ):
                    return str(event.get("id") or "")
                # 单边匹配 + 比分一致：作缺场补采候选
                if home_goals is None or away_goals is None:
                    continue
                if home_score != home_goals or away_score != away_goals:
                    continue
                side_hits = int(self._espn_team_matches(home_team, espn_home)) + int(
                    self._espn_team_matches(away_team, espn_away)
                )
                if side_hits >= 1:
                    score_fallback.append((str(event.get("id") or ""), side_hits))
            return None

        for day in candidates:
            date_str = day.strftime("%Y%m%d")
            data = self._espn_scoreboard_json(espn_code, date_str)
            if not data:
                continue
            hit = _scan_events(data.get("events") or [])
            if hit:
                return hit

        # 日级未命中：用当月日期范围再扫一轮（ESPN 支持 YYYYMMDD-YYYYMMDD）
        month_start = base.replace(day=1)
        if base.month == 12:
            month_end = base.replace(year=base.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = base.replace(month=base.month + 1, day=1) - timedelta(days=1)
        range_str = f"{month_start.strftime('%Y%m%d')}-{month_end.strftime('%Y%m%d')}"
        data = self._espn_scoreboard_json(espn_code, range_str)
        if data:
            hit = _scan_events(data.get("events") or [])
            if hit:
                return hit

        if score_fallback:
            score_fallback.sort(key=lambda x: x[1], reverse=True)
            best_id, hits = score_fallback[0]
            if best_id and hits >= 1:
                logger.info(
                    "ESPN event score-assisted match: %s (side_hits=%s) for %s vs %s",
                    best_id, hits, home_team.get("id"), away_team.get("id"),
                )
                return best_id
        return None

    def _espn_team_matches(self, our_team: Dict, espn_team: Dict) -> bool:
        if not our_team or not espn_team:
            return False
        our_keys = self._espn_match_keyset(our_team, is_espn=False)
        espn_keys = self._espn_match_keyset(espn_team, is_espn=True)
        if our_keys & espn_keys:
            return True
        for our_name in our_keys:
            for espn_name in espn_keys:
                if len(our_name) >= 4 and (our_name in espn_name or espn_name in our_name):
                    return True
        return False

    def _espn_match_keyset(self, team: Dict, is_espn: bool = False) -> set:
        raw = {
            (team.get("id") or ""),
            (team.get("name") or ""),
            (team.get("short_name") or ""),
            (team.get("displayName") or ""),
            (team.get("shortDisplayName") or ""),
            (team.get("abbreviation") or ""),
        }
        if is_espn and team.get("id") is not None:
            raw.add(f"espn{team.get('id')}")
        keys = set()
        for item in raw:
            text = str(item).strip().lower()
            if not text or text == "none":
                continue
            keys.add(text)
            compact = re.sub(r"[\s\-_]+", "", text)
            if compact:
                keys.add(compact)
            # 系统归并别名（得到规范 ID）
            sys_alias = self._alias_lookup(text)
            if sys_alias:
                keys.add(sys_alias.lower())
            try:
                from services.team_alias_service import lookup_espn_abbrs
                tid = str(team.get("id") or sys_alias or "").strip()
                for abbr in lookup_espn_abbrs(tid):
                    keys.add(abbr.lower())
            except Exception:
                pass
            # 英文检索提示（消歧 / 中文队名）
            for candidate in (text, compact, (sys_alias or "").lower(), str(team.get("id") or "").lower()):
                if not candidate:
                    continue
                for hint in ESPN_NAME_HINTS.get(candidate, ()):
                    h = str(hint).strip().lower()
                    if not h:
                        continue
                    keys.add(h)
                    hc = re.sub(r"[\s\-_]+", "", h)
                    if hc:
                        keys.add(hc)
            # ESPN 对阵别名仅用于「我方」队名 → ESPN abbr；
            # 对 ESPN 侧再映射会把拜仁 MUN 误加成曼联 MAN
            if is_espn:
                continue
            for candidate in (text, compact, (sys_alias or "").lower(), str(team.get("id") or "").lower()):
                if not candidate:
                    continue
                espn_alias = ESPN_MATCH_ALIASES.get(candidate)
                if espn_alias:
                    keys.add(espn_alias.lower())
        return keys

    def _parse_espn_match_summary(
        self, summary: Dict, home_team: Dict, away_team: Dict
    ) -> List[Dict]:
        stats: List[Dict] = []
        team_map = {
            "home": home_team,
            "away": away_team,
        }
        for roster_block in summary.get("rosters") or []:
            side = roster_block.get("homeAway")
            team_info = team_map.get(side)
            if not team_info:
                continue
            team_id = team_info.get("id")
            for entry in roster_block.get("roster") or []:
                parsed = self._parse_espn_match_roster_entry(entry, team_id, side == "home")
                if parsed:
                    stats.append(parsed)
        return stats

    def _parse_espn_match_roster_entry(
        self, entry: Dict, team_id: str, is_home: bool
    ) -> Optional[Dict]:
        athlete = entry.get("athlete") or {}
        name = (athlete.get("displayName") or athlete.get("fullName") or "").strip()
        if not name:
            return None

        stats_map: Dict[str, float] = {}
        for st in entry.get("stats") or []:
            key = st.get("name") or ""
            try:
                stats_map[key] = float(st.get("value") or 0)
            except (TypeError, ValueError):
                stats_map[key] = 0.0

        if stats_map.get("appearances", 0) <= 0:
            return None

        pos = entry.get("position") or athlete.get("position") or {}
        pos_abbr = (pos.get("abbreviation") or pos.get("name") or "M").upper()
        if pos_abbr == "SUB":
            pos_abbr = "CM"
        position = self.ESPN_POSITION_MAP.get(pos_abbr, "CM")

        jersey = entry.get("jersey") or athlete.get("jersey")
        try:
            jersey_number = int(jersey) if jersey not in (None, "") else None
        except (TypeError, ValueError):
            jersey_number = None

        espn_id = str(athlete.get("id") or "")
        player_id = f"PE{espn_id}"[:30] if espn_id else None

        minutes = int(stats_map.get("minutesPlayed") or 0)
        if not minutes:
            starter = bool(entry.get("starter"))
            subbed_in = bool(entry.get("subbedIn"))
            subbed_out = bool(entry.get("subbedOut"))
            if starter and not subbed_out:
                minutes = 90
            elif starter and subbed_out:
                minutes = 70
            elif subbed_in and not subbed_out:
                minutes = 25
            elif subbed_in and subbed_out:
                minutes = 15
            else:
                minutes = 90 if starter else 0

        rating_val = stats_map.get("rating")
        rating = round(rating_val, 1) if rating_val else None

        return {
            "player_id": player_id,
            "player_name": name,
            "jersey_number": jersey_number,
            "team_id": team_id,
            "is_home": is_home,
            "position": position,
            "goals": int(stats_map.get("totalGoals") or 0),
            "assists": int(stats_map.get("goalAssists") or 0),
            "shots": int(stats_map.get("totalShots") or 0),
            "shots_on_target": int(stats_map.get("shotsOnTarget") or 0),
            "passes": int(stats_map.get("totalPasses") or 0),
            "pass_accuracy": round(stats_map.get("passPct"), 2) if stats_map.get("passPct") else None,
            "tackles": int(stats_map.get("totalTackles") or stats_map.get("effectiveTackles") or 0),
            "interceptions": int(stats_map.get("interceptions") or 0),
            "clearances": int(stats_map.get("totalClearance") or stats_map.get("effectiveClearance") or 0),
            "dribbles": int(stats_map.get("dribbles") or 0),
            "dribble_success": int(stats_map.get("successfulDribbles") or 0),
            "fouls_committed": int(stats_map.get("foulsCommitted") or 0),
            "fouls_suffered": int(stats_map.get("foulsSuffered") or 0),
            "yellow_cards": int(stats_map.get("yellowCards") or 0),
            "red_cards": int(stats_map.get("redCards") or 0),
            "minutes_played": minutes,
            "rating": rating,
        }
