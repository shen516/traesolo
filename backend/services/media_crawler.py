"""下载联赛/球队/球员图片（仅当远程确实有图）。"""
import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
MEDIA_ROOT = BACKEND_ROOT / "static" / "media"
MIN_BYTES = 400
PLACEHOLDER_MARKERS = (
    "zanwutupian", "notfound", "placeholder", "noimage", "default.png", "nopic",
)

# football-data.org 联赛徽标（部分已失效，失败时回退 ESPN）
FD_LEAGUE_CRESTS = {
    "EPL": "https://crests.football-data.org/PL.png",
    "LALIGA": "https://crests.football-data.org/PD.png",
    "BUNDES": "https://crests.football-data.org/BL1.png",
    "SERIEA": "https://crests.football-data.org/SA.png",
    "LIGUE1": "https://crests.football-data.org/FL1.png",
    "UCL": "https://crests.football-data.org/CL.png",
    "UEL": "https://crests.football-data.org/EL.png",
    "MLS": "https://crests.football-data.org/MLS.png",
}

# ESPN scoreboard 联赛徽标（覆盖 FD 缺失的 WC/EC/BRA 等）
ESPN_LEAGUE_LOGOS = {
    "EPL": "https://a.espncdn.com/i/leaguelogos/soccer/500/23.png",
    "LALIGA": "https://a.espncdn.com/i/leaguelogos/soccer/500/15.png",
    "BUNDES": "https://a.espncdn.com/i/leaguelogos/soccer/500/10.png",
    "SERIEA": "https://a.espncdn.com/i/leaguelogos/soccer/500/12.png",
    "LIGUE1": "https://a.espncdn.com/i/leaguelogos/soccer/500/9.png",
    "UCL": "https://a.espncdn.com/i/leaguelogos/soccer/500/2.png",
    "UEL": "https://a.espncdn.com/i/leaguelogos/soccer/500/2310.png",
    "WC": "https://a.espncdn.com/i/leaguelogos/soccer/500/4.png",
    "EC": "https://a.espncdn.com/i/leaguelogos/soccer/500/74.png",
    "MLS": "https://a.espncdn.com/i/leaguelogos/soccer/500/19.png",
    "BRA": "https://a.espncdn.com/i/leaguelogos/soccer/500/85.png",
    "SWE": "https://a.espncdn.com/i/leaguelogos/soccer/500/54.png",
    "NOR": "https://a.espncdn.com/i/leaguelogos/soccer/500/2043.png",
    "FIN": "https://a.espncdn.com/i/leaguelogos/soccer/500/2046.png",
    "K1": "https://a.espncdn.com/i/leaguelogos/soccer/500/2023.png",
    "ECH": "https://a.espncdn.com/i/leaguelogos/soccer/500/24.png",  # 英冠
}

ESPN_TEAM_LOGO = "https://a.espncdn.com/i/teamlogos/soccer/500/{espn_id}.png"
ESPN_COUNTRY_FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/{code}.png"
ESPN_SEARCH_API = "https://site.web.api.espn.com/apis/common/v3/search"

