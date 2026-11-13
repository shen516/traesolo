"""竞彩足球全玩法 SP 采集（trade.500.com/jczq）。

与 real_crawler._crawl_jczq_* 的区别：
- 以 500 侧主键 ``process_id + process_date`` 为唯一键，直接落 ``jingcai_match_odds`` 表，
  不做 team/league 名映射强约束，保证列表页不缺场次。
- 混合过关页（playid=312&g=2）仅主行胜平负/让球；扩展行 sbetbtn 为空，
  无法取比分/进球数/半全场，须由各独立玩法页补齐。
- 独立玩法页：进球数（playid=270）主行补 8 项、半全场（playid=272）主行补 9 项、
  比分（playid=271）扩展行补 31 项；单关（312&g=1）视图复用混过关主行。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# 主域名（数据行由页面内嵌 HTML 渲染，无需额外 ajax）
TRADE_BASE = "https://trade.500.com/jczq/"

# 玩法页 playid / 是否过关视图
PLAY_SPF = 269       # 胜平负（含让球）
PLAY_JQS = 270       # 进球数
PLAY_BF = 271        # 比分
PLAY_BQC = 272       # 半全场
PLAY_HHGG = 312      # 单关(g=1)/混合过关(g=2)

# 数据行投注按钮 data-type 映射到玩法 key
BTN_TYPE_MAP = {
    "spf": "spf",
    "nspf": "nspf",
    "bf": "bf",
    "jqs": "jqs",
    "bqc": "bqc",
}

# subactive 键 → 玩法 key + 单关/过关
# 实际源站键（jz.js）：bf=比分, bq=半全场, jq=进球数, dxq=大小球, hc=混合过关, spf/nspf=胜平负/让球
SUBACTIVE_KEYS = {
    "spfdg": ("spf", "dg"), "spfgg": ("spf", "gg"),
    "nspfdg": ("nspf", "dg"), "nspfgg": ("nspf", "gg"),
    "bfdg": ("bf", "dg"), "bfgg": ("bf", "gg"),
    "bqdg": ("bqc", "dg"), "bqgg": ("bqc", "gg"),
    "jqdg": ("jqs", "dg"), "jqgg": ("jqs", "gg"),
    "hcdg": ("hc", "dg"), "hcgg": ("hc", "gg"),
    "dxqdg": ("dxq", "dg"), "dxqgg": ("dxq", "gg"),
}

# 各玩法选项顺序（前端展示 & 后端排序用）
# 说明：500 页面 data-value 格式：
#   spf/nspf -> "3"/"1"/"0"
#   bf       -> "1:0"..."5:2" + "胜其它"/"平其它"/"负其它"
#   jqs      -> "0".."7"（7 代表 7+）
#   bqc      -> "3-3".."0-0"
PLAY_OPTION_ORDER = {
    "nspf": ["3", "1", "0"],
    "spf": ["3", "1", "0"],
    "bf": [
        "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "5:0",
        "5:1", "5:2", "0:0", "1:1", "2:2", "3:3", "0:1", "0:2", "1:2", "0:3",
        "1:3", "2:3", "0:4", "1:4", "2:4", "0:5", "1:5", "2:5", "胜其它", "平其它", "负其它",
    ],
    "jqs": ["0", "1", "2", "3", "4", "5", "6", "7"],
    "bqc": [
        "3-3", "3-1", "3-0", "1-3", "1-1", "1-0", "0-3", "0-1", "0-0",
    ],
}


def _num(value: Any) -> Optional[float]:
    """把 '3.45' / '3.45↑' / '-' 安全转 float。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "未开售", "—", ""):
        return None
    s = re.sub(r"[^\d.]", "", s)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_bool_attr(value: Any) -> bool:
    return str(value or "").strip() == "1"


