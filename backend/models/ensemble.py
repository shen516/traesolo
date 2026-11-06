"""多模型融合 - 加权组合 ELO + 泊松 + xG + 蒙特卡洛"""
import yaml
from pathlib import Path
from .poisson_model import PoissonModel
from .elo_model import EloModel
from .monte_carlo import MonteCarloSimulator
from .xg_model import XGModel


class EnsembleModel:
    """多模型加权融合预测引擎"""

    WEIGHT_KEYS = ("elo", "poisson", "xg", "monte_carlo")

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        p_cfg = self.config.get("poisson", {})
        e_cfg = self.config.get("elo", {})
        mc_cfg = self.config.get("monte_carlo", {})
        x_cfg = self.config.get("xg", {})

        self.poisson = PoissonModel(max_goals=p_cfg.get("max_goals", 10))
        self.elo = EloModel(
            k_factor=e_cfg.get("k_factor", 32),
            home_advantage=e_cfg.get("home_advantage", 100),
            initial_rating=e_cfg.get("initial_rating", 1500),
        )
        self.monte_carlo = MonteCarloSimulator(
            simulations=mc_cfg.get("simulations", 10000)
        )
        self.xg = XGModel(
            home_advantage=float(x_cfg.get("home_advantage", 1.08)),
            prior_xg_per_shot=float(x_cfg.get("prior_xg_per_shot", 0.11)),
            prior_xg_per_sot=float(x_cfg.get("prior_xg_per_sot", 0.31)),
            shrink_k=float(x_cfg.get("shrink_k", 4.0)),
            min_matches=int(x_cfg.get("min_matches", 2)),
        )

        raw = self.config.get("ensemble", {}).get("weights", {})
        self.league_weights = {}
        ens_cfg = self.config.get("ensemble", {}) or {}
        min_cfg = ens_cfg.get("min_league_samples", 40)
        self.min_league_samples = int(min_cfg) if min_cfg else 40
        soft_cfg = ens_cfg.get("soft_league_samples", 20)
        soft_n = int(soft_cfg) if soft_cfg is not None else 20
        # soft 不得高于 min；至少为 1
        self.soft_league_samples = max(1, min(soft_n, self.min_league_samples))

        # 权重 EMA：小样本联赛对新网格结果更保守
        sm_cfg = ens_cfg.get("weight_smoothing") or {}
        prior = sm_cfg.get("prior_strength", self.min_league_samples)
        self.weight_smoothing = {
            "enabled": bool(sm_cfg.get("enabled", True)),
            "prior_strength": float(prior if prior is not None else self.min_league_samples),
            "min_alpha": float(sm_cfg.get("min_alpha", 0.20)),
            "max_alpha": float(sm_cfg.get("max_alpha", 0.85)),
        }

        # MC 权重上下限：降低与泊松共线
        self.max_monte_carlo_weight = float(ens_cfg.get("max_monte_carlo_weight", 0.28) or 0.28)
        self.min_monte_carlo_weight = float(ens_cfg.get("min_monte_carlo_weight", 0.05) or 0.05)
        if self.max_monte_carlo_weight < self.min_monte_carlo_weight:
            self.max_monte_carlo_weight = self.min_monte_carlo_weight

        # 时间衰减
        td_cfg = ens_cfg.get("time_decay") or {}
        self.time_decay = {
            "enabled": bool(td_cfg.get("enabled", True)),
            "half_life_days": float(td_cfg.get("half_life_days", 180) or 180),
        }

        # 评测配置
        ev_cfg = ens_cfg.get("evaluation") or {}
        self.evaluation = {
            "primary_metric": str(ev_cfg.get("primary_metric") or "brier").lower(),
            "walk_forward_folds": int(ev_cfg.get("walk_forward_folds") or 3),
            "calibration_bins": int(ev_cfg.get("calibration_bins") or 5),
        }

        self.weights = self._normalize_weights({
            "elo": float(raw.get("elo", 0.30)),
            "poisson": float(raw.get("poisson", 0.30)),
            "xg": float(raw.get("xg", 0.22)),
            "monte_carlo": float(raw.get("monte_carlo", 0.18)),
        })

        # 全局 / 分联赛超参（主场优势、ELO K）
        hp_cfg = ens_cfg.get("hyperparams") or {}
        self.global_hyperparams = {
            "elo_k": float(e_cfg.get("k_factor", 32)),
            "elo_home_advantage": float(e_cfg.get("home_advantage", 100)),
            "poisson_home_advantage": float(p_cfg.get("home_advantage", 1.15)),
        }
        self.league_hyperparams = {}
        self.hyperparam_options = {
            "elo_k": [float(x) for x in (hp_cfg.get("elo_k_options") or [20, 24, 28, 32, 36, 40])],
            "elo_home_advantage": [
                float(x) for x in (hp_cfg.get("elo_home_advantage_options") or [50, 75, 100, 125, 150])
            ],
            "poisson_home_advantage": [
                float(x) for x in (
                    hp_cfg.get("poisson_home_advantage_options") or [1.05, 1.10, 1.15, 1.20, 1.25]
                )
            ],
        }

        # 无库数据时的回退参数
        self.team_params = {
            "MCI": {"attack": 1.35, "defense": 0.75, "league": "EPL", "name": "曼城"},
            "ARS": {"attack": 1.20, "defense": 0.80, "league": "EPL", "name": "阿森纳"},
            "LIV": {"attack": 1.28, "defense": 0.85, "league": "EPL", "name": "利物浦"},
            "CHE": {"attack": 1.00, "defense": 0.95, "league": "EPL", "name": "切尔西"},
            "MUN": {"attack": 0.95, "defense": 1.00, "league": "EPL", "name": "曼联"},
            "TOT": {"attack": 1.10, "defense": 0.92, "league": "EPL", "name": "热刺"},
            "RMA": {"attack": 1.38, "defense": 0.72, "league": "LALIGA", "name": "皇马"},
            "BAR": {"attack": 1.30, "defense": 0.78, "league": "LALIGA", "name": "巴萨"},
            "ATM": {"attack": 1.10, "defense": 0.85, "league": "LALIGA", "name": "马竞"},
            "BAY": {"attack": 1.42, "defense": 0.70, "league": "BUNDES", "name": "拜仁"},
            "DOR": {"attack": 1.15, "defense": 0.95, "league": "BUNDES", "name": "多特"},
            "JUV": {"attack": 1.05, "defense": 0.88, "league": "SERIEA", "name": "尤文"},
            "INT": {"attack": 1.18, "defense": 0.82, "league": "SERIEA", "name": "国米"},
            "MIL": {"attack": 1.08, "defense": 0.90, "league": "SERIEA", "name": "AC米兰"},
            "PSG": {"attack": 1.32, "defense": 0.80, "league": "LIGUE1", "name": "巴黎"},
            "BRA": {"attack": 1.40, "defense": 0.78, "league": "WC", "name": "巴西"},
            "ARG": {"attack": 1.35, "defense": 0.80, "league": "WC", "name": "阿根廷"},
            "FRA": {"attack": 1.33, "defense": 0.76, "league": "WC", "name": "法国"},
            "ENG": {"attack": 1.28, "defense": 0.79, "league": "WC", "name": "英格兰"},
            "ESP": {"attack": 1.25, "defense": 0.81, "league": "WC", "name": "西班牙"},
            "GER": {"attack": 1.22, "defense": 0.83, "league": "WC", "name": "德国"},
            "NED": {"attack": 1.20, "defense": 0.85, "league": "WC", "name": "荷兰"},
            "POR": {"attack": 1.18, "defense": 0.86, "league": "WC", "name": "葡萄牙"},
            "ITA": {"attack": 1.10, "defense": 0.88, "league": "WC", "name": "意大利"},
            "BEL": {"attack": 1.12, "defense": 0.87, "league": "WC", "name": "比利时"},
            "URU": {"attack": 1.10, "defense": 0.90, "league": "WC", "name": "乌拉圭"},
            "CRO": {"attack": 1.08, "defense": 0.90, "league": "WC", "name": "克罗地亚"},
            "MAR": {"attack": 1.03, "defense": 0.92, "league": "WC", "name": "摩洛哥"},
            "JPN": {"attack": 1.05, "defense": 0.91, "league": "WC", "name": "日本"},
            "USA": {"attack": 1.02, "defense": 0.92, "league": "WC", "name": "美国"},
            "MEX": {"attack": 0.99, "defense": 0.94, "league": "WC", "name": "墨西哥"},
            "KOR": {"attack": 1.00, "defense": 0.93, "league": "WC", "name": "韩国"},
            "SEN": {"attack": 0.99, "defense": 0.94, "league": "WC", "name": "塞内加尔"},
            "DEN": {"attack": 1.00, "defense": 0.94, "league": "WC", "name": "丹麦"},
            "COL": {"attack": 1.08, "defense": 0.92, "league": "WC", "name": "哥伦比亚"},
            "SUI": {"attack": 1.02, "defense": 0.93, "league": "WC", "name": "瑞士"},
        }

        self.league_avg = p_cfg.get("league_avg_goals", {
            "EPL": 2.85, "LALIGA": 2.50, "BUNDES": 3.10,
            "SERIEA": 2.60, "LIGUE1": 2.70, "UCL": 2.80,
            "WC": 2.65
        })
        self.home_advantage = float(p_cfg.get("home_advantage", 1.15))

    def _normalize_weights(self, weights: dict) -> dict:
        elo = max(0.0, float(weights.get("elo", 0)))
        poisson = max(0.0, float(weights.get("poisson", 0)))
        xg = max(0.0, float(weights.get("xg", 0)))
        mc = max(0.0, float(weights.get("monte_carlo", 0)))
        max_mc = float(getattr(self, "max_monte_carlo_weight", 0.28) or 0.28)
        min_mc = float(getattr(self, "min_monte_carlo_weight", 0.05) or 0.0)
        if mc > max_mc:
            poisson += mc - max_mc
            mc = max_mc
        total = elo + poisson + xg + mc
        if total <= 0:
            return {"elo": 0.30, "poisson": 0.30, "xg": 0.22, "monte_carlo": 0.18}
        out = {
            "elo": elo / total,
            "poisson": poisson / total,
            "xg": xg / total,
            "monte_carlo": mc / total,
        }
        if out["monte_carlo"] < min_mc and min_mc > 0:
            deficit = min_mc - out["monte_carlo"]
            take = min(deficit, out["poisson"] * 0.5)
            out["poisson"] -= take
            out["monte_carlo"] += take
        return out

    def set_weights(self, weights: dict):
        """设置全局权重；若 payload 含 by_league / global 则走 apply_weights_payload。"""
        if weights and ("by_league" in weights or "global" in weights):
            self.apply_weights_payload(weights)
            return
        self.weights = self._normalize_weights(weights or {})

    def smoothing_alpha(self, sample_n: int) -> float:
        """样本自适应平滑系数：α = clamp(n / (n + prior_strength), min, max)。"""
        cfg = self.weight_smoothing or {}
        if not cfg.get("enabled", True):
            return 1.0
        n = max(0.0, float(sample_n or 0))
        k = max(0.0, float(cfg.get("prior_strength", 40)))
        min_a = float(cfg.get("min_alpha", 0.20))
        max_a = float(cfg.get("max_alpha", 0.85))
        if max_a < min_a:
            min_a, max_a = max_a, min_a
        if k <= 0:
            alpha = 1.0
        else:
            alpha = n / (n + k)
        return max(min_a, min(max_a, alpha))

    def blend_weights(self, league_weights: dict, global_weights: dict, beta: float) -> dict:
        """按 beta 混合联赛权重与全局：w = β·league + (1-β)·global。"""
        b = max(0.0, min(1.0, float(beta)))
        lw = self._normalize_weights(league_weights or {})
        gw = self._normalize_weights(global_weights or self.weights)
        if b >= 0.999:
            return lw
        if b <= 0.001:
            return gw
        mixed = {
            k: b * float(lw.get(k, 0)) + (1.0 - b) * float(gw.get(k, 0))
            for k in self.WEIGHT_KEYS
        }
        return self._normalize_weights(mixed)

    def soft_blend_beta(self, sample_n: int) -> float:
        """小样本向全局收缩的信任系数：n/min_league_samples，封顶 1。"""
        n = max(0, int(sample_n or 0))
        denom = max(1, int(self.min_league_samples or 40))
        return min(1.0, n / float(denom))

    def smooth_weights(self, new_weights: dict, prev_weights: dict = None, sample_n: int = None):
        """
        指数平滑：w = α·new + (1-α)·prev，再归一化。
        无旧权重或关闭平滑时直接返回新权重；返回 (weights, alpha)。
        """
        new_n = self._normalize_weights(new_weights or {})
        if not prev_weights or not isinstance(prev_weights, dict):
            return new_n, 1.0
        cfg = self.weight_smoothing or {}
        if not cfg.get("enabled", True):
            return new_n, 1.0
        prev_n = self._normalize_weights(prev_weights)
        alpha = self.smoothing_alpha(sample_n if sample_n is not None else 0)
        if alpha >= 0.999:
            return new_n, alpha
        if alpha <= 0.001:
            return prev_n, alpha
        blended = {
            k: alpha * float(new_n.get(k, 0)) + (1.0 - alpha) * float(prev_n.get(k, 0))
            for k in self.WEIGHT_KEYS
        }
        return self._normalize_weights(blended), alpha

    def set_league_weights(self, league_weights: dict):
        """league_id -> 归一化权重 dict。"""
        cleaned = {}
        for lid, w in (league_weights or {}).items():
            if not lid or not isinstance(w, dict):
                continue
            raw = w.get("weights") if isinstance(w.get("weights"), dict) else w
            cleaned[str(lid)] = self._normalize_weights(raw)
        self.league_weights = cleaned

    def get_weights_for_league(self, league_id) -> dict:
        if league_id and str(league_id) in self.league_weights:
            return self.league_weights[str(league_id)]
        return self.weights

    def _normalize_hyperparams(self, raw: dict = None) -> dict:
        base = dict(self.global_hyperparams or {})
        if not raw or not isinstance(raw, dict):
            return {
                "elo_k": float(base.get("elo_k", 32)),
                "elo_home_advantage": float(base.get("elo_home_advantage", 100)),
                "poisson_home_advantage": float(base.get("poisson_home_advantage", 1.15)),
            }
        return {
            "elo_k": float(raw.get("elo_k", base.get("elo_k", 32))),
            "elo_home_advantage": float(
                raw.get("elo_home_advantage", base.get("elo_home_advantage", 100))
            ),
            "poisson_home_advantage": float(
                raw.get("poisson_home_advantage", base.get("poisson_home_advantage", 1.15))
            ),
        }

    def get_hyperparams_for_league(self, league_id) -> dict:
        if league_id and str(league_id) in self.league_hyperparams:
            return self._normalize_hyperparams(self.league_hyperparams[str(league_id)])
        return self._normalize_hyperparams(self.global_hyperparams)

    def set_global_hyperparams(self, hyperparams: dict):
        hp = self._normalize_hyperparams(hyperparams)
        self.global_hyperparams = hp
        self.elo.k = hp["elo_k"]
        self.elo.home_advantage = hp["elo_home_advantage"]
        self.home_advantage = hp["poisson_home_advantage"]
        # xG 主场优势随泊松超参小幅联动（保持相对比例）
        try:
            x_cfg = (self.config or {}).get("xg") or {}
            base_p = float(((self.config or {}).get("poisson") or {}).get("home_advantage", 1.15))
            base_x = float(x_cfg.get("home_advantage", 1.08))
            if base_p > 0:
                self.xg.home_advantage = max(1.0, base_x * (hp["poisson_home_advantage"] / base_p))
        except Exception:
            pass

    def set_league_hyperparams(self, league_hyperparams: dict):
        cleaned = {}
        for lid, hp in (league_hyperparams or {}).items():
            if not lid or not isinstance(hp, dict):
                continue
            cleaned[str(lid)] = self._normalize_hyperparams(hp)
        self.league_hyperparams = cleaned

    def apply_weights_payload(self, payload: dict):
        """
        兼容两种存储格式:
        - 旧: {elo, poisson, monte_carlo}
        - 新: {global: {...}, by_league: {EPL: {elo..}|{weights:{elo..}}, hyperparams?}, hyperparams?}
        """
        if not payload or not isinstance(payload, dict):
            return
        if "global" in payload or "by_league" in payload:
            global_w = payload.get("global") or {
                k: payload[k] for k in ("elo", "poisson", "xg", "monte_carlo") if k in payload
            }
            if global_w:
                self.weights = self._normalize_weights(global_w)
            if isinstance(payload.get("hyperparams"), dict):
                self.set_global_hyperparams(payload["hyperparams"])
            by_league = payload.get("by_league") or {}
            cleaned = {}
            cleaned_hp = {}
            for lid, meta in by_league.items():
                if not isinstance(meta, dict):
                    continue
                raw = meta.get("weights") if isinstance(meta.get("weights"), dict) else meta
                if any(k in raw for k in ("elo", "poisson", "xg", "monte_carlo")):
                    cleaned[str(lid)] = self._normalize_weights(raw)
                if isinstance(meta.get("hyperparams"), dict):
                    cleaned_hp[str(lid)] = self._normalize_hyperparams(meta["hyperparams"])
            self.league_weights = cleaned
            if cleaned_hp:
                self.league_hyperparams = cleaned_hp
            return
        self.weights = self._normalize_weights(payload)

    def export_weights_payload(self, league_meta: dict = None) -> dict:
        """导出可写入 model_versions.weights_json 的结构。"""
        by_league = {}
        meta = league_meta or {}
        lids = set(self.league_weights or {}) | set(self.league_hyperparams or {}) | set(meta or {})
        for lid in lids:
            w = (self.league_weights or {}).get(str(lid)) or self.weights
            entry = {"weights": {k: round(v, 4) for k, v in w.items()}}
            hp = (self.league_hyperparams or {}).get(str(lid))
            extra = meta.get(lid) or meta.get(str(lid)) or {}
            if not hp and isinstance(extra.get("hyperparams"), dict):
                hp = extra["hyperparams"]
            if hp:
                entry["hyperparams"] = {
                    "elo_k": round(float(hp.get("elo_k", 32)), 2),
                    "elo_home_advantage": round(float(hp.get("elo_home_advantage", 100)), 2),
                    "poisson_home_advantage": round(float(hp.get("poisson_home_advantage", 1.15)), 4),
                }
            for key in (
                "validation_accuracy", "validation_matches", "train_matches",
                "source", "sample_n", "hyper_source", "smooth_alpha", "blend_beta",
            ):
                if key in extra:
                    entry[key] = extra[key]
            by_league[str(lid)] = entry
        ghp = self._normalize_hyperparams(self.global_hyperparams)
        return {
            "elo": round(self.weights.get("elo", 0), 4),
            "poisson": round(self.weights.get("poisson", 0), 4),
            "xg": round(self.weights.get("xg", 0), 4),
            "monte_carlo": round(self.weights.get("monte_carlo", 0), 4),
            "global": {k: round(v, 4) for k, v in self.weights.items()},
            "hyperparams": {
                "elo_k": round(ghp["elo_k"], 2),
                "elo_home_advantage": round(ghp["elo_home_advantage"], 2),
                "poisson_home_advantage": round(ghp["poisson_home_advantage"], 4),
            },
            "by_league": by_league,
        }

    def predict(self, home_team, away_team, *, home_params=None, away_params=None,
                elo_home=None, elo_away=None, league_avg=None, weights=None, league_id=None,
                weather=None, temperature=None, pitch_condition=None,
                lambda_override=None, xg_lambda_override=None,
                poisson_home_advantage=None, simulations=None, seed=None,
                max_goals=None, detailed_mc=False):
        """
        完整预测流程:
        1. 泊松  2. ELO  3. xG  4. 蒙特卡洛  5. 加权融合（权重归一化）
        home_params / away_params: {attack, defense, xg_for?, xg_against?, league, name?}
        weights / league_id: 优先显式权重，否则按联赛权重，再回退全局。
        weather / temperature / pitch_condition: 环境修正（作用于 λ 路径）。
        模拟预测可选覆盖参数（默认 None 时行为与生产路径一致）：
        - lambda_override: {"home": x, "away": y} 显式泊松 λ（环境修正仍生效）
        - xg_lambda_override: {"home": x, "away": y} 显式 xG λ
        - poisson_home_advantage: 覆盖主场优势系数
        - simulations / seed: 蒙特卡洛次数与种子
        - max_goals: 比分矩阵上限（detailed_mc 时生效）
        - detailed_mc: True 时用 simulate_detailed 输出 mc_detailed
        """
        home = home_params or self._get_team_params(home_team)
        away = away_params or self._get_team_params(away_team)
        lid = league_id or home.get("league")
        avg = league_avg if league_avg is not None else self.league_avg.get(lid, 2.70)
        self._hydrate_xg_from_params(home_team, home, lid)
        self._hydrate_xg_from_params(away_team, away, lid)

        hp = self.get_hyperparams_for_league(lid)
        poisson_ha = float(hp.get("poisson_home_advantage", self.home_advantage))
        if poisson_home_advantage is not None:
            poisson_ha = float(poisson_home_advantage)
        elo_ha = float(hp.get("elo_home_advantage", self.elo.home_advantage))

        if lambda_override and (lambda_override.get("home") or lambda_override.get("away")):
            lambda_home = float(lambda_override.get("home") or 0) or self.poisson.calculate_lambda(
                float(home["attack"]), float(away["defense"]), float(avg),
                is_home=True, home_adv=poisson_ha,
            )
            lambda_away = float(lambda_override.get("away") or 0) or self.poisson.calculate_lambda(
                float(away["attack"]), float(home["defense"]), float(avg),
                is_home=False, home_adv=poisson_ha,
            )
        else:
            lambda_home = self.poisson.calculate_lambda(
                float(home["attack"]), float(away["defense"]), float(avg),
                is_home=True, home_adv=poisson_ha,
            )
            lambda_away = self.poisson.calculate_lambda(
                float(away["attack"]), float(home["defense"]), float(avg),
                is_home=False, home_adv=poisson_ha,
            )

        env_adjust = self._apply_environment(
            lambda_home, lambda_away,
            weather=weather, temperature=temperature, pitch_condition=pitch_condition,
        )
        lambda_home = env_adjust["lambda_home"]
        lambda_away = env_adjust["lambda_away"]

        poisson_result = self.poisson.predict(lambda_home, lambda_away)

        # 临时套用联赛级 xG 主场优势
        old_xg_ha = self.xg.home_advantage
        try:
            x_cfg = (self.config or {}).get("xg") or {}
            base_p = float(((self.config or {}).get("poisson") or {}).get("home_advantage", 1.15)) or 1.15
            base_x = float(x_cfg.get("home_advantage", 1.08))
            self.xg.home_advantage = max(1.0, base_x * (poisson_ha / base_p))
            elo_result = self.elo.predict_prob(
                home_team, away_team,
                rating_a=elo_home, rating_b=elo_away,
                home_advantage=elo_ha,
            )
            elo_h = int(elo_home) if elo_home is not None else self.elo.get_rating(home_team)
            elo_a = int(elo_away) if elo_away is not None else self.elo.get_rating(away_team)

            xg_result = self.xg.predict_prob(
                home_team, away_team, league_id=lid, poisson_model=self.poisson
            )
        finally:
            self.xg.home_advantage = old_xg_ha

        xg_coverage = float(xg_result.get("coverage") or 0)
        # 显式 xG λ 覆盖：用泊松模型重建 xG 概率，coverage 标记为 1
        if xg_lambda_override and (xg_lambda_override.get("home") or xg_lambda_override.get("away")):
            xg_lh_o = float(xg_lambda_override.get("home") or 0) or float(xg_result.get("lambda_home") or 0)
            xg_la_o = float(xg_lambda_override.get("away") or 0) or float(xg_result.get("lambda_away") or 0)
            if xg_lh_o > 0 and xg_la_o > 0:
                rebuilt = self.poisson.predict(xg_lh_o, xg_la_o)
                rebuilt["lambda_home"] = xg_lh_o
                rebuilt["lambda_away"] = xg_la_o
                rebuilt["coverage"] = 1.0
                xg_result = rebuilt
                xg_coverage = 1.0
        # xG 路径同样套用环境系数，与泊松一致
        if abs(env_adjust["lambda_factor"] - 1.0) > 1e-6:
            xg_lh = float(xg_result.get("lambda_home") or 0) * env_adjust["lambda_factor"]
            xg_la = float(xg_result.get("lambda_away") or 0) * env_adjust["lambda_factor"]
            if xg_lh > 0 or xg_la > 0:
                adj = self.poisson.predict(xg_lh, xg_la)
                adj["lambda_home"] = xg_lh
                adj["lambda_away"] = xg_la
                adj["coverage"] = xg_coverage
                xg_result = adj

        # 蒙特卡洛：泊松 λ 与 xG λ 混合，降低与纯泊松路径的高度相关
        xg_lh = float(xg_result.get("lambda_home") or 0)
        xg_la = float(xg_result.get("lambda_away") or 0)
        mc_blend = 0.0
        if xg_coverage > 0 and (xg_lh > 0 or xg_la > 0):
            mc_blend = min(0.55, 0.35 + 0.2 * xg_coverage)
            mc_lh = (1.0 - mc_blend) * float(lambda_home) + mc_blend * xg_lh
            mc_la = (1.0 - mc_blend) * float(lambda_away) + mc_blend * xg_la
        else:
            mc_lh, mc_la = float(lambda_home), float(lambda_away)
        mc_detailed = None
        if detailed_mc:
            mc_detailed = self.monte_carlo.simulate_detailed(
                mc_lh, mc_la,
                simulations=simulations, seed=seed,
                max_goals=max_goals if max_goals is not None else 8,
            )
            mc_result = {
                "home_win_prob": mc_detailed["home_win_prob"],
                "draw_prob": mc_detailed["draw_prob"],
                "away_win_prob": mc_detailed["away_win_prob"],
                "top_scores": [(t["score"], t["prob"]) for t in mc_detailed["top_scores"][:5]],
                "total_goals_avg": mc_detailed["total_goals_avg"],
                "total_goals_std": mc_detailed["total_goals_std"],
            }
        elif simulations is not None or seed is not None:
            mc_result = MonteCarloSimulator(
                simulations=int(simulations) if simulations else self.monte_carlo.simulations,
                seed=seed,
            ).simulate(mc_lh, mc_la)
        else:
            mc_result = self.monte_carlo.simulate(mc_lh, mc_la)

        if weights is not None:
            w = self._normalize_weights(weights)
            weight_source = "explicit"
        elif lid and str(lid) in self.league_weights:
            w = self._normalize_weights(self.league_weights[str(lid)])
            weight_source = f"league:{lid}"
        else:
            w = self._normalize_weights(self.weights)
            weight_source = "global"

        warnings: list = []
        # 显式权重被 MC 上下限约束调整时提示
        if weights is not None:
            raw_mc = float(weights.get("monte_carlo", 0) or 0)
            if abs(raw_mc - w.get("monte_carlo", 0)) > 1e-6 and raw_mc > 0:
                warnings.append("蒙特卡洛权重已按生产约束调整")

        # 双方都无 xG 样本时，把 xg 权重并入泊松，避免先验噪声
        if xg_coverage <= 0 and w.get("xg", 0) > 0:
            w = self._normalize_weights({
                "elo": w.get("elo", 0),
                "poisson": w.get("poisson", 0) + w.get("xg", 0),
                "xg": 0,
                "monte_carlo": w.get("monte_carlo", 0),
            })
            warnings.append("xG 样本不足，已将 xG 权重并入泊松路径")

        final_home_win = (
            w["poisson"] * poisson_result["home_win_prob"]
            + w["elo"] * elo_result["home_win_prob"]
            + w["xg"] * xg_result["home_win_prob"]
            + w["monte_carlo"] * mc_result["home_win_prob"]
        )
        final_away_win = (
            w["poisson"] * poisson_result["away_win_prob"]
            + w["elo"] * elo_result["away_win_prob"]
            + w["xg"] * xg_result["away_win_prob"]
            + w["monte_carlo"] * mc_result["away_win_prob"]
        )
        final_draw = (
            w["poisson"] * poisson_result.get("draw_prob", 0)
            + w["elo"] * elo_result["draw_prob"]
            + w["xg"] * xg_result.get("draw_prob", 0)
            + w["monte_carlo"] * mc_result["draw_prob"]
        )
        # 若泊松未显式给平局，用残差补齐后再归一
        if final_draw <= 0:
            final_draw = max(0.01, 1.0 - final_home_win - final_away_win)
        total = final_home_win + final_away_win + final_draw
        final_home_win /= total
        final_away_win /= total
        final_draw /= total

        max_prob = max(final_home_win, final_away_win, final_draw)
        confidence = self._calc_confidence(max_prob)
        risk_level = self._calc_risk(max_prob, home, away)
        if env_adjust.get("risk_boost") and risk_level == "low":
            risk_level = "mid"
        elif env_adjust.get("risk_boost") and risk_level == "mid":
            risk_level = "high"
        if env_adjust.get("risk_boost") and confidence == "high":
            confidence = "mid"
        tendency = self._build_tendency(final_home_win, final_away_win, final_draw)

        home_name = home.get("name") or home_team
        away_name = away.get("name") or away_team
        key_variables = self._extract_key_variables(home_team, away_team, home_name, away_name)
        if env_adjust.get("weather") or env_adjust.get("pitch_condition"):
            env_tag = " / ".join(
                x for x in (
                    env_adjust.get("weather"),
                    env_adjust.get("pitch_condition"),
                    env_adjust.get("temperature"),
                ) if x
            )
            if env_tag:
                key_variables = list(key_variables)[:2] + [f"环境:{env_tag}"]
        analysis = self._build_analysis(
            home_name, away_name, final_home_win, final_away_win,
            lambda_home, lambda_away, tendency
        )
        if env_adjust.get("applied") and abs(env_adjust["lambda_factor"] - 1.0) > 1e-6:
            analysis = (
                f"{analysis} 环境修正系数 {env_adjust['lambda_factor']:.2f}"
                f"（天气 {env_adjust.get('weather') or '-'} / "
                f"草坪 {env_adjust.get('pitch_condition') or '-'}）。"
            )
        total_goals = self._calc_total_goals(mc_result["total_goals_avg"])

        from services.analysis_scenarios import (
            SCENARIO_ENSEMBLE,
            SCENARIO_ELO,
            SCENARIO_MONTE_CARLO,
            SCENARIO_POISSON,
            SCENARIO_XG,
            build_scenarios_payload,
            scenario_label,
        )

        scenario_block = build_scenarios_payload(
            league_id=lid,
            xg_coverage=xg_coverage,
            ensemble_weights=w,
            poisson=poisson_result,
            elo=elo_result,
            xg=xg_result,
            mc=mc_result,
            poisson_main_score=poisson_result.get("main_score"),
            poisson_alt_scores=poisson_result.get("alt_scores"),
            xg_main_score=xg_result.get("main_score"),
            mc_top_scores=mc_result.get("top_scores"),
        )
        primary = scenario_block.get("primary_scenario") or SCENARIO_ENSEMBLE
        scenario_reason = scenario_block.get("scenario_reason") or ""

        # 默认顶栏结论 = 整合版；缺数时自动切到主场景（配置可关）
        sc_cfg = (self.config or {}).get("ensemble", {}).get("analysis_scenarios") or {}
        scenarios_enabled = bool(sc_cfg.get("enabled", True))
        apply_primary = scenarios_enabled and bool(sc_cfg.get("apply_primary", True))
        display_home, display_draw, display_away = final_home_win, final_draw, final_away_win
        display_weights = w
        display_weight_source = weight_source
        display_main = poisson_result.get("main_score")
        display_alts = poisson_result.get("alt_scores")
        display_total = total_goals
        display_matrix = poisson_result.get("score_matrix")

        if apply_primary and primary != SCENARIO_ENSEMBLE:
            pack = (scenario_block.get("scenarios") or {}).get(primary) or {}
            display_home = float(pack.get("home_win_prob", display_home))
            display_draw = float(pack.get("draw_prob", display_draw))
            display_away = float(pack.get("away_win_prob", display_away))
            display_weights = pack.get("weights") or display_weights
            display_weight_source = f"scenario:{primary}"
            if primary == SCENARIO_POISSON:
                display_main = poisson_result.get("main_score")
                display_alts = poisson_result.get("alt_scores")
                display_matrix = poisson_result.get("score_matrix")
            elif primary == SCENARIO_XG and xg_result.get("main_score"):
                display_main = xg_result.get("main_score")
                display_alts = xg_result.get("alt_scores") or display_alts
                display_matrix = xg_result.get("score_matrix") or display_matrix
            elif primary == SCENARIO_MONTE_CARLO:
                tops = mc_result.get("top_scores") or []
                if tops and isinstance(tops[0], (list, tuple)):
                    display_main = str(tops[0][0])
                    display_alts = [str(t[0]) for t in tops[1:4] if t]
                display_total = self._calc_total_goals(mc_result.get("total_goals_avg") or 0)
            elif primary == SCENARIO_ELO:
                display_main = None
                display_alts = []
                # 保留泊松矩阵作参考，前端可提示

            max_prob = max(display_home, display_away, display_draw)
            confidence = self._calc_confidence(max_prob)
            risk_level = self._calc_risk(max_prob, home, away)
            if env_adjust.get("risk_boost") and risk_level == "low":
                risk_level = "mid"
            elif env_adjust.get("risk_boost") and risk_level == "mid":
                risk_level = "high"
            if env_adjust.get("risk_boost") and confidence == "high":
                confidence = "mid"
            tendency = self._build_tendency(display_home, display_away, display_draw)
            analysis = self._build_analysis(
                home_name, away_name, display_home, display_away,
                lambda_home, lambda_away, tendency,
            )
            analysis = (
                f"【主结论·{scenario_label(primary)}】{analysis} "
                f"（{scenario_reason}）"
            )
        else:
            if apply_primary and primary == SCENARIO_ENSEMBLE and scenario_reason:
                analysis = f"{analysis} （场景：整合版 — {scenario_reason}）"

        return {
            "home_win_prob": round(display_home, 4),
            "draw_prob": round(display_draw, 4),
            "away_win_prob": round(display_away, 4),
            "lambda_home": round(lambda_home, 2),
            "lambda_away": round(lambda_away, 2),
            "main_score": display_main,
            "alt_scores": display_alts,
            "total_goals": display_total,
            "tendency": tendency,
            "confidence": confidence,
            "risk_level": risk_level,
            "key_variables": key_variables,
            "analysis": analysis,
            "score_matrix": display_matrix,
            "elo_home": elo_h,
            "elo_away": elo_a,
            "mc_top_scores": mc_result["top_scores"],
            "xg_home": round(float(xg_result.get("lambda_home") or 0), 2),
            "xg_away": round(float(xg_result.get("lambda_away") or 0), 2),
            "xg_coverage": round(xg_coverage, 2),
            "mc_lambda_home": round(mc_lh, 2),
            "mc_lambda_away": round(mc_la, 2),
            "mc_blend": round(mc_blend, 3),
            "weights_used": {k: round(float(v), 4) for k, v in (display_weights or {}).items()},
            "weight_source": display_weight_source,
            "league_id": lid,
            "hyperparams_used": {
                "elo_k": round(float(hp.get("elo_k", 32)), 2),
                "elo_home_advantage": round(elo_ha, 2),
                "poisson_home_advantage": round(poisson_ha, 4),
            },
            "env_adjust": {
                "weather": env_adjust.get("weather"),
                "temperature": env_adjust.get("temperature"),
                "pitch_condition": env_adjust.get("pitch_condition"),
                "lambda_factor": env_adjust.get("lambda_factor"),
                "weather_factor": env_adjust.get("weather_factor"),
                "pitch_factor": env_adjust.get("pitch_factor"),
                "applied": env_adjust.get("applied"),
            },
            "primary_scenario": primary,
            "scenario_reason": scenario_reason,
            "espn_pipeline": scenario_block.get("espn_pipeline"),
            "scenarios": scenario_block.get("scenarios"),
            "scenario_order": scenario_block.get("scenario_order"),
            "ensemble_probs": {
                "home_win_prob": round(final_home_win, 4),
                "draw_prob": round(final_draw, 4),
                "away_win_prob": round(final_away_win, 4),
                "weights_used": {k: round(v, 4) for k, v in w.items()},
                "weight_source": weight_source,
            },
            "components": {
                "poisson": {
                    "home_win_prob": round(float(poisson_result.get("home_win_prob") or 0), 4),
                    "draw_prob": round(float(poisson_result.get("draw_prob") or 0), 4),
                    "away_win_prob": round(float(poisson_result.get("away_win_prob") or 0), 4),
                },
                "elo": {
                    "home_win_prob": round(float(elo_result.get("home_win_prob") or 0), 4),
                    "draw_prob": round(float(elo_result.get("draw_prob") or 0), 4),
                    "away_win_prob": round(float(elo_result.get("away_win_prob") or 0), 4),
                },
                "xg": {
                    "home_win_prob": round(float(xg_result.get("home_win_prob") or 0), 4),
                    "draw_prob": round(float(xg_result.get("draw_prob") or 0), 4),
                    "away_win_prob": round(float(xg_result.get("away_win_prob") or 0), 4),
                },
                "monte_carlo": {
                    "home_win_prob": round(float(mc_result.get("home_win_prob") or 0), 4),
                    "draw_prob": round(float(mc_result.get("draw_prob") or 0), 4),
                    "away_win_prob": round(float(mc_result.get("away_win_prob") or 0), 4),
                },
            },
            "warnings": warnings,
            "mc_detailed": mc_detailed,
        }

    def predict_from_db(self, db, home_team_id, away_team_id, match_id=None):
        """从数据库加载球队/联赛参数后预测；可选 match_id 读取环境字段。"""
        from services import TeamService, LeagueService

        home_team = TeamService.get_by_id(db, home_team_id)
        away_team = TeamService.get_by_id(db, away_team_id)

        home_params = self._params_from_orm(home_team, home_team_id)
        away_params = self._params_from_orm(away_team, away_team_id)

        league_id = (home_team.league_id if home_team else None) or home_params.get("league")
        league_avg = None
        if league_id:
            league = LeagueService.get_by_id(db, league_id)
            if league and league.avg_goals is not None:
                league_avg = float(league.avg_goals)
            else:
                league_avg = self.league_avg.get(league_id, 2.70)

        elo_home = int(home_team.elo_rating) if home_team and home_team.elo_rating else None
        elo_away = int(away_team.elo_rating) if away_team and away_team.elo_rating else None
        if elo_home is not None:
            self.elo.set_rating(home_team_id, elo_home)
        if elo_away is not None:
            self.elo.set_rating(away_team_id, elo_away)

        weather = temperature = pitch_condition = None
        if match_id:
            from services import MatchService
            match = MatchService.get_by_id(db, match_id)
            if match:
                weather = match.weather or None
                temperature = match.temperature or None
                pitch_condition = match.pitch_condition or None
                # 缺环境时尝试即时补全（不阻塞预测）
                if not weather or not pitch_condition:
                    try:
                        from services.environment_service import environment_service
                        if environment_service.enrich_orm_match(db, match):
                            db.commit()
                            weather = match.weather or weather
                            temperature = match.temperature or temperature
                            pitch_condition = match.pitch_condition or pitch_condition
                            environment_service.ensure_risk_alerts(db, match)
                    except Exception:
                        pass

        prior_meta = self._apply_soft_priors(
            db, home_params, away_params, league_id, home_team_id, away_team_id,
            match_id=match_id,
        )

        from services.ensemble_registry import ensure_weights_current
        ensure_weights_current()

        result = self.predict(
            home_team_id, away_team_id,
            home_params=home_params,
            away_params=away_params,
            elo_home=elo_home,
            elo_away=elo_away,
            league_avg=league_avg,
            league_id=league_id,
            weather=weather,
            temperature=temperature,
            pitch_condition=pitch_condition,
        )
        if prior_meta:
            result["soft_priors"] = prior_meta
        return result

    def _apply_soft_priors(
        self,
        db,
        home_params,
        away_params,
        league_id,
        home_team_id,
        away_team_id,
        match_id=None,
    ):
        """用积分榜 / 射手榜 / 球员阵容 / 伤停预警做轻微攻防微调（可关）。"""
        cfg = (self.config or {}).get("soft_priors") or {}
        if not cfg.get("enabled", False) or not league_id:
            return None
        try:
            from services import StandingService, ScorerService, PlayerService
        except Exception:
            return None

        min_played = int(cfg.get("min_played") or 3)
        sw = float(cfg.get("standings_weight") or 0.05)
        gw = float(cfg.get("scorers_weight") or 0.03)
        pw = float(cfg.get("players_weight") or 0.03)
        iw = float(cfg.get("injury_weight") or 0.02)
        min_player_apps = int(cfg.get("min_player_apps") or 1)
        min_squad_players = int(cfg.get("min_squad_players") or 5)
        # 阵容指数差约 ±0.15（进球+0.5助攻 / 出场）时触及 players_weight 上限
        players_scale = float(cfg.get("players_scale") or 0.15)
        injury_scale = float(cfg.get("injury_scale") or 3.0)

        home_row = StandingService.get_team_row(db, league_id, home_team_id)
        away_row = StandingService.get_team_row(db, league_id, away_team_id)
        standings_adj = 0.0
        if (
            home_row and away_row
            and int(home_row.played or 0) >= min_played
            and int(away_row.played or 0) >= min_played
        ):
            hppg = float(home_row.points or 0) / max(int(home_row.played), 1)
            appg = float(away_row.points or 0) / max(int(away_row.played), 1)
            # 场均积分差约 ±1.5 时触及上限
            standings_adj = max(-sw, min(sw, (hppg - appg) / 1.5 * sw))

        home_share = ScorerService.team_goals_share(db, league_id, home_team_id)
        away_share = ScorerService.team_goals_share(db, league_id, away_team_id)
        scorers_adj = max(-gw, min(gw, (home_share - away_share) * gw * 4))

        home_squad = PlayerService.team_squad_index(
            db, home_team_id, min_apps=min_player_apps, min_players=min_squad_players
        )
        away_squad = PlayerService.team_squad_index(
            db, away_team_id, min_apps=min_player_apps, min_players=min_squad_players
        )
        players_adj = 0.0
        if home_squad and away_squad and players_scale > 0 and pw > 0:
            delta = float(home_squad["index"]) - float(away_squad["index"])
            players_adj = max(-pw, min(pw, delta / players_scale * pw))

        home_inj, away_inj = self._count_match_injuries(db, match_id, home_team_id, away_team_id)
        injury_adj = 0.0
        if iw > 0 and injury_scale > 0 and (home_inj or away_inj):
            # 主队伤停更多 → 下调主队进攻（负向）
            injury_adj = max(-iw, min(iw, (away_inj - home_inj) / injury_scale * iw))

        total_adj = standings_adj + scorers_adj + players_adj + injury_adj
        meta = {
            "applied": False,
            "standings_adj": round(standings_adj, 4),
            "scorers_adj": round(scorers_adj, 4),
            "players_adj": round(players_adj, 4),
            "injury_adj": round(injury_adj, 4),
            "home_injuries": home_inj,
            "away_injuries": away_inj,
            "home_ppg": round(float(home_row.points or 0) / max(int(home_row.played), 1), 3) if home_row and home_row.played else None,
            "away_ppg": round(float(away_row.points or 0) / max(int(away_row.played), 1), 3) if away_row and away_row.played else None,
            "home_scorer_share": round(home_share, 3),
            "away_scorer_share": round(away_share, 3),
            "home_squad_index": round(home_squad["index"], 4) if home_squad else None,
            "away_squad_index": round(away_squad["index"], 4) if away_squad else None,
            "home_squad_players": home_squad["players"] if home_squad else 0,
            "away_squad_players": away_squad["players"] if away_squad else 0,
        }
        if abs(total_adj) < 1e-6:
            return meta

        # 主队进攻↑ / 客队进攻↓（或反向）；防守反向微调一半
        home_params["attack"] = float(home_params["attack"]) * (1.0 + total_adj)
        away_params["attack"] = float(away_params["attack"]) * (1.0 - total_adj)
        home_params["defense"] = float(home_params["defense"]) * (1.0 - total_adj * 0.5)
        away_params["defense"] = float(away_params["defense"]) * (1.0 + total_adj * 0.5)
        meta["applied"] = True
        meta["total_adj"] = round(total_adj, 4)
        return meta

    @staticmethod
    def _count_match_injuries(db, match_id, home_team_id, away_team_id):
        """从伤停 RiskAlert 描述中解析主客队伤停人数。"""
        home_n = away_n = 0
        if not match_id:
            return home_n, away_n
        try:
            from db.models import RiskAlert
            alert = (
                db.query(RiskAlert)
                .filter(
                    RiskAlert.match_id == str(match_id),
                    RiskAlert.type == "injury",
                    RiskAlert.is_processed == False,  # noqa: E712
                )
                .order_by(RiskAlert.created_at.desc())
                .first()
            )
            if not alert or not alert.description:
                return home_n, away_n
            text = alert.description
            # 形如：伤停提示：主队 A(Out)、B(Out)；客队 无
            if "主队" in text and "客队" in text:
                home_part = text.split("主队", 1)[1].split("客队", 1)[0]
                away_part = text.split("客队", 1)[1]
            else:
                home_part = away_part = text
            def _count(part: str) -> int:
                part = (part or "").strip().rstrip("；;。 ")
                if not part or part in ("无", "无；", "无。"):
                    return 0
                return len([p for p in part.replace("；", "、").split("、") if p.strip() and p.strip() != "无"])
            home_n = _count(home_part)
            away_n = _count(away_part)
        except Exception:
            return 0, 0
        return home_n, away_n

    def _apply_environment(self, lambda_home, lambda_away, *, weather=None,
                           temperature=None, pitch_condition=None):
        """按天气/草坪修正泊松 λ。"""
        from services.environment_service import EnvironmentService
        factors = EnvironmentService.compute_factors(
            weather=weather,
            pitch_condition=pitch_condition,
            temperature=temperature,
            config=self.config.get("environment"),
        )
        factor = float(factors.get("lambda_factor") or 1.0)
        return {
            **factors,
            "lambda_home": float(lambda_home) * factor,
            "lambda_away": float(lambda_away) * factor,
        }

    def _params_from_orm(self, team, team_id):
        fallback = self._get_team_params(team_id)
        if not team:
            return fallback
        xg_for = getattr(team, "xg_for", None)
        xg_against = getattr(team, "xg_against", None)
        return {
            "attack": float(team.attack_strength or fallback["attack"]),
            "defense": float(team.defense_strength or fallback["defense"]),
            "xg_for": float(xg_for if xg_for is not None else fallback.get("xg_for") or 1.35),
            "xg_against": float(xg_against if xg_against is not None else fallback.get("xg_against") or 1.35),
            # DB 未存样本场次：有持久化 xG 时视为有效样本，避免 coverage=0
            "xg_matches": int(fallback.get("xg_matches") or (
                max(self.xg.min_matches, 8) if xg_for is not None else 0
            )),
            "league": team.league_id or fallback.get("league", "EPL"),
            "name": team.name or team.short_name or fallback.get("name") or team_id,
        }

    def _hydrate_xg_from_params(self, team_id, params: dict, league_id=None):
        """把球队参数同步到 xG 子模型（训练内存 / DB 回读共用）。"""
        if not team_id or not params:
            return
        matches_n = int(params.get("xg_matches") or params.get("matches") or 0)
        if matches_n <= 0 and "xg_for" not in params:
            return
        if matches_n <= 0:
            matches_n = self.xg.min_matches
        self.xg.set_team(team_id, {
            "xg_for": params.get("xg_for", 1.35),
            "xg_against": params.get("xg_against", 1.35),
            "shots_pg": params.get("shots_pg", 12.0),
            "sot_pg": params.get("sot_pg", 4.0),
            "matches": matches_n,
            "league": league_id or params.get("league"),
        })
        lid = league_id or params.get("league")
        if lid and lid not in self.xg.league_priors:
            avg_goals = float(self.league_avg.get(lid, 2.70) or 2.70)
            self.xg.set_league_prior(lid, {
                "xg_for_avg": max(0.6, avg_goals / 2.0),
                "xg_per_shot": self.xg.prior_xg_per_shot,
                "xg_per_sot": self.xg.prior_xg_per_sot,
            })

    def _get_team_params(self, team_id):
        return self.team_params.get(team_id, {
            "attack": 1.0, "defense": 1.0, "league": "EPL", "name": team_id
        })

    def _calc_confidence(self, max_prob):
        if max_prob > 0.50:
            return "high"
        elif max_prob > 0.38:
            return "mid"
        return "low"

    def _calc_risk(self, max_prob, home, away):
        diff = abs(float(home["attack"]) - float(away["attack"]))
        if max_prob < 0.38 or diff < 0.15:
            return "high"
        elif max_prob < 0.45:
            return "mid"
        return "low"

    def _build_tendency(self, home_win, away_win, draw):
        """基于融合后的概率生成倾向，避免与结论矛盾。"""
        ranked = sorted(
            [("home", home_win), ("draw", draw), ("away", away_win)],
            key=lambda x: x[1],
            reverse=True,
        )
        top, second = ranked[0], ranked[1]
        margin = top[1] - second[1]
        if top[0] == "home":
            return "主队占优，主场加持明显" if margin > 0.12 else "主队微优，需防平局"
        if top[0] == "away":
            return "客队占优，客场实力较强" if margin > 0.12 else "客队微优，主队有主场抵抗"
        return "势均力敌，平局概率较高"

    def _extract_key_variables(self, home_team, away_team, home_name, away_name):
        variables_map = {
            "MCI": "哈兰德终结效率", "ARS": "阿森纳反击质量", "LIV": "萨拉赫状态",
            "CHE": "切尔西中场控制", "MUN": "曼联防守稳定性", "TOT": "孙兴慜速度发挥",
            "RMA": "姆巴佩终结效率", "BAR": "巴萨中场调度", "BAY": "凯恩进球效率",
            "DOR": "多特防线稳定性", "INT": "劳塔罗状态", "JUV": "尤文防守硬度",
            "PSG": "巴黎攻击群配合", "BRA": "维尼修斯突破能力", "ARG": "梅西组织调度",
            "FRA": "姆巴佩速度冲击", "ENG": "凯恩终结效率", "ESP": "中场控制力",
            "GER": "穆西亚拉创造力", "NED": "防线硬度", "POR": "关键传球质量",
        }
        return [
            variables_map.get(home_team, f"{home_name}进攻效率"),
            variables_map.get(away_team, f"{away_name}反击质量"),
            "中场控制力对比",
        ]

    def _build_analysis(self, h_name, a_name, h_win, a_win, lh, la, tendency):
        lh_s, la_s = round(lh, 2), round(la, 2)
        if h_win > a_win:
            return f"{h_name}主场作战，预期进球{lh_s}个，整体占优。{a_name}客场预期进球{la_s}个，面临一定压力。{tendency}。"
        if a_win > h_win:
            return f"{a_name}客场实力出色，预期进球{la_s}个。{h_name}虽主场作战但预期进球仅{lh_s}个，需加强进攻。{tendency}。"
        return f"双方实力接近，{h_name}预期进球{lh_s}个，{a_name}预期进球{la_s}个。比赛结果存在较大不确定性，{tendency}。"

    def _calc_total_goals(self, avg):
        low = max(0, int(avg - 1))
        high = int(avg + 1) + 1
        return f"{low}-{high}球"