# 常见规范球队 ID → ESPN 数字 ID（API 403 时的直链兜底）
ESPN_TEAM_IDS = {
    "ARS": "359", "AVL": "362", "BHA": "331", "BOU": "349", "BRE": "337",
    "CHE": "363", "CRY": "384", "EVE": "368", "FUL": "370", "LIV": "364",
    "MCI": "382", "MUN": "360", "NEW": "361", "NFO": "393", "SOU": "376",
    "TOT": "367", "WHU": "371", "WOL": "380", "LEE": "357", "LEI": "375",
    "IPS": "373", "SUN": "366",
    "RMA": "86", "BAR": "83", "ATM": "1068", "SEV": "243", "BIL": "93",
    "REAL_SOC": "89", "BET": "244", "VAL": "94", "VIL": "102", "CEL": "85",
    "GET": "2922", "OSA": "97", "RVA": "101",
    "BAY": "132", "DOR": "124", "LEV": "131", "RBL": "11420", "SGE": "125",
    "FRE": "126", "HOF": "7911", "WOB": "138", "VFB": "133", "MG": "129",
    "AUG": "3841", "KOL": "122", "MAI": "1294", "S04": "115", "UNB": "598",
    "JUV": "111", "INT": "110", "MIL": "103", "NAP": "114", "ROMA": "104",
    "LAZ": "118", "ATL": "105", "FIO": "109", "BOL": "107", "TOR": "239",
    "GEN": "326", "UDI": "113", "SAS": "3997", "MNZ": "17666",
    "PSG": "160", "ASM": "174", "OM": "176", "LYO": "167", "RCL": "175",
    "STR": "180", "T997": "167", "T998": "166", "T1134": "2502",
    "FCP": "437", "AJA": "139", "SHK": "493",
    "CAG": "2925", "DEP": "90", "LEC": "1041", "COM": "10759",
    "BOT": "6086", "FLA": "819", "STL": "12006", "DAL": "182",
    "VAL": "94", "MAL": "99", "ATLUTD": "18418",
}

TEAM_LOGO_URL = (
    "https://liansai.500.com/static/soccerdata/images/TeamPic/teamsignnew_{src_id}.png"
)
PLAYER_PHOTO_URLS = (
    "https://liansai.500.com/static/soccerdata/images/CharacterPic/characterpic1_{pid}.png",
    "https://liansai.500.com/static/soccerdata/images/CharacterPic/characterpic_{pid}.png",
    "https://liansai.500.com/static/soccerdata/images/CharacterPic/characterpic2_{pid}.png",
)
ESPN_PLAYER_PHOTO = "https://a.espncdn.com/i/headshots/soccer/players/full/{espn_id}.png"
ESPN_ATHLETE_API = "https://site.api.espn.com/apis/common/v3/sports/soccer/athletes/{espn_id}"

# ISO2 / 常用国家码 → ESPN countries 目录（世界杯国家队）
COUNTRY_FLAG_CODES = {
    "ALG": "alg", "ARG": "arg", "AUS": "aus", "AUT": "aut", "BEL": "bel",
    "BRA": "bra", "CAN": "can", "CHI": "chi", "CHN": "chn", "CIV": "civ",
    "CMR": "cmr", "COL": "col", "CRC": "crc", "CRO": "cro", "CZE": "cze",
    "DEN": "den", "ECU": "ecu", "EGY": "egy", "ENG": "eng", "ESP": "esp",
    "FIN": "fin", "FRA": "fra", "GER": "ger", "GHA": "gha", "GRE": "gre",
    "HUN": "hun", "IRN": "irn", "IRL": "irl", "ISL": "isl", "ITA": "ita",
    "JPN": "jpn", "KOR": "kor", "KSA": "ksa", "MAR": "mar", "MEX": "mex",
    "NED": "ned", "NGA": "nga", "NIR": "nir", "NOR": "nor", "NZL": "nzl",
    "PAR": "par", "PER": "per", "POL": "pol", "POR": "por", "QAT": "qat",
    "ROU": "rou", "RUS": "rus", "SCO": "sco", "SEN": "sen", "SRB": "srb",
    "SUI": "sui", "SVK": "svk", "SVN": "svn", "SWE": "swe", "TUN": "tun",
    "TUR": "tur", "UKR": "ukr", "URU": "uru", "USA": "usa", "WAL": "wal",
    "RSA": "rsa", "BIH": "bih", "COD": "cod", "CPV": "cpv", "CUW": "cuw",
    "HAI": "hai", "HTI": "hai", "SAF": "rsa", "IRQ": "irq", "JOR": "jor",
    "PAN": "pan", "SAU": "ksa", "UZB": "uzb",
}


def is_media_path(value) -> bool:
    if not value:
        return False
    text = str(value)
    return text.startswith(("http://", "https://", "/static/"))


