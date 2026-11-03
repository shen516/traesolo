"""ELO评级模型 - 评估球队相对实力"""


class EloModel:
    def __init__(self, k_factor=32, home_advantage=100, initial_rating=1500):
        self.k = k_factor
        self.home_advantage = home_advantage
        self.initial_rating = initial_rating
        # 预置评级作为无库数据时的回退
        self.ratings = {
            "MCI": 2085, "ARS": 2020, "LIV": 2050, "CHE": 1880, "MUN": 1860,
            "TOT": 1900, "RMA": 2100, "BAR": 2030, "ATM": 1950, "BAY": 2090,
            "DOR": 1880, "JUV": 1920, "INT": 1960, "MIL": 1890, "PSG": 2000,
            "BRA": 2150, "ARG": 2120, "FRA": 2100, "ENG": 2070, "ESP": 2050,
            "GER": 2010, "NED": 1980, "POR": 1960, "ITA": 1940, "BEL": 1920,
            "URU": 1930, "CRO": 1890, "COL": 1880, "MAR": 1860, "JPN": 1870,
            "USA": 1850, "MEX": 1830, "KOR": 1840, "SEN": 1830, "DEN": 1840,
            "SUI": 1850, "CHI": 1840, "ECU": 1800, "PER": 1790, "SRB": 1820,
            "CAN": 1770, "IRN": 1780, "KSA": 1760, "AUS": 1770, "NGA": 1810,
            "CAM": 1780,
        }

    def set_rating(self, team_id, rating):
        if team_id and rating is not None:
            self.ratings[team_id] = int(rating)

    def expected_score(self, rating_a, rating_b, is_home=False, home_advantage=None):
        ha = self.home_advantage if home_advantage is None else home_advantage
        if is_home:
            rating_a = float(rating_a) + float(ha)
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    def predict_prob(self, team_a, team_b, rating_a=None, rating_b=None, home_advantage=None):
        """返回胜平负概率 (基于ELO实力差)，三项之和归一化为 1。"""
        ra = int(rating_a) if rating_a is not None else self.ratings.get(team_a, self.initial_rating)
        rb = int(rating_b) if rating_b is not None else self.ratings.get(team_b, self.initial_rating)

        expected_home = self.expected_score(ra, rb, is_home=True, home_advantage=home_advantage)

        diff = abs(ra - rb)
        draw_prob = max(0.20, 0.35 - diff * 0.0003)

        if expected_home > 0.5:
            home_win = expected_home - draw_prob / 2
            away_win = 1 - home_win - draw_prob
        else:
            expected_away = 1 - expected_home
            away_win = expected_away - draw_prob / 2
            home_win = 1 - away_win - draw_prob

        home_win = max(0.05, home_win)
        away_win = max(0.05, away_win)
        draw_prob = max(0.05, draw_prob)
        total = home_win + away_win + draw_prob
        return {
            "home_win_prob": home_win / total,
            "draw_prob": draw_prob / total,
            "away_win_prob": away_win / total,
            "elo_diff": ra - rb,
        }

    def get_rating(self, team_id):
        return self.ratings.get(team_id, self.initial_rating)

    def update_match(
        self,
        ratings: dict,
        home_team: str,
        away_team: str,
        home_goals: int,
        away_goals: int,
        k_factor=None,
        home_advantage=None,
    ) -> dict:
        """按场更新评级（不把主场加成写入存量分）。返回更新后的 ratings。"""
        k = float(self.k if k_factor is None else k_factor)
        ha = float(self.home_advantage if home_advantage is None else home_advantage)
        ra = float(ratings.get(home_team, self.initial_rating))
        rb = float(ratings.get(away_team, self.initial_rating))
        expected_a = self.expected_score(ra, rb, is_home=True, home_advantage=ha)
        expected_b = 1.0 - expected_a
        if home_goals > away_goals:
            actual_a, actual_b = 1.0, 0.0
        elif home_goals < away_goals:
            actual_a, actual_b = 0.0, 1.0
        else:
            actual_a, actual_b = 0.5, 0.5
        goal_diff = abs(home_goals - away_goals)
        k_multiplier = 1 + min(goal_diff, 3) * 0.25
        ratings[home_team] = ra + k * k_multiplier * (actual_a - expected_a)
        ratings[away_team] = rb + k * k_multiplier * (actual_b - expected_b)
        return ratings
