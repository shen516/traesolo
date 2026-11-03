"""泊松分布模型 - 核心预测引擎"""
import numpy as np
from scipy.stats import poisson


class PoissonModel:
    def __init__(self, max_goals=10):
        self.max_goals = max_goals

    def calculate_lambda(self, attack_strength, defense_strength, league_avg, is_home=False, home_adv=1.15):
        """
        计算预期进球数 λ
        λ = 攻击力 × 防守力 × 联赛均值 × (主场优势)
        """
        factor = home_adv if is_home else 1.0
        return attack_strength * defense_strength * league_avg * factor

    def predict_score_matrix(self, lambda_home, lambda_away):
        """生成比分概率矩阵 (max_goals × max_goals)"""
        matrix = np.zeros((self.max_goals, self.max_goals))
        for i in range(self.max_goals):
            for j in range(self.max_goals):
                matrix[i][j] = poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
        return matrix

    def predict(self, lambda_home, lambda_away):
        """完整预测: 胜平负概率 + 比分矩阵 + 最可能比分"""
        matrix = self.predict_score_matrix(lambda_home, lambda_away)

        home_win = float(np.tril(matrix, -1).sum())
        draw = float(np.trace(matrix))
        away_win = float(np.triu(matrix, 1).sum())

        # 取概率最高的5个比分
        flat = []
        for i in range(self.max_goals):
            for j in range(self.max_goals):
                if i + j <= 6:  # 只考虑合理比分
                    flat.append((f"{i}-{j}", matrix[i][j]))
        flat.sort(key=lambda x: x[1], reverse=True)
        top_scores = flat[:5]

        return {
            "home_win_prob": home_win,
            "draw_prob": draw,
            "away_win_prob": away_win,
            "score_matrix": matrix[:5, :5].tolist(),
            "main_score": top_scores[0][0],
            "alt_scores": [s[0] for s in top_scores[1:4]],
        }
