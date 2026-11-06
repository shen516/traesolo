"""prize_calculator 单元测试：SP 回退、让球聚合、比分 31 项、奖金规则。"""

from types import SimpleNamespace

from services import prize_calculator as pc


class _EmptyQuery:
    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return None


class _FakeDB:
    def query(self, *a, **k):
        return _EmptyQuery()


def _mc():
    """构造一份 simulate_detailed 风格的输出（9x9 矩阵，单元格之和=1）。

    与胜/平/负概率一致：主胜 0.55、平 0.25、客胜 0.20。
    """
    size = 9
    cells = {
        # 主胜（diff>0）合计 0.55；其中 BF_HOME_KEYS 内 0.32，其余进"胜其它"0.23
        (1, 0): 0.10, (2, 0): 0.06, (2, 1): 0.11, (3, 1): 0.05,
        (6, 0): 0.10, (7, 1): 0.08, (8, 2): 0.05,
        # 平（diff=0）合计 0.25；BF_DRAW_KEYS 内 0.20，其余进"平其它"0.05
        (0, 0): 0.08, (1, 1): 0.12, (4, 4): 0.05,
        # 客胜（diff<0）合计 0.20；BF_AWAY_KEYS 内 0.11，其余进"负其它"0.09
        (0, 1): 0.07, (1, 2): 0.04, (3, 6): 0.09,
    }
    matrix = [[0.0] * size for _ in range(size)]
    for (h, a), v in cells.items():
        matrix[h][a] = v
    goal_distribution = [{"goals": g, "prob": 0.1} for g in range(11)]
    return {
        "home_win_prob": 0.55,
        "draw_prob": 0.25,
        "away_win_prob": 0.20,
        "score_matrix": matrix,
        "score_matrix_size": size,
        "goal_distribution": goal_distribution,
        "over_2_5_prob": 0.5,
        "over_3_5_prob": 0.3,
        "btts_prob": 0.5,
        "top_scores": [{"score": "1-1", "prob": 0.12}],
        "total_goals_avg": 2.5,
        "total_goals_std": 1.3,
        "simulations": 1000,
        "seed": 1,
    }


def _match(**kw):
    base = dict(
        id="M1", handicap=-1,
        odds_spf_win=1.8, odds_spf_draw=3.4, odds_spf_lose=4.2,
        odds_nspf_win=2.6, odds_nspf_draw=3.3, odds_nspf_lose=2.3,
        odds_bf_json=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_spf_real_sp_and_ev():
    prize = pc.calculate_prize(_FakeDB(), _match(), _mc())
    spf = prize["spf"]
    assert prize["sp_source"]["spf"] == "real"
    assert spf["sp"]["win"] == 1.8
    assert spf["probs"]["win"] == 0.55
    # EV = P × SP × 2 − 2 = 0.55 × 1.8 × 2 − 2 = −0.02
    assert spf["ev"]["win"] == -0.02
    # 单注奖金 = 2 × SP
    assert spf["payout"]["win"] == 3.6
    # 隐含概率归一化
    assert abs(sum(spf["implied"].values()) - 1.0) < 1e-3


def test_synthetic_mode_uses_model_probs():
    prize = pc.calculate_prize(_FakeDB(), _match(), _mc(), sp_mode="synthetic", overround=0.13)
    assert prize["sp_source"]["spf"] == "synthetic"
    sp = prize["spf"]["sp"]["win"]
    # SP = 1 / (0.55 × 1.13) ≈ 1.606
    assert abs(sp - 1 / (0.55 * 1.13)) < 0.01


def test_manual_sp_overrides():
    manual = {"spf": {"win": 2.0, "draw": 3.0, "lose": 3.5}}
    prize = pc.calculate_prize(_FakeDB(), _match(), _mc(), manual_sp=manual)
    assert prize["sp_source"]["spf"] == "manual"
    assert prize["spf"]["sp"]["win"] == 2.0


def test_nspf_handicap_aggregation():
    """让球 -1：让球后主胜 = 原始净胜 ≥ 2。"""
    prize = pc.calculate_prize(_FakeDB(), _match(), _mc())
    nspf = prize["nspf"]
    assert nspf["handicap"] == -1
    assert nspf["handicap_source"] == "match"
    # 让球后主胜（净胜≥2）：2:0(0.06)+3:1(0.05)+6:0(0.10)+7:1(0.08)+8:2(0.05)=0.34
    assert abs(nspf["probs"]["win"] - 0.34) < 1e-6
    # 让球后平（净胜=1）：1:0(0.10)+2:1(0.11)=0.21
    assert abs(nspf["probs"]["draw"] - 0.21) < 1e-6
    assert abs(sum(nspf["probs"].values()) - 1.0) < 1e-3

    # 手动让球覆盖
    prize2 = pc.calculate_prize(_FakeDB(), _match(), _mc(), handicap=0)
    assert prize2["nspf"]["handicap"] == 0
    assert prize2["nspf"]["handicap_source"] == "manual"


def test_bf_31_options_and_other_bucket():
    prize = pc.calculate_prize(
        _FakeDB(),
        _match(odds_bf_json='{"1:0": 7.5, "2:1": 8.5, "胜其它": 20.0}'),
        _mc(),
    )
    bf = prize["bf"]
    assert prize["sp_source"]["bf"] == "real"
    # 31 个选项全部有概率
    assert len(bf["probs"]) == 31
    # 胜其它 = 主胜 − 已知主胜比分 = 0.55 − (0.10+0.06+0.11+0.05) = 0.23
    assert abs(bf["probs"]["胜其它"] - 0.23) < 1e-6
    assert abs(sum(bf["probs"].values()) - 1.0) < 1e-3
    # top_value 只覆盖有 SP 的选项，按 EV 降序
    assert len(bf["top_value"]) == 3
    assert bf["top_value"][0]["score"] == "胜其它"
    assert bf["top_value"][0]["ev"] >= bf["top_value"][-1]["ev"]


def test_tg_distribution_and_synthetic():
    prize = pc.calculate_prize(_FakeDB(), _match(), _mc())
    tg = prize["tg"]
    assert prize["sp_source"]["tg"] == "synthetic"
    assert set(tg["probs"].keys()) == {"0", "1", "2", "3", "4", "5", "6", "7+"}
    assert tg["probs"]["3"] == 0.1
    assert abs(sum(tg["probs"].values()) - 1.0) < 1e-3


def test_payout_cap_and_floor():
    assert pc._payout(60000) == 100000  # 上限
    assert pc._payout(0.5) == 2.0  # 不足 2 元补足
    assert pc._payout(3.0) == 6.0


def test_value_flag_threshold():
    """edge > 0.02 才标记价值。"""
    probs = {"win": 0.60, "draw": 0.20, "lose": 0.20}
    # SP 隐含：win 0.5 → edge 0.10 → 价值
    sp = {"win": 2.0, "draw": 4.0, "lose": 4.0}
    block = pc._option_block(probs, sp)
    assert block["value_flags"]["win"] is True
    assert block["value_flags"]["draw"] is False
