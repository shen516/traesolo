"""500.com 单场技术统计（射门/射正）第二数据源。

优先解析 odds.500.com/fenxi/shuju-{fixture_id}.shtml；
失败时尝试 live.m.500.com 分析页文本。
写入目标为 match_team_stats，不造假球员行。
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SHOT_LABELS = ("射门", "总射门", "射门次数")
SOT_LABELS = ("射正", "射正球门", "射正次数")
POSS_LABELS = ("控球率", "控球")
CORNER_LABELS = ("角球",)


class Five00FenxiCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://odds.500.com/",
            }
        )

    def crawl_team_shots(
        self,
        fixture_id: str,
        home_team_id: str,
        away_team_id: str,
    ) -> List[Dict]:
        fid = str(fixture_id or "").strip()
        if not fid or not home_team_id or not away_team_id:
            return []
        home_shots = away_shots = home_sot = away_sot = None
        home_poss = away_poss = home_corners = away_corners = None

        for fetcher in (self._fetch_fenxi_shuju, self._fetch_mobile_analysis):
            try:
                text = fetcher(fid)
            except Exception as e:
                logger.debug("500 fenxi fetch %s failed: %s", fetcher.__name__, e)
                text = None
            if not text:
                continue
            soup = BeautifulSoup(text, "html.parser")
            pair = self._pair_from_tables(soup, SHOT_LABELS) or self._pair_from_text(text, SHOT_LABELS)
            sot_pair = self._pair_from_tables(soup, SOT_LABELS) or self._pair_from_text(text, SOT_LABELS)
            if pair:
                home_shots, away_shots = pair
            if sot_pair:
                home_sot, away_sot = sot_pair
            poss = self._pair_from_tables(soup, POSS_LABELS) or self._pair_from_text(text, POSS_LABELS)
            if poss:
                home_poss, away_poss = poss
            corners = self._pair_from_tables(soup, CORNER_LABELS) or self._pair_from_text(text, CORNER_LABELS)
            if corners:
                home_corners, away_corners = corners
            if home_shots is not None and away_shots is not None:
                break

        if home_shots is None or away_shots is None:
            return []
        if home_sot is None:
            home_sot = 0
        if away_sot is None:
            away_sot = 0

        return [
            {
                "team_id": home_team_id,
                "is_home": True,
                "shots": int(home_shots),
                "shots_on_target": int(home_sot),
                "possession": float(home_poss) if home_poss is not None else None,
                "corners": int(home_corners) if home_corners is not None else None,
                "source": "500_fenxi",
            },
            {
                "team_id": away_team_id,
                "is_home": False,
                "shots": int(away_shots),
                "shots_on_target": int(away_sot),
                "possession": float(away_poss) if away_poss is not None else None,
                "corners": int(away_corners) if away_corners is not None else None,
                "source": "500_fenxi",
            },
        ]

    def _fetch_fenxi_shuju(self, fixture_id: str) -> Optional[str]:
        url = f"https://odds.500.com/fenxi/shuju-{fixture_id}.shtml"
        r = self.session.get(url, timeout=20)
        if r.status_code != 200:
            return None
        try:
            return r.content.decode("gbk", errors="replace")
        except Exception:
            return r.text

    def _fetch_mobile_analysis(self, fixture_id: str) -> Optional[str]:
        url = f"https://live.m.500.com/detail/football/{fixture_id}/analysis/zj"
        r = self.session.get(url, timeout=20)
        if r.status_code != 200:
            return None
        return r.text

    @staticmethod
    def _pair_from_tables(soup: BeautifulSoup, labels: Tuple[str, ...]) -> Optional[Tuple[int, int]]:
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            joined = " ".join(cells)
            if not any(lab in joined for lab in labels):
                continue
            # 常见：主 | 指标 | 客
            nums = []
            for cell in cells:
                if any(lab in cell for lab in labels) and not re.search(r"\d", cell):
                    continue
                m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*%?", cell.replace(",", ""))
                if m:
                    nums.append(float(m.group(1)))
            if len(nums) >= 2:
                return int(nums[0]), int(nums[1])
            # 整行抽前两个数字
            all_nums = [int(x) for x in re.findall(r"\d+", joined)]
            if len(all_nums) >= 2:
                return all_nums[0], all_nums[1]
        return None

    @staticmethod
    def _pair_from_text(text: str, labels: Tuple[str, ...]) -> Optional[Tuple[int, int]]:
        for lab in labels:
            # 12 射门 10  或 射门 12-10
            patterns = [
                rf"(\d+)\s*{re.escape(lab)}\s*(\d+)",
                rf"{re.escape(lab)}\s*(\d+)\s*[-:：]\s*(\d+)",
                rf"{re.escape(lab)}\D+(\d+)\D+(\d+)",
            ]
            for pat in patterns:
                m = re.search(pat, text)
                if m:
                    return int(m.group(1)), int(m.group(2))
        return None


five00_fenxi_crawler = Five00FenxiCrawler()