class JingcaiTradeCrawler:
    """竞彩全玩法 SP 采集器。"""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Referer": TRADE_BASE,
            "Accept": "text/html,application/xhtml+xml",
        })

    # ---- 对外入口 ----

    def crawl(self, days_ahead: int = 7, days_back: int = 0) -> List[Dict[str, Any]]:
        """抓取在售 + 可选历史销售日的全玩法数据。

        days_back>0 且 days_ahead==0 时按历史日期回补（赛果对照用）。
        """
        buckets: List[Dict[str, Any]] = []
        # 混合过关页：仅主行胜平负/让球（扩展行 sbetbtn 为空，无法取 bf/jqs/bqc）
        buckets.extend(self._crawl_mix_page(days_ahead=days_ahead))
        # 独立玩法页补齐：进球数(270 主行)、半全场(272 主行)、比分(271 扩展行)
        buckets.extend(self._crawl_single_play(PLAY_JQS, days_ahead=days_ahead, play_key="jqs"))
        buckets.extend(self._crawl_single_play(PLAY_BQC, days_ahead=days_ahead, play_key="bqc"))
        buckets.extend(self._crawl_single_play(PLAY_BF, days_ahead=days_ahead, play_key="bf"))
        # 历史销售日回补（混过关 + 各独立玩法页）
        if int(days_back or 0) > 0 and int(days_ahead or 0) == 0:
            for offset in range(1, int(days_back) + 1):
                d = date.today() - timedelta(days=offset)
                ds = d.strftime("%Y-%m-%d")
                buckets.extend(self._crawl_mix_page(date_str=ds))
                buckets.extend(self._crawl_single_play(PLAY_JQS, date_str=ds, play_key="jqs"))
                buckets.extend(self._crawl_single_play(PLAY_BQC, date_str=ds, play_key="bqc"))
                buckets.extend(self._crawl_single_play(PLAY_BF, date_str=ds, play_key="bf"))
        return self._merge_rows(buckets)

    # ---- 页面抓取 ----

    def _fetch(self, url: str) -> Optional[str]:
        try:
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            for enc in ("gbk", "utf-8"):
                try:
                    return r.content.decode(enc, errors="replace")
                except Exception:
                    continue
            return r.text
        except Exception as e:  # noqa: BLE001
            logger.warning("Jingcai trade fetch failed (%s): %s", url, e)
            return None

    def _crawl_mix_page(self, days_ahead: int = 7, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """混合过关页（playid=312&g=2）抓全，返回按 process 主键去重的比赛列表。"""
        url = f"{TRADE_BASE}?playid={PLAY_HHGG}&g=2"
        if date_str:
            url += f"&date={date_str}"
        html = self._fetch(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        rows = self._parse_rows(soup, url, date_str=date_str)
        logger.info("Jingcai mix crawled %s rows from %s", len(rows), url)
        return rows

    def _crawl_single_play(
        self, play_id: int, days_ahead: int = 7, play_key: str = "", date_str: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """单玩法页（如进球数 270）抓取，用于补齐混过关页缺失的玩法。"""
        url = f"{TRADE_BASE}?playid={play_id}&g=2"
        if date_str:
            url += f"&date={date_str}"
        html = self._fetch(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        rows = self._parse_rows(soup, url, date_str=date_str, force_play=play_key)
        logger.info("Jingcai play%d crawled %s rows from %s", play_id, len(rows), url)
        return rows

    # ---- 行解析 ----

    def _merge_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """跨页合并相同 process_key 的行：保留完整 odds 与标量。"""
        merged: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            key = row["process_key"]
            existing = merged.get(key)
            if not existing:
                merged[key] = row
                continue
            # 合并玩法 SP（保留非空值）
            for play_key, play_odds in (row.get("odds") or {}).items():
                existing.setdefault("odds", {}).setdefault(play_key, {})
                for opt, sp in play_odds.items():
                    if sp is not None:
                        existing["odds"][play_key][opt] = sp
            # 补齐缺失标量
            for k in ("subactive", "kdg", "is_end", "home_goals", "away_goals", "result"):
                if row.get(k) not in (None, "", {}, []) and existing.get(k) in (None, "", {}, []):
                    existing[k] = row[k]
        return list(merged.values())

    def _parse_rows(
        self, soup: BeautifulSoup, url: str,
        date_str: Optional[str] = None, force_play: str = "",
    ) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        seen: Dict[str, Dict[str, Any]] = {}
        for tr in soup.select("table.bet-tb tr.bet-tb-tr"):
            item = self._parse_row(tr, date_str, force_play=force_play)
            if not item:
                continue
            key = item["process_key"]
            existing = seen.get(key)
            if existing:
                # 合并：单玩法页仅补齐对应玩法 SP，不覆盖混过关完整数据
                for play_key, play_odds in (item.get("odds") or {}).items():
                    existing.setdefault("odds", {}).setdefault(play_key, {})
                    for opt, sp in play_odds.items():
                        if sp is not None:
                            existing["odds"][play_key][opt] = sp
                # 补齐其他标量字段（仅当缺失）
                for k in ("subactive", "kdg", "is_end"):
                    if item.get(k) not in (None, "", {}, []) and existing.get(k) in (None, "", {}, []):
                        existing[k] = item[k]
                continue
            seen[key] = item
            matches.append(item)
        return matches

    def _parse_row(
        self, tr, date_str: Optional[str] = None, force_play: str = "",
    ) -> Optional[Dict[str, Any]]:
        try:
            process_id = (tr.get("data-processid") or "").strip()
            process_date = (tr.get("data-processdate") or date_str or "").strip()
            if not process_id or not process_date:
                return None

            # 基础信息
            home_name = (tr.get("data-homesxname") or "").strip()
            away_name = (tr.get("data-awaysxname") or "").strip()
            if not home_name or not away_name:
                # 兜底从 td[3] 的 VS 文本解析
                tds = tr.find_all("td", recursive=False)
                if len(tds) >= 4:
                    vs = tds[3].get_text(" ", strip=True)
                    m = re.match(r"(.+?)\s+[Vv][Ss]\s+(.+)", vs)
                    if m:
                        home_name, away_name = m.group(1).strip(), m.group(2).strip()
            if not home_name or not away_name:
                return None

            process_key = f"{process_id}|{process_date}"
            is_end = _parse_bool_attr(tr.get("data-isend"))

            odds: Dict[str, Dict[str, Optional[float]]] = {}
            subactive: Dict[str, bool] = self._parse_subactive(tr)

            # 主行胜平负/让球
            odds.update(self._extract_main_sp(tr))
            # 扩展行：比分/进球数/半全场
            odds.update(self._extract_extra_sp(tr))

            # 让球盘口
            handicap = self._parse_handicap(tr)

            # 单关可用性：data-kdg 或 subactive 中任一玩法 dg=1
            kdg = _parse_bool_attr(tr.get("data-kdg"))
            if not kdg:
                kdg = any(
                    subactive.get(p, {}).get("dg", False)
                    for p in ("spf", "nspf", "bf", "bqc", "jqs", "hc")
                )

            # 赛果（历史对照）
            home_goals, away_goals, result = self._parse_result(tr, is_end)

            match_date, match_time = self._parse_match_time(tr, process_date)

            return {
                "process_key": process_key,
                "process_id": process_id,
                "process_date": process_date,
                "match_num": (tr.get("data-matchnum") or "").strip(),
                "fixture_id": (tr.get("data-fixtureid") or "").strip() or None,
                "match_id": (tr.get("data-matchid") or "").strip() or None,
                "home_team_id": (tr.get("data-homeid") or "").strip() or None,
                "away_team_id": (tr.get("data-awayid") or "").strip() or None,
                "league_name": (tr.get("data-simpleleague") or "").strip(),
                "league_rank": (tr.get("data-simpleleagueid") or "").strip() or None,
                "home_name": home_name,
                "away_name": away_name,
                "match_date": match_date,
                "match_time": match_time,
                "buy_end_time": (tr.get("data-buyendtime") or "").strip() or None,
                "is_end": is_end,
                "handicap": handicap,
                "kdg": kdg,
                "subactive": subactive,
                "odds": odds,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "result": result,
                "source": "500_trade_mix",
            }
        except Exception as e:  # noqa: BLE001
            logger.debug("Jingcai row parse failed: %s", e)
            return None

    def _parse_subactive(self, tr) -> Dict[str, Dict[str, bool]]:
        """解析 subactive 为嵌套结构：{"spf": {"dg": true, "gg": true}, ...}。"""
        out: Dict[str, Dict[str, bool]] = {}
        raw = (tr.get("data-subactive") or "").strip()
        for pair in raw.split(","):
            if ":" not in pair:
                continue
            k, v = pair.split(":", 1)
            play, mode = SUBACTIVE_KEYS.get(k.strip(), (None, None))
            if play:
                out.setdefault(play, {})[mode] = v.strip() == "1"
        return out

    def _extract_main_sp(self, tr) -> Dict[str, Dict[str, Optional[float]]]:
        """主行胜平负/让球：data-type in (spf, nspf) 的按钮。

        单玩法页（如进球数 270）的按钮也在主行，data-type 为该玩法（jqs/bf/bqc），
        一并收集，便于独立页作为混过关的补齐源。
        """
        out: Dict[str, Dict[str, Optional[float]]] = {}
        for btn in tr.select("p.betbtn"):
            btype = (btn.get("data-type") or "").strip()
            if btype not in BTN_TYPE_MAP:
                continue
            value = (btn.get("data-value") or "").strip()
            sp = _num(btn.get("data-sp"))
            out.setdefault(btype, {})[value] = sp
        return out

    def _extract_extra_sp(self, tr) -> Dict[str, Dict[str, Optional[float]]]:
        """扩展行比分/进球数/半全场：bet-more-wrap 内 sbetbtn。"""
        out: Dict[str, Dict[str, Optional[float]]] = {}
        wrap = self._find_extra_wrap(tr)
        if not wrap:
            return out
        for btn in wrap.select("p.sbetbtn"):
            btype = (btn.get("data-type") or "").strip()
            if btype not in BTN_TYPE_MAP:
                continue
            value = (btn.get("data-value") or "").strip()
            sp = _num(btn.get("data-sp"))
            out.setdefault(btype, {})[value] = sp
        return out

    def _find_extra_wrap(self, tr):
        """定位本场扩展行（比分/进球数/半全场），兼容源站缺失 </tr> 的畸形结构。"""
        for child in tr.children:
            if getattr(child, "name", None) != "tr":
                continue
            classes = child.get("class") or []
            if "bet-more-wrap" in classes:
                return child
            if "bet-tb-tr" in classes:
                return None
        nxt = tr.find_next_sibling("tr")
        if nxt and "bet-more-wrap" in (nxt.get("class") or []):
            return nxt
        return None

    def _parse_handicap(self, tr) -> Optional[int]:
        raw = (tr.get("data-rangqiu") or "").strip()
        if not raw:
            return None
        try:
            return int(float(raw))
        except ValueError:
            return None

    def _parse_result(self, tr, is_end: bool):
        """从行内 .team-bf / a.team-bf 提取赛果。"""
        home_goals = away_goals = result = None
        score_el = tr.select_one(".team-bf, a.team-bf")
        if not score_el:
            return home_goals, away_goals, result
        txt = score_el.get_text(strip=True)
        if ":" not in txt:
            return home_goals, away_goals, result
        parts = txt.split(":")
        try:
            home_goals = int(parts[0])
            away_goals = int(parts[1])
            if home_goals > away_goals:
                result = "H"
            elif home_goals < away_goals:
                result = "A"
            else:
                result = "D"
        except ValueError:
            pass
        return home_goals, away_goals, result

    def _parse_match_time(self, tr, process_date: str):
        """解析开赛时间；无明确日期时用销售日。"""
        match_date_attr = (tr.get("data-matchdate") or "").strip()
        match_time_attr = (tr.get("data-matchtime") or "").strip()
        mdate = match_date_attr or process_date
        if match_time_attr and ":" in match_time_attr and "-" not in match_time_attr:
            try:
                dt = datetime.strptime(f"{mdate} {match_time_attr}", "%Y-%m-%d %H:%M")
                return dt.date(), dt.strftime("%H:%M")
            except ValueError:
                pass
        try:
            d = datetime.strptime(mdate, "%Y-%m-%d").date()
            return d, match_time_attr
        except ValueError:
            return None, match_time_attr


# 便于外部复用：按玩法取选项顺序
def option_order(play: str) -> List[str]:
    return PLAY_OPTION_ORDER.get(play, [])


# 供 crawler_service 复用：把采集结果落库前的归一化（可选）
def normalize_odds_for_play(row: Dict[str, Any], play: str) -> Dict[str, Optional[float]]:
    """从采集行中取出某玩法的 {option: sp}。"""
    return (row.get("odds") or {}).get(play) or {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawler = JingcaiTradeCrawler()
    rows = crawler.crawl(days_ahead=1)
    print(f"crawled {len(rows)} rows")
    for r in rows[:3]:
        print(r["process_key"], r["home_name"], "vs", r["away_name"], r["odds"])
