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
