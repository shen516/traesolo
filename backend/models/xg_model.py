"""期望进球 (xG) 模型

基于 match_player_stats 的射门 / 射正历史，估计球队进攻 xG 与防守 xG（被造 xG），
再合成单场 λ，经泊松分布得到胜平负概率。

无逐场射门样本的球队回退到联赛先验，避免拖垮融合。
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple


class XGModel:
    """射门转化型期望进球模型。"""

    def __init__(
        self,
        home_advantage: float = 1.08,
        prior_xg_per_shot: float = 0.11,
        prior_xg_per_sot: float = 0.31,
        shrink_k: float = 4.0,
        min_matches: int = 2,
    ):
        self.home_advantage = float(home_advantage)
        self.prior_xg_per_shot = float(prior_xg_per_shot)
        self.prior_xg_per_sot = float(prior_xg_per_sot)
        self.shrink_k = float(shrink_k)
        self.min_matches = int(min_matches)
        # team_id -> params
        self.team_xg: Dict[str, dict] = {}
        # league_id -> priors
        self.league_priors: Dict[str, dict] = {}

    def set_team(self, team_id: str, params: dict):
        if not team_id:
            return
        self.team_xg[str(team_id)] = {
            "xg_for": float(params.get("xg_for", 1.35)),
            "xg_against": float(params.get("xg_against", 1.35)),
            "shots_pg": float(params.get("shots_pg", 12.0)),
            "sot_pg": float(params.get("sot_pg", 4.0)),
            "matches": int(params.get("matches", 0)),
            "league": params.get("league"),
        }

    def set_league_prior(self, league_id: str, prior: dict):
        if not league_id:
            return
        self.league_priors[str(league_id)] = {
            "xg_per_shot": float(prior.get("xg_per_shot", self.prior_xg_per_shot)),
            "xg_per_sot": float(prior.get("xg_per_sot", self.prior_xg_per_sot)),
            "xg_for_avg": float(prior.get("xg_for_avg", 1.35)),
            "shots_pg": float(prior.get("shots_pg", 12.0)),
            "sot_pg": float(prior.get("sot_pg", 4.0)),
            "matches": int(prior.get("matches", 0)),
        }

    def has_team(self, team_id: str) -> bool:
        p = self.team_xg.get(str(team_id) if team_id else "")
        return bool(p and int(p.get("matches") or 0) >= self.min_matches)

    def coverage(self, home_id: str, away_id: str) -> float:
        """0~1，双方有多少侧具备有效 xG 样本。"""
        n = int(self.has_team(home_id)) + int(self.has_team(away_id))
        return n / 2.0

    def _league_avg_xg(self, league_id: Optional[str]) -> float:
        if league_id and str(league_id) in self.league_priors:
            return float(self.league_priors[str(league_id)]["xg_for_avg"])
        return 1.35

    def _get_team(self, team_id: str, league_id: Optional[str] = None) -> dict:
        tid = str(team_id) if team_id else ""
        avg = self._league_avg_xg(league_id)
        base = {
            "xg_for": avg,
            "xg_against": avg,
            "shots_pg": 12.0,
            "sot_pg": 4.0,
            "matches": 0,
            "league": league_id,
        }
        if tid in self.team_xg:
            p = dict(self.team_xg[tid])
            n = max(0, int(p.get("matches") or 0))
            k = self.shrink_k
            p["xg_for"] = (n * float(p["xg_for"]) + k * avg) / (n + k)
            p["xg_against"] = (n * float(p["xg_against"]) + k * avg) / (n + k)
            return p
        return base

    def estimate_lambda(
        self,
        home_id: str,
        away_id: str,
        league_id: Optional[str] = None,
    ) -> Tuple[float, float]:
        home = self._get_team(home_id, league_id)
        away = self._get_team(away_id, league_id)
        league_avg = self._league_avg_xg(league_id) or 1.35

        home_factor = float(away["xg_against"]) / league_avg
        away_factor = float(home["xg_against"]) / league_avg
        lambda_home = float(home["xg_for"]) * home_factor * self.home_advantage
        lambda_away = float(away["xg_for"]) * away_factor
        return (
            max(0.15, min(4.5, lambda_home)),
            max(0.15, min(4.5, lambda_away)),
        )

    def predict_prob(
        self,
        home_id: str,
        away_id: str,
        league_id: Optional[str] = None,
        poisson_model=None,
    ) -> dict:
        """返回胜平负概率；传入 PoissonModel 时用比分矩阵。"""
        lh, la = self.estimate_lambda(home_id, away_id, league_id)
        if poisson_model is None:
            diff = lh - la
            home_win = 1 / (1 + 10 ** (-diff / 1.2))
            draw = max(0.18, 0.32 - abs(diff) * 0.08)
            away_win = max(0.05, 1.0 - home_win - draw)
            home_win = max(0.05, home_win - draw / 2)
            total = home_win + draw + away_win
            return {
                "home_win_prob": home_win / total,
                "draw_prob": draw / total,
                "away_win_prob": away_win / total,
                "lambda_home": lh,
                "lambda_away": la,
                "coverage": self.coverage(home_id, away_id),
            }
        result = poisson_model.predict(lh, la)
        result["lambda_home"] = lh
        result["lambda_away"] = la
        result["coverage"] = self.coverage(home_id, away_id)
        return result

    @staticmethod
    def match_team_xg_from_shots(
        shots: float,
        sot: float,
        xg_per_shot: float,
        xg_per_sot: float,
    ) -> float:
        shots = max(0.0, float(shots or 0))
        sot = max(0.0, float(sot or 0))
        return 0.40 * shots * float(xg_per_shot) + 0.60 * sot * float(xg_per_sot)
