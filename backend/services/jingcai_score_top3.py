"""竞彩比分 Top3：历史相似盘口比分分布（看盘对照层）。

样本库：已完赛、有让球盘口与 SP、有赛果的竞彩场次（赔率优先取开赛前最后一帧快照）。
目标场次：同盘口内按（胜平负、让球）隐含概率做核加权 kNN，统计相似场次的实际比分；
以市场 SP 反推的泊松比分分布做先验平滑，可按 bf_prior_weight 混入赛前比分 SP（默认 0，不改变结果）；再按胜平负 / 让球方向约束，取概率最高的若干比分
（个数由 recommend_count 决定，默认 3，可在竞彩足球配置页覆盖）。

不参与融合训练，不替换主预测结论；文案仅供竞技分析对照，不构成投注建议。
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from services.odds_analysis import _f, _odds_fields, implied_probs_from_sp

logger = logging.getLogger(__name__)

DISCLAIMER = "历史相似盘口比分分布仅供分析对照，不构成投注建议"

# 与竞彩比分玩法（JingcaiBf.vue）31 个键一致
HOME_KEYS = ("1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "5:0", "5:1", "5:2")
DRAW_KEYS = ("0:0", "1:1", "2:2", "3:3")
AWAY_KEYS = ("0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4", "0:5", "1:5", "2:5")
ALL_KEYS = HOME_KEYS + ("胜其它",) + DRAW_KEYS + ("平其它",) + AWAY_KEYS + ("负其它",)
_KEY_INDEX = {k: i for i, k in enumerate(ALL_KEYS)}

OUTCOMES = ("H", "D", "A")
DIRECTION_AUTO = "auto"
DIRECTION_ANY = "any"
DIRECTION_MODEL = "model"
DIRECTION_CHOICES = (DIRECTION_AUTO, DIRECTION_ANY, DIRECTION_MODEL) + OUTCOMES

# 进球网格 0..GRID-1；单队进球 ≥ GRID-1 归入最后一格（只影响「其它」类）
GRID = 10
_CELL_HOME = np.repeat(np.arange(GRID), GRID)
_CELL_AWAY = np.tile(np.arange(GRID), GRID)
_CELL_DIFF = _CELL_HOME - _CELL_AWAY

# 样本需在目标场次开赛前已完赛：开赛时间至少早于目标这么多秒
_FINISH_GAP_SECONDS = 3 * 3600

FALLBACK_LABELS = {
    0: "同盘口 · 胜平负与让球赔率相似",
    1: "同盘口 · 单一玩法赔率相似",
    2: "同盘口全部样本",
    3: "市场泊松先验（样本不足）",
}

RECOMMEND_COUNT_MIN = 1
RECOMMEND_COUNT_MAX = 10
DEFAULT_RECOMMEND_COUNT = 3
SETTING_KEY = "jingcai.recommend_score_count"

DEFAULTS: Dict[str, Any] = {
    "recommend_count": DEFAULT_RECOMMEND_COUNT,
    "lookback_days": 540,
    "k": 80,
    "bandwidth": 0.15,
    "smoothing_alpha": 80.0,
    "same_league_boost": 1.3,
    "recency_half_life_days": 180,
    "min_effective_samples": 25,
    "no_snapshot_weight": 1.0,
    "bf_prior_weight": 0.0,     # 赛前比分 SP 在先验中的权重；0 表示仍用纯泊松
    "model_prior_weight": 0.0,  # 赛前预测 λ 的泊松网格在先验中的权重；0 表示不用
    "cache_ttl_seconds": 600,
    "max_batch": 50,
}


def get_config(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """config.yaml → jingcai_score_top3，缺省项回退 DEFAULTS。"""
    cfg = dict(DEFAULTS)
    try:
        from db.database import config as app_config

        cfg.update((app_config or {}).get("jingcai_score_top3") or {})
    except Exception:
        pass
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    cfg["recommend_count"] = recommend_count_of(cfg)
    cfg["bf_prior_weight"] = _bf_weight(cfg.get("bf_prior_weight"))
    cfg["model_prior_weight"] = _bf_weight(cfg.get("model_prior_weight"))
    return cfg


def recommend_count_of(cfg: Optional[Dict[str, Any]] = None) -> int:
    """把配置里的推荐个数收成 1..RECOMMEND_COUNT_MAX 的整数，异常回退默认值。"""
    raw = DEFAULT_RECOMMEND_COUNT if not cfg else cfg.get("recommend_count", DEFAULT_RECOMMEND_COUNT)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_RECOMMEND_COUNT
    return max(RECOMMEND_COUNT_MIN, min(RECOMMEND_COUNT_MAX, n))


def parse_recommend_count(value: Any) -> int:
    """页面保存用：越界或非整数直接拒绝。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError("推荐比分数量必须是整数") from None
    if n < RECOMMEND_COUNT_MIN or n > RECOMMEND_COUNT_MAX:
        raise ValueError(f"推荐比分数量需在 {RECOMMEND_COUNT_MIN} 到 {RECOMMEND_COUNT_MAX} 之间")
    return n


def _stored_recommend_count(db) -> Optional[int]:
    if db is None:
        return None
    try:
        from db.models import AppSetting

        row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    except Exception:
        logger.debug("read jingcai recommend count skipped", exc_info=True)
        return None
    if row is None or row.value in (None, ""):
        return None
    return recommend_count_of({"recommend_count": row.value})


