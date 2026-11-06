"""蒙特卡洛模拟 - 通过大量随机模拟提升预测精度"""
import numpy as np


class MonteCarloSimulator:
    def __init__(self, simulations=10000, seed=None):
        self.simulations = simulations
        self.rng = np.random.default_rng(seed)

    def simulate(self, lambda_home, lambda_away):
        """批量模拟比赛并统计结果"""
        home_goals = self.rng.poisson(lambda_home, self.simulations)
        away_goals = self.rng.poisson(lambda_away, self.simulations)

        home_wins = int(np.sum(home_goals > away_goals))
        draws = int(np.sum(home_goals == away_goals))
        away_wins = int(np.sum(home_goals < away_goals))

        # 比分频率统计
        score_counts = {}
        for h, a in zip(home_goals, away_goals):
            key = f"{h}-{a}"
            score_counts[key] = score_counts.get(key, 0) + 1

        top_scores = sorted(score_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        total_goals = home_goals + away_goals

        return {
            "home_win_prob": home_wins / self.simulations,
            "draw_prob": draws / self.simulations,
            "away_win_prob": away_wins / self.simulations,
            "top_scores": [(s, c / self.simulations) for s, c in top_scores],
            "total_goals_avg": float(np.mean(total_goals)),
            "total_goals_std": float(np.std(total_goals)),
        }

    def simulate_detailed(self, lambda_home, lambda_away, *, simulations=None,
                          seed=None, max_goals=8):
        """
        模拟明细输出（供模拟预测使用）：
        胜/平/负、比分矩阵、Top 比分、总进球分布(0~10+)、大 2.5/3.5、双方进球。
        使用独立 RNG，不修改共享 self.rng。
        """
        n = int(simulations) if simulations else int(self.simulations)
        rng = np.random.default_rng(seed)

        home_goals = rng.poisson(lambda_home, n)
        away_goals = rng.poisson(lambda_away, n)

        home_win_prob = float(np.mean(home_goals > away_goals))
        draw_prob = float(np.mean(home_goals == away_goals))
        away_win_prob = float(np.mean(home_goals < away_goals))

        size = max(2, int(max_goals) + 1)
        score_matrix = np.zeros((size, size), dtype=float)
        capped_h = np.clip(home_goals, 0, size - 1)
        capped_a = np.clip(away_goals, 0, size - 1)
        np.add.at(score_matrix, (capped_h, capped_a), 1.0)
        score_matrix /= n

        flat = score_matrix.flatten()
        top_idx = np.argsort(flat)[::-1][:8]
        top_scores = [
            {"score": f"{idx // size}-{idx % size}", "prob": round(float(flat[idx]), 4)}
            for idx in top_idx
            if flat[idx] > 0
        ]

        total_goals = home_goals + away_goals
        goal_max = 10  # 0~9，10 表示 10+
        goal_distribution = []
        counts = np.bincount(np.clip(total_goals, 0, goal_max), minlength=goal_max + 1)
        for g in range(goal_max + 1):
            goal_distribution.append({
                "goals": g,
                "prob": round(float(counts[g]) / n, 4),
            })

        return {
            "home_win_prob": round(home_win_prob, 4),
            "draw_prob": round(draw_prob, 4),
            "away_win_prob": round(away_win_prob, 4),
            "top_scores": top_scores,
            "goal_distribution": goal_distribution,
            "total_goals_avg": round(float(np.mean(total_goals)), 4),
            "total_goals_std": round(float(np.std(total_goals)), 4),
            "over_2_5_prob": round(float(np.mean(total_goals > 2)), 4),
            "over_3_5_prob": round(float(np.mean(total_goals > 3)), 4),
            "btts_prob": round(float(np.mean((home_goals > 0) & (away_goals > 0))), 4),
            "score_matrix": [[round(float(v), 4) for v in row] for row in score_matrix],
            "score_matrix_size": size,
            "simulations": n,
            "seed": seed,
        }
