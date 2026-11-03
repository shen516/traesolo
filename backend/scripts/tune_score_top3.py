"""竞彩比分 Top3 参数网格搜索。

用法：python scripts/tune_score_top3.py [网格回测天数，默认 60]

先用 60 天和 90 天的子集回测分别决定 bf_prior_weight、model_prior_weight
（只取 0 或 1，不和网格相乘）。两路都过线才允许建议把 smoothing_alpha 降到当前值以下。
网格只搜 k、bandwidth、smoothing_alpha、min_effective_samples，权重锁定为上面的决定。

排序：先按「不约束 Top3 − 先验不约束 Top3」降序，再按真实方向 Top3 降序。
真实方向 Top3 低于「先验 + 真实方向」的组合剔除。本脚本只打印，不改配置。
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import SessionLocal  # noqa: E402
from services.jingcai_score_top3 import (  # noqa: E402
    backtest,
    get_config,
    load_sample_pool,
    prior_weight_decision,
    rank_tune_results,
    tune_none_delta,
    tune_row_advice,
)

GRID = {
    "k": [30, 80, 150],
    "bandwidth": [0.03, 0.06, 0.1, 0.15],
    "smoothing_alpha": [5, 10, 20, 40, 80],
    "min_effective_samples": [5, 12, 25],
}
GATE_WINDOWS = (60, 90)


def _fmt(value) -> str:
    return "-" if value is None else f"{value:.4f}"


def _subset_line(report, group, candidate, baseline) -> str:
    block = report.get(group) or {}
    cand = (block.get(candidate) or {}).get("top3")
    base = (block.get(baseline) or {}).get("top3")
    return f"n={block.get('n') or 0} 候选={_fmt(cand)} 对照={_fmt(base)}"


def _print_grid(results, days, decision, current_alpha) -> int:
    if not results or not results[0][1]["test_size"]:
        print("样本不足，无法回测")
        return 1
    base = results[0][1]["baselines"]
    eligible, rejected = rank_tune_results(results)
    print(f"网格回测 {days} 天，测试样本 {results[0][1]['test_size']}，样本库 {results[0][1]['pool_size']}")
    print(f"基线 先验(不约束) top3={base['prior']['top3']}  先验(真实方向) top3={base['prior_oracle']['top3']}"
          f"  启发式 top3={base['heuristic']['top3']}")
    print(f"候选 {len(eligible)} 组，剔除 {len(rejected)} 组"
          f"（真实方向 Top3 低于先验+真实方向，或命中率缺失）")
    print("排序：d.none = 不约束 Top3 − 先验不约束；其次真实方向 Top3。d.none > 0 且建议为「可考虑」才写回。")
    if not eligible:
        print("没有组合通过门槛，不建议改配置")
        return 0
    print(f"{'k':>4} {'bw':>5} {'alpha':>5} {'min_eff':>7} | "
          f"{'none.t1':>7} {'none.t3':>7} {'d.none':>7} {'orc.t1':>7} {'orc.t3':>7} | 建议")
    for params, report in eligible[:15]:
        modes = report["modes"]
        delta = tune_none_delta(report)
        advice = tune_row_advice(report, retune_alpha=decision["retune_alpha"], current_alpha=current_alpha)
        print(f"{params['k']:>4} {params['bandwidth']:>5} {params['smoothing_alpha']:>5} "
              f"{params['min_effective_samples']:>7} | {_fmt(modes['none']['top1']):>7} {_fmt(modes['none']['top3']):>7} "
              f"{_fmt(delta):>7} {_fmt(modes['oracle']['top1']):>7} {_fmt(modes['oracle']['top3']):>7} | {advice}")
    return 0


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    cfg = get_config()
    current_alpha = float(cfg["smoothing_alpha"])
    db = SessionLocal()
    try:
        pool = load_sample_pool(db, int(cfg["lookback_days"]) + max(days, max(GATE_WINDOWS)))
        gate_reports = []
        print("权重单独判定（不进入 k/带宽/α/最小样本网格）；60 天和 90 天都要过线。")
        for window in GATE_WINDOWS:
            report = backtest(db, days=window, overrides={
                "bf_prior_weight": 0,
                "model_prior_weight": 0,
            }, pool=pool)
            gate_reports.append(report)
            print(f"  {window} 天  比分SP {_subset_line(report, 'bf_subset', 'bf_prior', 'prior')}"
                  f"  |  模型λ {_subset_line(report, 'model_lambda_subset', 'model_prior', 'none')}")
        decision = prior_weight_decision(*gate_reports)
        print(f"锁定 bf_prior_weight={decision['bf_prior_weight']:g}"
              f"  model_prior_weight={decision['model_prior_weight']:g}")
        if decision["retune_alpha"]:
            print("两路都过线，网格里的 α 可以低于当前值。")
        else:
            print(f"两路未同时过线，α 低于当前 {current_alpha:g} 的行标为「暂不下调 α」。")
        print("不搜 lookback_days、same_league_boost、no_snapshot_weight、recommend_count。")

        results = []
        keys = list(GRID)
        locked = {
            "bf_prior_weight": decision["bf_prior_weight"],
            "model_prior_weight": decision["model_prior_weight"],
        }
        for values in itertools.product(*(GRID[k] for k in keys)):
            params = dict(zip(keys, values))
            params.update(locked)
            results.append((params, backtest(db, days=days, overrides=params, pool=pool)))
    finally:
        db.close()

    return _print_grid(results, days, decision, current_alpha)


if __name__ == "__main__":
    raise SystemExit(main())