def resolve_recommend_count(
    db,
    cfg: Optional[Dict[str, Any]] = None,
    *,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """yaml/默认值之上，用数据库里的推荐个数覆盖（显式 overrides 优先）。"""
    out = dict(cfg or get_config())
    if not overrides or "recommend_count" not in overrides:
        stored = _stored_recommend_count(db)
        if stored is not None:
            out["recommend_count"] = stored
    out["recommend_count"] = recommend_count_of(out)
    return out


def load_recommend_count(db) -> int:
    return int(resolve_recommend_count(db)["recommend_count"])


def save_recommend_count(db, value: Any) -> int:
    from db.models import AppSetting

    n = parse_recommend_count(value)
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if row is None:
        db.add(AppSetting(key=SETTING_KEY, value=str(n)))
    else:
        row.value = str(n)
    db.commit()
    return n


# ===== 比分归档 / 方向约束 =====

def score_key(home_goals: int, away_goals: int) -> str:
    """实际比分 → 竞彩比分键（超出列表的归入胜/平/负其它）。"""
    key = f"{int(home_goals)}:{int(away_goals)}"
    if key in _KEY_INDEX:
        return key
    if home_goals > away_goals:
        return "胜其它"
    if home_goals == away_goals:
        return "平其它"
    return "负其它"


def _cell(home_goals: int, away_goals: int) -> int:
    return min(int(home_goals), GRID - 1) * GRID + min(int(away_goals), GRID - 1)


_CELL_KEY = np.array([_KEY_INDEX[score_key(h, a)] for h, a in zip(_CELL_HOME, _CELL_AWAY)])
# 每个竞彩键对应的格子。「其它」均分到这些格子上，只为方向掩码能按格子截断；汇总回键时质量不变
_KEY_CELLS = [np.flatnonzero(_CELL_KEY == i) for i in range(len(ALL_KEYS))]


def outcome_of(diff: int) -> str:
    return "H" if diff > 0 else ("D" if diff == 0 else "A")


def _sign_mask(values: np.ndarray, outcome: str) -> np.ndarray:
    if outcome == "H":
        return values > 0
    if outcome == "D":
        return values == 0
    return values < 0


def direction_mask(handicap: int, nspf: Optional[str] = None, spf: Optional[str] = None) -> np.ndarray:
    """比分网格上满足方向约束的格子。

    胜平负看 d = 主 − 客；让球看 d + handicap（handicap=-1 表示主队让 1 球）。
    """
    mask = np.ones(GRID * GRID, dtype=bool)
    if nspf:
        mask &= _sign_mask(_CELL_DIFF, nspf)
    if spf:
        mask &= _sign_mask(_CELL_DIFF + int(handicap), spf)
    return mask


def satisfies(home_goals: int, away_goals: int, handicap: int,
              nspf: Optional[str] = None, spf: Optional[str] = None) -> bool:
    d = int(home_goals) - int(away_goals)
    if nspf and outcome_of(d) != nspf:
        return False
    if spf and outcome_of(d + int(handicap)) != spf:
        return False
    return True


# ===== 市场泊松先验 =====

_LAMBDAS = np.round(np.arange(0.2, 3.55, 0.05), 2)
_DEFAULT_LAMBDAS = (1.35, 1.10)


def _poisson_pmf(lam: float) -> np.ndarray:
    k = np.arange(GRID)
    fact = np.array([math.factorial(int(i)) for i in k], dtype=float)
    pmf = np.exp(-lam) * np.power(lam, k) / fact
    pmf[-1] += max(0.0, 1.0 - pmf.sum())
    return pmf


@lru_cache(maxsize=1)
def _pmf_table() -> np.ndarray:
    return np.stack([_poisson_pmf(float(lam)) for lam in _LAMBDAS])


@lru_cache(maxsize=16)
def _outcome_tables(offset: int) -> np.ndarray:
    """(3, nλ, nλ)：主 λ_i、客 λ_j 下 P(d+offset>0 / =0 / <0)。"""
    table = _pmf_table()
    diff = np.subtract.outer(np.arange(GRID), np.arange(GRID)) + int(offset)
    return np.stack([table @ m.astype(float) @ table.T for m in (diff > 0, diff == 0, diff < 0)])


@lru_cache(maxsize=4096)
def fit_market_lambdas(
    nspf: Optional[Tuple[float, float, float]],
    spf: Optional[Tuple[float, float, float]],
    handicap: Optional[int],
) -> Tuple[float, float]:
    """网格反解 (λ主, λ客)，使泊松胜平负 / 让球概率最贴近市场隐含概率。"""
    n = len(_LAMBDAS)
    err = np.zeros((n, n))
    used = False
    if nspf is not None:
        tabs = _outcome_tables(0)
        err += sum((tabs[i] - nspf[i]) ** 2 for i in range(3))
        used = True
    if spf is not None and handicap is not None:
        tabs = _outcome_tables(int(handicap))
        err += sum((tabs[i] - spf[i]) ** 2 for i in range(3))
        used = True
    if not used:
        return _DEFAULT_LAMBDAS
    i, j = np.unravel_index(int(np.argmin(err)), err.shape)
    return float(_LAMBDAS[i]), float(_LAMBDAS[j])


def poisson_grid(lam_home: float, lam_away: float) -> np.ndarray:
    grid = np.outer(_poisson_pmf(lam_home), _poisson_pmf(lam_away)).ravel()
    return grid / grid.sum()


# ===== 特征 =====

@dataclass
class Features:
    handicap: int
    nspf: Optional[np.ndarray]  # (3,) 胜平负隐含概率
    spf: Optional[np.ndarray]   # (3,) 让球隐含概率

    def prior_key(self) -> Tuple:
        def r(p):
            return None if p is None else tuple(round(float(x), 3) for x in p)
        return r(self.nspf), r(self.spf), self.handicap


def _probs(win: Any, draw: Any, lose: Any) -> Optional[np.ndarray]:
    p = implied_probs_from_sp(win, draw, lose)
    if not p:
        return None
    return np.array([p["home"], p["draw"], p["away"]], dtype=float)


def _handicap(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def features_from_odds(src: Any) -> Optional[Features]:
    """赛事行或 dict → 特征；需有让球盘口且至少一组完整 SP。"""
    fields = _odds_fields(src)
    hc = _handicap(fields["handicap"])
    if hc is None:
        return None
    nspf = _probs(fields["odds_nspf_win"], fields["odds_nspf_draw"], fields["odds_nspf_lose"])
    spf = _probs(fields["odds_spf_win"], fields["odds_spf_draw"], fields["odds_spf_lose"])
    if nspf is None and spf is None:
        return None
    return Features(handicap=hc, nspf=nspf, spf=spf)


def market_prior(feat: Features) -> Tuple[np.ndarray, Tuple[float, float]]:
    nspf, spf, hc = feat.prior_key()
    lams = fit_market_lambdas(nspf, spf, hc)
    return poisson_grid(*lams), lams


def _bf_weight(value: Any) -> float:
    try:
        weight = float(value)
    except (TypeError, ValueError):
        return 0.0
    if weight < 0:
        return 0.0
    if weight > 1:
        return 1.0
    return weight


def _complete_bf_sp(odds_bf: Any) -> Optional[Dict[str, float]]:
    """31 个竞彩比分键都是正数才采用。缺格、非正数退回纯泊松。"""
    if isinstance(odds_bf, str):
        try:
            odds_bf = json.loads(odds_bf)
        except (TypeError, ValueError):
            return None
    if not isinstance(odds_bf, dict):
        return None
    parsed: Dict[str, float] = {}
    for key in ALL_KEYS:
        raw = odds_bf.get(key)
        if raw is None or raw == "":
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        parsed[key] = value
    return parsed


def bf_implied_grid(odds_bf: Any) -> Optional[np.ndarray]:
    """比分 SP 去水后铺到 10×10 网格。概率记在 31 个竞彩键上，不把「其它」拆成独立比分。"""
    sp = _complete_bf_sp(odds_bf)
    if sp is None:
        return None
    inv = np.array([1.0 / sp[key] for key in ALL_KEYS], dtype=float)
    total = float(inv.sum())
    if total <= 0:
        return None
    probs = inv / total
    grid = np.zeros(GRID * GRID, dtype=float)
    for index, cells in enumerate(_KEY_CELLS):
        if cells.size == 0:
            return None
        grid[cells] = probs[index] / float(cells.size)
    mass = float(grid.sum())
    if mass <= 0:
        return None
    return grid / mass


def model_lambda_grid(lams: Any) -> Optional[np.ndarray]:
    """赛前预测的 (λ主, λ客) → 10×10 泊松网格。不用落库的 5×5 score_matrix。"""
    if not lams or len(lams) < 2:
        return None
    try:
        lam_home, lam_away = float(lams[0]), float(lams[1])
    except (TypeError, ValueError):
        return None
    if not (0 < lam_home <= 20 and 0 < lam_away <= 20):
        return None
    grid = poisson_grid(lam_home, lam_away)
    if grid.size != GRID * GRID or not np.isfinite(grid).all() or float(grid.sum()) <= 0:
        return None
    return grid


def _blend_market_prior(
    poisson: np.ndarray,
    odds_bf: Any,
    bf_weight: Any,
    model_lams: Any = None,
    model_weight: Any = 0,
) -> Tuple[np.ndarray, bool, bool]:
    """P = (1-w_bf-w_model)·泊松 + w_bf·比分 SP + w_model·模型 λ。

    缺比分 SP 或没有赛前 λ 时，该路权重为 0，质量回到泊松。
    两路之和超过 1 时按比例压到 1，泊松权重为 0。
    """
    w_bf = _bf_weight(bf_weight)
    w_model = _bf_weight(model_weight)
    bf_grid = bf_implied_grid(odds_bf) if w_bf > 0 else None
    model_grid = model_lambda_grid(model_lams) if w_model > 0 else None
    if bf_grid is None:
        w_bf = 0.0
    if model_grid is None:
        w_model = 0.0
    if w_bf + w_model <= 0:
        return poisson, False, False
    if w_bf + w_model > 1:
        scale = 1.0 / (w_bf + w_model)
        w_bf *= scale
        w_model *= scale
    mixed = (1.0 - w_bf - w_model) * poisson
    if w_bf > 0:
        mixed = mixed + w_bf * bf_grid
    if w_model > 0:
        mixed = mixed + w_model * model_grid
    mass = float(mixed.sum())
    if mass <= 0:
        return poisson, False, False
    return mixed / mass, w_bf > 0, w_model > 0


# ===== 样本库 =====

@dataclass
class SamplePool:
    match_ids: np.ndarray       # object
    league: np.ndarray          # object
    kickoff: np.ndarray         # float，epoch 秒
    handicap: np.ndarray        # int
    nspf: np.ndarray            # (N,3)，缺失为 nan
    spf: np.ndarray             # (N,3)
    nspf_sp: np.ndarray         # (N,3) 原始 SP（回测复用看盘启发式）
    spf_sp: np.ndarray          # (N,3)
    home_goals: np.ndarray
    away_goals: np.ndarray
    cell: np.ndarray            # 比分网格下标
    snapshot: np.ndarray        # bool：赔率是否来自赛前快照
    built_at: float

    def __len__(self) -> int:
        return int(self.kickoff.size)


def _kickoff_dt(match_date: Optional[date], match_time: Any) -> datetime:
    if isinstance(match_time, timedelta):
        match_time = (datetime.min + match_time).time()
    if not isinstance(match_time, dt_time):
        match_time = dt_time(23, 59, 59)
    return datetime.combine(match_date or date.today(), match_time)


def _sp_triplet(win: Any, draw: Any, lose: Any) -> Optional[Tuple[float, float, float]]:
    vals = (_f(win), _f(draw), _f(lose))
    return None if any(v is None for v in vals) else vals


def _closing_snapshots(db, kickoffs: Dict[str, datetime]) -> Dict[str, Any]:
    """每场取开赛前最后一帧让球 SP 完整的快照。"""
    from db.models import OddsSnapshot

    out: Dict[str, Any] = {}
    ids = list(kickoffs)
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        rows = (
            db.query(
                OddsSnapshot.match_id, OddsSnapshot.captured_at, OddsSnapshot.handicap,
                OddsSnapshot.odds_nspf_win, OddsSnapshot.odds_nspf_draw, OddsSnapshot.odds_nspf_lose,
                OddsSnapshot.odds_spf_win, OddsSnapshot.odds_spf_draw, OddsSnapshot.odds_spf_lose,
            )
            .filter(OddsSnapshot.match_id.in_(chunk), OddsSnapshot.captured_at.isnot(None))
            .order_by(OddsSnapshot.captured_at.asc())
            .all()
        )
        for r in rows:
            if r.captured_at > kickoffs[r.match_id]:
                continue
            if _sp_triplet(r.odds_spf_win, r.odds_spf_draw, r.odds_spf_lose) is None:
                continue
            out[r.match_id] = r
    return out


def load_sample_pool(db, lookback_days: int, no_snapshot_weight: float = 1.0) -> SamplePool:
    """已完赛竞彩样本：status=finished 且 result 非空（home_goals 默认 0，不能单凭比分判断）。"""
    from db.models import Match

    since = date.today() - timedelta(days=max(1, int(lookback_days)))
    rows = (
        db.query(
            Match.id, Match.league_id, Match.match_date, Match.match_time, Match.handicap,
            Match.odds_nspf_win, Match.odds_nspf_draw, Match.odds_nspf_lose,
            Match.odds_spf_win, Match.odds_spf_draw, Match.odds_spf_lose,
            Match.home_goals, Match.away_goals,
        )
        .filter(
            Match.status == "finished",
            Match.result.isnot(None),
            Match.handicap.isnot(None),
            Match.odds_spf_win.isnot(None),
            Match.odds_spf_draw.isnot(None),
            Match.odds_spf_lose.isnot(None),
            Match.home_goals.isnot(None),
            Match.away_goals.isnot(None),
            Match.match_date >= since,
        )
        .all()
    )
    kickoffs = {r.id: _kickoff_dt(r.match_date, r.match_time) for r in rows}
    snaps = _closing_snapshots(db, kickoffs) if rows else {}

    nan3 = (np.nan, np.nan, np.nan)
    ids, leagues, ko, hcs, nspf_sp, spf_sp, hg, ag, snap_flags = [], [], [], [], [], [], [], [], []
    for r in rows:
        snap = snaps.get(r.id)
        hc = r.handicap
        spf = _sp_triplet(r.odds_spf_win, r.odds_spf_draw, r.odds_spf_lose)
        nspf = _sp_triplet(r.odds_nspf_win, r.odds_nspf_draw, r.odds_nspf_lose)
        if snap is not None:
            if snap.handicap is not None:
                hc = snap.handicap
            spf = _sp_triplet(snap.odds_spf_win, snap.odds_spf_draw, snap.odds_spf_lose)
            nspf = _sp_triplet(snap.odds_nspf_win, snap.odds_nspf_draw, snap.odds_nspf_lose) or nspf
        if spf is None or hc is None:
            continue
        ids.append(r.id)
        leagues.append(r.league_id)
        ko.append(kickoffs[r.id].timestamp())
        hcs.append(int(hc))
        nspf_sp.append(nspf or nan3)
        spf_sp.append(spf)
        hg.append(int(r.home_goals))
        ag.append(int(r.away_goals))
        snap_flags.append(snap is not None)

    def to_probs(sp: np.ndarray) -> np.ndarray:
        if sp.size == 0:
            return sp.reshape(0, 3)
        raw = 1.0 / sp
        return raw / raw.sum(axis=1, keepdims=True)

    nspf_arr = np.array(nspf_sp, dtype=float).reshape(-1, 3)
    spf_arr = np.array(spf_sp, dtype=float).reshape(-1, 3)
    hg_arr = np.array(hg, dtype=int)
    ag_arr = np.array(ag, dtype=int)
    return SamplePool(
        match_ids=np.array(ids, dtype=object),
        league=np.array(leagues, dtype=object),
        kickoff=np.array(ko, dtype=float),
        handicap=np.array(hcs, dtype=int),
        nspf=to_probs(nspf_arr),
        spf=to_probs(spf_arr),
        nspf_sp=nspf_arr,
        spf_sp=spf_arr,
        home_goals=hg_arr,
        away_goals=ag_arr,
        cell=np.minimum(hg_arr, GRID - 1) * GRID + np.minimum(ag_arr, GRID - 1),
        snapshot=np.array(snap_flags, dtype=bool),
        built_at=time.time(),
    )


_POOL_CACHE: Dict[int, SamplePool] = {}
_POOL_LOCK = threading.Lock()


def get_sample_pool(db, cfg: Optional[Dict[str, Any]] = None) -> SamplePool:
    """进程内缓存样本库（TTL 见 cache_ttl_seconds）；赛果回写后由采集侧主动失效。"""
    cfg = cfg or get_config()
    key = int(cfg["lookback_days"])
    ttl = float(cfg["cache_ttl_seconds"])
    with _POOL_LOCK:
        pool = _POOL_CACHE.get(key)
        if pool is not None and time.time() - pool.built_at < ttl:
            return pool
    pool = load_sample_pool(db, key)
    with _POOL_LOCK:
        _POOL_CACHE[key] = pool
    return pool


def invalidate_pool_cache() -> None:
    with _POOL_LOCK:
        _POOL_CACHE.clear()


# ===== 推荐核心 =====

def _neighbours(
    feat: Features,
    pool: SamplePool,
    eligible: np.ndarray,
    level: int,
    cfg: Dict[str, Any],
    league_id: Optional[str],
    ref_ts: float,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """返回 (样本下标, 最终权重, 核权重)；该级别不适用时返回 None。"""
    mask = eligible & (pool.handicap == feat.handicap)
    if level == 0:
        if feat.nspf is None or feat.spf is None:
            return None
        mask &= ~np.isnan(pool.nspf[:, 0])
        X = np.hstack([pool.nspf, pool.spf])
        x = np.concatenate([feat.nspf, feat.spf])
    elif level == 1:
        if feat.spf is not None:
            X, x = pool.spf, feat.spf
        else:
            mask &= ~np.isnan(pool.nspf[:, 0])
            X, x = pool.nspf, feat.nspf
    else:
        X = x = None

    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return idx, np.zeros(0), np.zeros(0)
    if X is not None:
        dist = np.linalg.norm(X[idx] - x, axis=1)
        order = np.argsort(dist, kind="stable")[: int(cfg["k"])]
        idx, dist = idx[order], dist[order]
        bw = float(cfg["bandwidth"])
        kernel = np.exp(-(dist ** 2) / (2.0 * bw * bw))
    else:
        kernel = np.ones(idx.size)

    w = kernel.copy()
    if league_id:
        w *= np.where(pool.league[idx] == league_id, float(cfg["same_league_boost"]), 1.0)
    half_life = float(cfg["recency_half_life_days"])
    if half_life > 0:
        age_days = np.maximum(0.0, (ref_ts - pool.kickoff[idx]) / 86400.0)
        w *= np.power(0.5, age_days / half_life)
    no_snap = float(cfg["no_snapshot_weight"])
    if no_snap != 1.0:
        w *= np.where(pool.snapshot[idx], 1.0, no_snap)
    return idx, w, kernel


def _apply_direction(
    p_grid: np.ndarray,
    handicap: int,
    nspf: Optional[str],
    spf: Optional[str],
    locked: Tuple[str, ...] = (),
) -> Tuple[Optional[np.ndarray], Optional[str], Optional[str], List[str]]:
    """按方向约束截断并重新归一化。组合不可能时逐步放宽，但 locked 中的玩法（用户指定）不放宽。"""
    attempts = [(nspf, spf), (nspf, None), (None, spf), (None, None)]
    relaxed: List[str] = []
    seen = set()
    for n, s in attempts:
        if (n, s) in seen:
            continue
        if ("nspf" in locked and n != nspf) or ("spf" in locked and s != spf):
            continue
        seen.add((n, s))
        mask = direction_mask(handicap, n, s)
        mass = float(p_grid[mask].sum())
        if mass > 1e-12:
            if nspf and not n:
                relaxed.append("nspf")
            if spf and not s:
                relaxed.append("spf")
            return np.where(mask, p_grid, 0.0) / mass, n, s, relaxed
    return None, None, None, relaxed


def _outcome_dist(p_grid: np.ndarray, offset: int) -> Dict[str, float]:
    diff = _CELL_DIFF + int(offset)
    return {
        "home": round(float(p_grid[diff > 0].sum()), 4),
        "draw": round(float(p_grid[diff == 0].sum()), 4),
        "away": round(float(p_grid[diff < 0].sum()), 4),
    }


def _recommend_core(
    feat: Features,
    pool: SamplePool,
    eligible: np.ndarray,
    cfg: Dict[str, Any],
    *,
    league_id: Optional[str] = None,
    ref_ts: Optional[float] = None,
    nspf: Optional[str] = None,
    spf: Optional[str] = None,
    locked: Tuple[str, ...] = (),
    force_level: Optional[int] = None,
    bf_odds: Any = None,
    bf_weight: Optional[float] = None,
    model_lams: Any = None,
    model_weight: Optional[float] = None,
) -> Dict[str, Any]:
    ref_ts = time.time() if ref_ts is None else ref_ts
    poisson, lams = market_prior(feat)
    bf_w = _bf_weight(cfg.get("bf_prior_weight")) if bf_weight is None else _bf_weight(bf_weight)
    model_w = _bf_weight(cfg.get("model_prior_weight")) if model_weight is None else _bf_weight(model_weight)
    prior, bf_used, model_used = _blend_market_prior(poisson, bf_odds, bf_w, model_lams, model_w)
    alpha = float(cfg["smoothing_alpha"])
    min_eff = float(cfg["min_effective_samples"])

    level, idx, w, kernel = 3, np.zeros(0, dtype=int), np.zeros(0), np.zeros(0)
    levels = (force_level,) if force_level is not None else (0, 1, 2)
    if force_level != 3:
        for lv in levels:
            got = _neighbours(feat, pool, eligible, lv, cfg, league_id, ref_ts)
            if got is None:
                continue
            if force_level is not None or float(got[2].sum()) >= min_eff:
                level, (idx, w, kernel) = lv, got
                break

    if level < 3 and idx.size:
        counts = np.bincount(pool.cell[idx], weights=w, minlength=GRID * GRID)
        p_hist = (counts + alpha * prior) / (float(w.sum()) + alpha)
    else:
        level, idx, w, kernel = 3, np.zeros(0, dtype=int), np.zeros(0), np.zeros(0)
        p_hist = prior

    p_cond, used_nspf, used_spf, relaxed = _apply_direction(p_hist, feat.handicap, nspf, spf, locked)
    out: Dict[str, Any] = {
        "fallback_level": level,
        "fallback_label": FALLBACK_LABELS[level],
        "lambdas": {"home": lams[0], "away": lams[1]},
        "outcome_dist": _outcome_dist(p_hist, 0),
        "handicap_dist": _outcome_dist(p_hist, feat.handicap),
        "samples": {
            "used": int(idx.size),
            "effective": round(float(kernel.sum()), 2),
            "same_handicap": int((eligible & (pool.handicap == feat.handicap)).sum()),
            "pool": int(eligible.sum()),
        },
        "constraint": {
            "handicap": feat.handicap,
            "nspf": used_nspf,
            "spf": used_spf,
            "relaxed": relaxed,
        },
        "bf_prior_used": bf_used,
        "bf_prior_weight": bf_w if bf_used else 0.0,
        "model_prior_used": model_used,
        "model_prior_weight": model_w if model_used else 0.0,
    }
    if p_cond is None:
        out["top3"] = []
        out["available"] = False
        out["reason"] = "所选胜平负与让球方向组合在该盘口下不可能同时成立"
        return out

    p_keys = np.bincount(_CELL_KEY, weights=p_cond, minlength=len(ALL_KEYS))
    p_raw_keys = np.bincount(_CELL_KEY, weights=p_hist, minlength=len(ALL_KEYS))
    sample_keys = _CELL_KEY[pool.cell[idx]] if idx.size else np.zeros(0, dtype=int)
    order = np.argsort(-p_keys, kind="stable")[:recommend_count_of(cfg)]
    out["top3"] = [
        {
            "score": ALL_KEYS[i],
            "prob": round(float(p_keys[i]), 4),
            "prob_unconditional": round(float(p_raw_keys[i]), 4),
            "sample_hits": int((sample_keys == i).sum()),
        }
        for i in order
        if p_keys[i] > 0
    ]
    out["available"] = True
    return out


def _heuristic_directions(src: Any) -> Tuple[Optional[str], Optional[str]]:
    from services.odds_heuristics import analyze_odds_heuristics

    lean_map = {"home": "H", "draw": "D", "away": "A"}
    try:
        h = analyze_odds_heuristics(src) or {}
    except Exception:
        return None, None
    return (
        lean_map.get((h.get("nspf") or {}).get("lean")),
        lean_map.get((h.get("spf") or {}).get("lean")),
    )


PredictionInput = Tuple[Tuple[float, float, float], Optional[Tuple[float, float]]]


def model_directions(
    prediction: Optional[PredictionInput],
    handicap: int,
) -> Tuple[Optional[str], Optional[str]]:
    """模型倾向：胜平负取融合概率最大的一侧；让球取该侧内 λ 泊松网格质量最大的让球结果。

    让球方向在胜平负方向内部选取，两者必然兼容。
    """
    if not prediction:
        return None, None
    probs, lams = prediction
    nspf = OUTCOMES[int(np.argmax(probs))]
    if not lams:
        return nspf, None
    grid = poisson_grid(*lams)
    inside = direction_mask(handicap, nspf)
    masses = [float(grid[inside & _sign_mask(_CELL_DIFF + int(handicap), o)].sum()) for o in OUTCOMES]
    return nspf, OUTCOMES[int(np.argmax(masses))]


def _prediction_input(row: Any) -> Optional[PredictionInput]:
    probs = tuple(_f(getattr(row, k, None)) for k in ("home_win_prob", "draw_prob", "away_win_prob"))
    if any(p is None for p in probs):
        return None
    lh, la = _f(getattr(row, "lambda_home", None)), _f(getattr(row, "lambda_away", None))
    return probs, ((lh, la) if lh is not None and la is not None else None)


def load_pre_match_predictions(db, kickoffs: Dict[str, datetime]) -> Dict[str, PredictionInput]:
    """每场取开赛前最后一条预测（未开赛场次即最新一条）。"""
    from db.models import MatchPrediction

    out: Dict[str, PredictionInput] = {}
    ids = list(kickoffs)
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        rows = (
            db.query(
                MatchPrediction.match_id, MatchPrediction.created_at,
                MatchPrediction.home_win_prob, MatchPrediction.draw_prob, MatchPrediction.away_win_prob,
                MatchPrediction.lambda_home, MatchPrediction.lambda_away,
            )
            .filter(MatchPrediction.match_id.in_(chunk), MatchPrediction.created_at.isnot(None))
            .order_by(MatchPrediction.created_at.asc(), MatchPrediction.id.asc())
            .all()
        )
        for r in rows:
            if r.created_at > kickoffs[r.match_id]:
                continue
            pred = _prediction_input(r)
            if pred is not None:
                out[r.match_id] = pred
    return out


def _resolve_direction(
    choice: Optional[str],
    heuristic: Optional[str],
    model: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    choice = (choice or DIRECTION_ANY).strip()
    if choice in OUTCOMES:
        return choice, "user"
    if choice == DIRECTION_AUTO and heuristic:
        return heuristic, "heuristic"
    if choice == DIRECTION_MODEL and model:
        return model, "model"
    return None, "none"


def recommend_top3(
    match: Any,
    pool: SamplePool,
    cfg: Optional[Dict[str, Any]] = None,
    *,
    nspf: str = DIRECTION_ANY,
    spf: str = DIRECTION_ANY,
    now: Optional[datetime] = None,
    prediction: Optional[PredictionInput] = None,
    bf_odds: Any = None,
) -> Dict[str, Any]:
    """单场比分 Top3。nspf / spf：any=不约束，H/D/A=指定方向，auto=看盘启发式倾向，
    model=赛前模型预测倾向（需传入 prediction，缺失时不约束并标记 model_available=false）。

    只使用目标开赛前已完赛的样本，已完赛场次可按赛前视角复盘。
    bf_odds 只接受开赛前最后一帧比分 SP；缺帧或不完整时先验仍是泊松。
    """
    cfg = cfg or get_config()
    match_id = getattr(match, "id", None) if not isinstance(match, dict) else match.get("id")
    feat = features_from_odds(match)
    if feat is None:
        return {"match_id": match_id, "available": False, "reason": "缺少让球盘口或完整 SP", "top3": []}

    g = match.get if isinstance(match, dict) else (lambda k, d=None: getattr(match, k, d))
    now_ts = (now or datetime.now()).timestamp()
    kickoff_ts = _kickoff_dt(g("match_date"), g("match_time")).timestamp()
    ref_ts = min(now_ts, kickoff_ts)
    eligible = (pool.kickoff + _FINISH_GAP_SECONDS <= kickoff_ts) & (pool.match_ids != match_id)

    h_nspf, h_spf = _heuristic_directions(match)
    m_nspf, m_spf = model_directions(prediction, feat.handicap)
    use_nspf, nspf_src = _resolve_direction(nspf, h_nspf if feat.nspf is not None else None, m_nspf)
    use_spf, spf_src = _resolve_direction(spf, h_spf if feat.spf is not None else None, m_spf)
    locked = tuple(k for k, src in (("nspf", nspf_src), ("spf", spf_src)) if src == "user")

    model_lams = prediction[1] if prediction else None
    out = _recommend_core(
        feat, pool, eligible, cfg,
        league_id=g("league_id"), ref_ts=ref_ts,
        nspf=use_nspf, spf=use_spf, locked=locked, bf_odds=bf_odds,
        model_lams=model_lams,
    )
    out["match_id"] = match_id
    out["constraint"]["source"] = {
        "nspf": nspf_src if out["constraint"]["nspf"] else "none",
        "spf": spf_src if out["constraint"]["spf"] else "none",
    }
    out["heuristic"] = {"nspf": h_nspf, "spf": h_spf}
    out["model"] = {"nspf": m_nspf, "spf": m_spf} if prediction else None
    out["model_available"] = prediction is not None
    if g("status") == "finished" and g("result"):
        hg, ag = g("home_goals"), g("away_goals")
        if hg is not None and ag is not None:
            actual = score_key(int(hg), int(ag))
            out["actual_score"] = actual
            out["hit"] = any(t["score"] == actual for t in out.get("top3") or [])
    return out


def recommend_for_matches(
    db,
    match_ids: Sequence[str],
    *,
    nspf: str = DIRECTION_ANY,
    spf: str = DIRECTION_ANY,
) -> List[Dict[str, Any]]:
    from db.models import Match

    cfg = resolve_recommend_count(db)
    pool = get_sample_pool(db, cfg)
    rows = {m.id: m for m in db.query(Match).filter(Match.id.in_(list(match_ids))).all()}
    kickoffs = {mid: _kickoff_dt(m.match_date, m.match_time) for mid, m in rows.items()}
    preds: Dict[str, PredictionInput] = {}
    if rows and (DIRECTION_MODEL in (nspf, spf) or _bf_weight(cfg.get("model_prior_weight")) > 0):
        preds = load_pre_match_predictions(db, kickoffs)
    bf_map: Dict[str, str] = {}
    if _bf_weight(cfg.get("bf_prior_weight")) > 0 and rows:
        from services.odds_snapshot_service import load_pre_match_bf

        bf_map = load_pre_match_bf(db, kickoffs)
    items: List[Dict[str, Any]] = []
    for mid in match_ids:
        m = rows.get(mid)
        if m is None:
            items.append({"match_id": mid, "available": False, "reason": "赛事不存在", "top3": []})
            continue
        try:
            items.append(recommend_top3(
                m, pool, cfg, nspf=nspf, spf=spf,
                prediction=preds.get(mid), bf_odds=bf_map.get(mid),
            ))
        except Exception as e:
            logger.warning("score top3 failed for %s: %s", mid, e)
            items.append({"match_id": mid, "available": False, "reason": "计算失败", "top3": []})
    return items


# ===== 回测 =====

def _hit_stats(hits1: int, hits3: int, n: int) -> Dict[str, Any]:
    return {
        "n": n,
        "top1": round(hits1 / n, 4) if n else None,
        "top3": round(hits3 / n, 4) if n else None,
    }


def _heuristic_scores(nspf_sp: np.ndarray, spf_sp: np.ndarray, handicap: int, limit: int = DEFAULT_RECOMMEND_COUNT) -> List[str]:
    from services.odds_heuristics import analyze_odds_heuristics

    src = {"handicap": handicap}
    if not np.isnan(nspf_sp[0]):
        src.update(odds_nspf_win=nspf_sp[0], odds_nspf_draw=nspf_sp[1], odds_nspf_lose=nspf_sp[2])
    src.update(odds_spf_win=spf_sp[0], odds_spf_draw=spf_sp[1], odds_spf_lose=spf_sp[2])
    h = analyze_odds_heuristics(src) or {}
    scores = [h.get("main_score")] + list(h.get("alt_scores") or [])
    return [s.replace("-", ":") for s in scores if s][:recommend_count_of({"recommend_count": limit})]


def _direction_rate(stats: Dict[str, List[int]]) -> Dict[str, Any]:
    def rate(pair):
        return round(pair[0] / pair[1], 4) if pair[1] else None
    return {"n": stats["both"][1], "nspf": rate(stats["nspf"]), "spf": rate(stats["spf"]), "both": rate(stats["both"])}


def backtest(
    db,
    days: int = 60,
    overrides: Optional[Dict[str, Any]] = None,
    pool: Optional[SamplePool] = None,
    predictions: Optional[Dict[str, PredictionInput]] = None,
    bf_by_match: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """滚动回测：每场只用其开赛前已完赛的样本。

    modes：none=不约束；auto=看盘启发式方向；model=赛前模型预测方向（仅统计有赛前预测的场次）；
    oracle=真实胜平负+让球方向（方向判断正确时的命中上限）。
    model_subset：同一批有赛前预测的场次上，不约束 vs 模型方向，便于同口径对比。
    direction_accuracy：看盘倾向 / 模型倾向的方向判断准确率。
    baselines：prior / prior_oracle=只用市场泊松先验（不约束 / 真实方向）；heuristic=看盘启发式写死的比分。
    bf_subset：有完整赛前比分 SP 的场次上，纯泊松先验 vs 纯比分 SP 先验（都不混历史）。
    比分 SP 只来自开赛前快照；没有这一帧的场次不进入该子集。
    model_lambda_subset：有赛前 λ 的场次上，不约束的当前结果 vs 把模型 λ 权重设为 1 的不约束结果。
    不用 5×5 score_matrix。后者没有高于前者时，model_prior_weight 保持 0。
    """
    cfg = resolve_recommend_count(db, get_config(overrides), overrides=overrides)
    days = max(1, int(days))
    if pool is None:
        pool = load_sample_pool(db, int(cfg["lookback_days"]) + days)
    start_ts = (datetime.now() - timedelta(days=days)).timestamp()
    test_idx = np.flatnonzero(pool.kickoff >= start_ts)
    test_idx = test_idx[np.argsort(pool.kickoff[test_idx], kind="stable")]
    if predictions is None:
        predictions = {}
        if db is not None and test_idx.size:
            predictions = load_pre_match_predictions(
                db, {pool.match_ids[i]: datetime.fromtimestamp(pool.kickoff[i]) for i in test_idx}
            )
    if bf_by_match is None:
        bf_by_match = {}
        if db is not None and test_idx.size:
            from services.odds_snapshot_service import load_pre_match_bf

            bf_by_match = load_pre_match_bf(
                db, {pool.match_ids[i]: datetime.fromtimestamp(float(pool.kickoff[i])) for i in test_idx}
            )

    modes = ("none", "auto", "model", "oracle")
    agg = {m: [0, 0, 0] for m in modes}
    subset_none = [0, 0, 0]
    dir_stats = {
        src: {"nspf": [0, 0], "spf": [0, 0], "both": [0, 0]} for src in ("auto", "model")
    }
    prior_agg = [0, 0, 0]
    prior_oracle_agg = [0, 0, 0]
    heur_agg = [0, 0, 0]
    bf_poisson_agg = [0, 0, 0]
    bf_prior_agg = [0, 0, 0]
    lambda_none_agg = [0, 0, 0]
    lambda_model_agg = [0, 0, 0]
    by_hc: Dict[int, Dict[str, List[int]]] = {}
    fallback_counts = {str(k): 0 for k in FALLBACK_LABELS}
    eff_sum = 0.0

    for i in test_idx:
        hc = int(pool.handicap[i])
        nspf_p = None if np.isnan(pool.nspf[i, 0]) else pool.nspf[i]
        feat = Features(handicap=hc, nspf=nspf_p, spf=pool.spf[i])
        eligible = pool.kickoff + _FINISH_GAP_SECONDS <= pool.kickoff[i]
        actual = score_key(pool.home_goals[i], pool.away_goals[i])
        diff = int(pool.home_goals[i] - pool.away_goals[i])
        bf_odds = bf_by_match.get(pool.match_ids[i])
        pred = predictions.get(pool.match_ids[i])
        model_lams = pred[1] if pred and pred[1] else None
        common = dict(
            league_id=pool.league[i], ref_ts=float(pool.kickoff[i]),
            bf_odds=bf_odds, model_lams=model_lams,
        )

        src = {"handicap": hc, "odds_spf_win": pool.spf_sp[i, 0],
               "odds_spf_draw": pool.spf_sp[i, 1], "odds_spf_lose": pool.spf_sp[i, 2]}
        if nspf_p is not None:
            src.update(odds_nspf_win=pool.nspf_sp[i, 0], odds_nspf_draw=pool.nspf_sp[i, 1],
                       odds_nspf_lose=pool.nspf_sp[i, 2])
        h_nspf, h_spf = _heuristic_directions(src)
        actual_dir = (outcome_of(diff), outcome_of(diff + hc))
        directions = {
            "none": (None, None),
            "auto": (h_nspf if nspf_p is not None else None, h_spf),
            "model": model_directions(pred, hc),
            "oracle": actual_dir,
        }
        for src_name in ("auto", "model"):
            n_dir, s_dir = directions[src_name]
            st = dir_stats[src_name]
            if n_dir:
                st["nspf"][0] += int(n_dir == actual_dir[0])
                st["nspf"][1] += 1
            if s_dir:
                st["spf"][0] += int(s_dir == actual_dir[1])
                st["spf"][1] += 1
            if n_dir and s_dir:
                st["both"][0] += int((n_dir, s_dir) == actual_dir)
                st["both"][1] += 1

        bucket = by_hc.setdefault(hc, {"none": [0, 0, 0], "auto": [0, 0, 0], "prior": [0, 0, 0]})
        none_tops: List[str] = []
        for mode in modes:
            if mode == "model" and pred is None:
                continue
            n_dir, s_dir = directions[mode]
            rec = _recommend_core(feat, pool, eligible, cfg, nspf=n_dir, spf=s_dir, **common)
            tops = [t["score"] for t in rec["top3"]]
            h1, h3 = int(bool(tops) and tops[0] == actual), int(actual in tops)
            targets = [agg[mode]]
            if mode in bucket:
                targets.append(bucket[mode])
            if mode == "none" and pred is not None:
                targets.append(subset_none)
            for stats in targets:
                stats[0] += h1
                stats[1] += h3
                stats[2] += 1
            if mode == "none":
                none_tops = tops
                fallback_counts[str(rec["fallback_level"])] += 1
                eff_sum += rec["samples"]["effective"]

        if model_lambda_grid(model_lams) is not None:
            if _bf_weight(cfg.get("model_prior_weight")) == 0:
                base_tops = none_tops
            else:
                base_rec = _recommend_core(
                    feat, pool, eligible, cfg, model_weight=0, **common
                )
                base_tops = [t["score"] for t in base_rec["top3"]]
            alt_rec = _recommend_core(
                feat, pool, eligible, cfg, model_weight=1, **common
            )
            alt_tops = [t["score"] for t in alt_rec["top3"]]
            for stats, tops in ((lambda_none_agg, base_tops), (lambda_model_agg, alt_tops)):
                stats[0] += int(bool(tops) and tops[0] == actual)
                stats[1] += int(actual in tops)
                stats[2] += 1

        prior_rec = _recommend_core(
            feat, pool, eligible, cfg, force_level=3, bf_weight=0, model_weight=0, **common
        )
        prior_tops = [t["score"] for t in prior_rec["top3"]]
        for stats in (prior_agg, bucket["prior"]):
            stats[0] += int(bool(prior_tops) and prior_tops[0] == actual)
            stats[1] += int(actual in prior_tops)
            stats[2] += 1
        if bf_implied_grid(bf_odds) is not None:
            bf_only = _recommend_core(
                feat, pool, eligible, cfg, force_level=3, bf_weight=1, **common
            )
            bf_tops = [t["score"] for t in bf_only["top3"]]
            for stats, tops in ((bf_poisson_agg, prior_tops), (bf_prior_agg, bf_tops)):
                stats[0] += int(bool(tops) and tops[0] == actual)
                stats[1] += int(actual in tops)
                stats[2] += 1
        o_nspf, o_spf = directions["oracle"]
        prior_oracle = _recommend_core(
            feat, pool, eligible, cfg, force_level=3, nspf=o_nspf, spf=o_spf,
            bf_weight=0, model_weight=0, **common,
        )
        po_tops = [t["score"] for t in prior_oracle["top3"]]
        prior_oracle_agg[0] += int(bool(po_tops) and po_tops[0] == actual)
        prior_oracle_agg[1] += int(actual in po_tops)
        prior_oracle_agg[2] += 1

        if nspf_p is not None:
            heur = _heuristic_scores(
                pool.nspf_sp[i], pool.spf_sp[i], hc, limit=recommend_count_of(cfg),
            )
            if heur:
                heur_agg[0] += int(heur[0] == actual)
                heur_agg[1] += int(actual in heur)
                heur_agg[2] += 1

    n_test = int(test_idx.size)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "days": days,
        "test_size": n_test,
        "pool_size": len(pool),
        "params": {k: cfg[k] for k in (
            "recommend_count", "lookback_days", "k", "bandwidth", "smoothing_alpha", "same_league_boost",
            "recency_half_life_days", "min_effective_samples", "no_snapshot_weight",
            "bf_prior_weight", "model_prior_weight",
        )},
        "modes": {m: _hit_stats(*agg[m]) for m in modes},
        "model_subset": {
            "n": agg["model"][2],
            "none": _hit_stats(*subset_none),
            "model": _hit_stats(*agg["model"]),
        },
        "direction_accuracy": {src: _direction_rate(v) for src, v in dir_stats.items()},
        "baselines": {
            "prior": _hit_stats(*prior_agg),
            "prior_oracle": _hit_stats(*prior_oracle_agg),
            "heuristic": _hit_stats(*heur_agg),
        },
        "bf_subset": {
            "n": bf_poisson_agg[2],
            "prior": _hit_stats(*bf_poisson_agg),
            "bf_prior": _hit_stats(*bf_prior_agg),
        },
        "model_lambda_subset": {
            "n": lambda_none_agg[2],
            "none": _hit_stats(*lambda_none_agg),
            "model_prior": _hit_stats(*lambda_model_agg),
        },
        "by_handicap": [
            {
                "handicap": hc,
                "none": _hit_stats(*v["none"]),
                "auto": _hit_stats(*v["auto"]),
                "prior": _hit_stats(*v["prior"]),
            }
            for hc, v in sorted(by_hc.items(), key=lambda kv: -kv[1]["none"][2])
        ],
        "fallback_levels": fallback_counts,
        "avg_effective_samples": round(eff_sum / n_test, 2) if n_test else None,
        "disclaimer": "回测为历史统计对照，不代表未来表现，不构成投注建议",
    }


def _rate_of(report: Dict[str, Any], *path: str) -> Optional[float]:
    node: Any = report
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if node is None:
        return None
    try:
        return float(node)
    except (TypeError, ValueError):
        return None


def tune_none_delta(report: Dict[str, Any]) -> Optional[float]:
    """不约束 Top3 相对市场泊松先验（不约束）的差值。页面默认「不限」看这个数。"""
    none = _rate_of(report, "modes", "none", "top3")
    prior = _rate_of(report, "baselines", "prior", "top3")
    if none is None or prior is None:
        return None
    return none - prior


def tune_oracle_gap(report: Dict[str, Any]) -> Optional[float]:
    """真实方向 Top3 相对「先验 + 真实方向」的差值。为负表示历史在方向已知时不如纯先验。"""
    oracle = _rate_of(report, "modes", "oracle", "top3")
    floor = _rate_of(report, "baselines", "prior_oracle", "top3")
    if oracle is None or floor is None:
        return None
    return oracle - floor


def rank_tune_results(
    results: Sequence[Tuple[Dict[str, Any], Dict[str, Any]]],
) -> Tuple[List[Tuple[Dict[str, Any], Dict[str, Any]]], List[Tuple[Dict[str, Any], Dict[str, Any]]]]:
    """网格结果分成（通过门槛的候选，被剔除的）。

    剔除：真实方向 Top3 低于「先验 + 真实方向」，或任一侧命中率缺失。
    候选排序：先按不约束 Top3 − 先验不约束 Top3 降序，再按真实方向 Top3 降序。
    差值为正才值得考虑写回配置；本函数不改配置。
    """
    eligible: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    rejected: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for item in results:
        gap = tune_oracle_gap(item[1])
        delta = tune_none_delta(item[1])
        passed = gap is not None and gap >= 0 and delta is not None
        (eligible if passed else rejected).append(item)

    def sort_key(item: Tuple[Dict[str, Any], Dict[str, Any]]) -> Tuple[float, float]:
        report = item[1]
        delta = tune_none_delta(report)
        oracle = _rate_of(report, "modes", "oracle", "top3")
        return (
            delta if delta is not None else float("-inf"),
            oracle if oracle is not None else float("-inf"),
        )

    eligible.sort(key=sort_key, reverse=True)
    return eligible, rejected


# 与回测卡片「高于基线 0.5 个百分点才标绿」一致
TUNE_MARGIN = 0.005


def _subset_beats(report: Dict[str, Any], group: str, candidate: str, baseline: str) -> bool:
    """子集上候选 Top3 高于对照超过 TUNE_MARGIN。场次为 0 或命中率缺失视为未过线。"""
    block = report.get(group) if isinstance(report, dict) else None
    if not isinstance(block, dict) or not block.get("n"):
        return False
    cand = _rate_of(report, group, candidate, "top3")
    base = _rate_of(report, group, baseline, "top3")
    if cand is None or base is None:
        return False
    return cand > base + TUNE_MARGIN


def prior_weight_decision(*reports: Dict[str, Any]) -> Dict[str, Any]:
    """分别决定两条先验权重，不和 k / 带宽 / α / 最小样本一起搜。

    比分 SP：bf_subset 里纯比分先验的不约束 Top3 高于同批泊松。
    模型 λ：model_lambda_subset 里权重为 1 的不约束 Top3 高于同批当前结果。
    每个给定窗口都要过线，权重才取 1，否则保持 0。
    两路都取 1 时才允许把 smoothing_alpha 调到当前值以下。
    """
    bf_ok = bool(reports) and all(
        _subset_beats(report, "bf_subset", "bf_prior", "prior") for report in reports
    )
    model_ok = bool(reports) and all(
        _subset_beats(report, "model_lambda_subset", "model_prior", "none") for report in reports
    )
    return {
        "bf_prior_weight": 1.0 if bf_ok else 0.0,
        "model_prior_weight": 1.0 if model_ok else 0.0,
        "retune_alpha": bool(bf_ok and model_ok),
    }


def tune_row_advice(
    report: Dict[str, Any],
    *,
    retune_alpha: bool,
    current_alpha: float,
) -> str:
    """网格一行的建议。两路先验未同时过线时，不把 α 降到当前配置以下。"""
    alpha = _rate_of(report, "params", "smoothing_alpha")
    if not retune_alpha and alpha is not None and alpha < float(current_alpha):
        return "暂不下调 α"
    delta = tune_none_delta(report)
    if delta is not None and delta > 0:
        return "可考虑"
    return "未超过先验"