def safe_id(entity_id: str) -> str:
    """生成可作文件名的 ID；含中文等非 ASCII 时附加短哈希，避免互相覆盖。"""
    s = str(entity_id or "").strip()
    if not s:
        return "unknown"
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", s)[:80]
    if re.search(r"[^A-Za-z0-9_-]", s):
        digest = hashlib.md5(s.encode("utf-8")).hexdigest()[:10]
        base = cleaned.strip("_")[:40] or "id"
        return f"{base}_{digest}"[:80]
    return cleaned or "unknown"


def public_url(kind: str, entity_id: str, ext: str = ".png") -> str:
    return f"/static/media/{kind}/{safe_id(entity_id)}{ext}"


def extract_source_pid(player_id: str) -> Optional[str]:
    """从球员 ID 提取 500.com 数字编号（不含 ESPN PE*）。"""
    if not player_id:
        return None
    s = str(player_id).strip()
    m = re.fullmatch(r"P(\d+)$", s)
    return m.group(1) if m else None


def extract_espn_id(player_id: str) -> Optional[str]:
    if not player_id:
        return None
    m = re.fullmatch(r"PE(\d+)", str(player_id).strip())
    return m.group(1) if m else None


class MediaCrawler:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        self.ensure_dirs()

    def ensure_dirs(self):
        for sub in ("leagues", "teams", "players"):
            (MEDIA_ROOT / sub).mkdir(parents=True, exist_ok=True)

    def dest(self, kind: str, entity_id: str, ext: str = ".png") -> Path:
        return MEDIA_ROOT / kind / f"{safe_id(entity_id)}{ext}"

    def download(self, url: str, dest: Path) -> bool:
        if dest.exists() and dest.stat().st_size >= MIN_BYTES:
            return True
        if not url or any(marker in url.lower() for marker in PLACEHOLDER_MARKERS):
            return False
        try:
            response = requests.get(url, timeout=15, headers=dict(self.session.headers))
            if response.status_code != 200:
                return False
            ctype = (response.headers.get("Content-Type") or "").lower()
            if "image" not in ctype and "octet-stream" not in ctype:
                return False
            data = response.content or b""
            if len(data) < MIN_BYTES:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return True
        except Exception as e:
            logger.debug("Image download failed %s: %s", url, e)
            return False

    def fetch_league_logo(self, league_id: str) -> Optional[str]:
        if not league_id:
            return None
        dest = self.dest("leagues", league_id)
        if dest.exists() and dest.stat().st_size >= MIN_BYTES:
            return public_url("leagues", league_id)
        for url in (
            FD_LEAGUE_CRESTS.get(league_id),
            ESPN_LEAGUE_LOGOS.get(league_id),
        ):
            if url and self.download(url, dest):
                return public_url("leagues", league_id)
        return None

    def fetch_team_logo(
        self,
        system_team_id: str,
        source_team_id: str = None,
        remote_url: str = None,
        espn_id: str = None,
        country_code: str = None,
        team_name: str = None,
    ) -> Optional[str]:
        if not system_team_id:
            return None
        dest = self.dest("teams", system_team_id)
        if dest.exists() and dest.stat().st_size >= MIN_BYTES:
            return public_url("teams", system_team_id)

        candidates = []
        if remote_url:
            candidates.append(remote_url)
        eid = espn_id or ESPN_TEAM_IDS.get(str(system_team_id).upper())
        if eid:
            candidates.append(ESPN_TEAM_LOGO.format(espn_id=eid))
        src = source_team_id
        if not src:
            m = re.fullmatch(r"T(\d+)", str(system_team_id))
            if m:
                src = m.group(1)
        if src:
            candidates.append(TEAM_LOGO_URL.format(src_id=src))
        code = (country_code or "").lower() or COUNTRY_FLAG_CODES.get(
            str(system_team_id or "").upper()
        )
        if code:
            candidates.append(ESPN_COUNTRY_FLAG.format(code=code))

        for url in candidates:
            if url and self.download(url, dest):
                return public_url("teams", system_team_id)

        # 搜索 API 兜底（不依赖 teams 列表接口）
        search_id = self._espn_team_id_from_search(team_name or system_team_id)
        if search_id:
            url = ESPN_TEAM_LOGO.format(espn_id=search_id)
            if self.download(url, dest):
                return public_url("teams", system_team_id)
        return None

    def _espn_team_id_from_search(self, query: str) -> Optional[str]:
        if not query or not str(query).strip():
            return None
        # 跳过明显脏 ID / 纯中文短噪声
        q = str(query).strip()
        if len(q) < 2:
            return None
        try:
            r = self.session.get(
                ESPN_SEARCH_API,
                params={"query": q, "limit": 8, "type": "team"},
                timeout=12,
                headers={
                    "User-Agent": self.session.headers.get("User-Agent", "Mozilla/5.0"),
                    "Referer": "https://www.espn.com/",
                },
            )
            if r.status_code != 200:
                return None
            for item in (r.json() or {}).get("items") or []:
                if (item.get("sport") or "").lower() != "soccer":
                    continue
                tid = str(item.get("id") or "").strip()
                if tid.isdigit():
                    return tid
        except Exception as e:
            logger.debug("ESPN team search failed %s: %s", query, e)
        return None

    def fetch_player_photo(
        self,
        player_id: str,
        source_pid: str = None,
        remote_url: str = None,
        source_team_id: str = None,
    ) -> Optional[str]:
        dest = self.dest("players", player_id)
        if dest.exists() and dest.stat().st_size >= MIN_BYTES:
            return public_url("players", player_id)

        if remote_url and self.download(remote_url, dest):
            return public_url("players", player_id)

        espn_id = extract_espn_id(player_id)
        if espn_id:
            # PE* 仅走 ESPN，勿用数字误打 500.com
            url = ESPN_PLAYER_PHOTO.format(espn_id=espn_id)
            if self.download(url, dest):
                return public_url("players", player_id)
            api_url = self._headshot_from_athlete_api(espn_id)
            if api_url and self.download(api_url, dest):
                return public_url("players", player_id)
            return None

        pid = source_pid or extract_source_pid(player_id)
        if pid:
            for tpl in PLAYER_PHOTO_URLS:
                url = tpl.format(pid=pid)
                if self.download(url, dest):
                    return public_url("players", player_id)
            if source_team_id:
                page_url = f"https://liansai.500.com/player/{source_team_id}-{pid}/"
                img_url = self._photo_from_player_page(page_url)
                if img_url and self.download(img_url, dest):
                    return public_url("players", player_id)

        return None

    def _headshot_from_athlete_api(self, espn_id: str) -> Optional[str]:
        try:
            r = self.session.get(ESPN_ATHLETE_API.format(espn_id=espn_id), timeout=12)
            if r.status_code != 200:
                return None
            ath = (r.json() or {}).get("athlete") or {}
            hs = ath.get("headshot") or {}
            href = hs.get("href") if isinstance(hs, dict) else None
            return href or None
        except Exception as e:
            logger.debug("Athlete API headshot failed %s: %s", espn_id, e)
            return None

    def _photo_from_player_page(self, page_url: str) -> Optional[str]:
        try:
            r = self.session.get(page_url, timeout=15)
            if r.status_code != 200:
                return None
            text = r.content.decode("gbk", errors="replace")
            for pat in (
                r'(https?://[^"\']+CharacterPic[^"\']+\.(?:png|jpg|jpeg))',
                r'(//[^"\']+CharacterPic[^"\']+\.(?:png|jpg|jpeg))',
            ):
                m = re.search(pat, text, re.I)
                if m:
                    url = m.group(1)
                    return url if url.startswith("http") else "https:" + url
        except Exception as e:
            logger.debug("Player page photo parse failed %s: %s", page_url, e)
        return None
