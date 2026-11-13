"""数据库模型 - SQLAlchemy ORM"""
from sqlalchemy import (
    Column, String, Integer, BigInteger, DECIMAL, DATE, TIME, TEXT,
    TIMESTAMP, ForeignKey, UniqueConstraint, Index, Boolean,
    Enum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class League(Base):
    """联赛表"""
    __tablename__ = 'leagues'

    id = Column(String(20), primary_key=True)
    name = Column(String(100), nullable=False)
    icon = Column(String(50))
    logo = Column(String(255))
    region = Column(String(50))
    category = Column(String(20), default='international')
    country = Column(String(50))
    flag = Column(String(50))
    level = Column(Integer, default=1)
    parent_id = Column(String(20), ForeignKey('leagues.id'), nullable=True)
    avg_goals = Column(DECIMAL(4, 2), default=2.70)
    is_active = Column(Boolean, default=True)
    source_url = Column(String(255))
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    parent = relationship('League', remote_side=[id], backref='children')
    teams = relationship('Team', back_populates='league')
    matches = relationship('Match', back_populates='league')


class Team(Base):
    """球队表"""
    __tablename__ = 'teams'

    id = Column(String(20), primary_key=True)
    name = Column(String(100), nullable=False)
    short_name = Column(String(20), nullable=False)
    logo = Column(String(255))
    league_id = Column(String(20), ForeignKey('leagues.id'))
    country = Column(String(50))
    elo_rating = Column(Integer, default=1500)
    attack_strength = Column(DECIMAL(4, 3), default=1.000)
    defense_strength = Column(DECIMAL(4, 3), default=1.000)
    xg_for = Column(DECIMAL(5, 3), default=1.350)
    xg_against = Column(DECIMAL(5, 3), default=1.350)
    home_ground = Column(String(100))
    founded_year = Column(Integer)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    league = relationship('League', back_populates='teams')
    home_matches = relationship('Match', foreign_keys='Match.home_team_id', back_populates='home_team')
    away_matches = relationship('Match', foreign_keys='Match.away_team_id', back_populates='away_team')
    players = relationship('Player', back_populates='team')
    aliases = relationship('TeamAlias', back_populates='team')


class TeamAlias(Base):
    """队名别名（DB 可维护，优先于硬编码 TEAM_ALIASES 的人工补丁）"""
    __tablename__ = 'team_aliases'

    id = Column(Integer, primary_key=True, autoincrement=True)
    alias = Column(String(120), nullable=False)
    team_id = Column(String(20), ForeignKey('teams.id'), nullable=False)
    league_id = Column(String(20), ForeignKey('leagues.id'), nullable=True)
    espn_abbr = Column(String(20))
    status = Column(Enum('pending', 'confirmed', 'rejected'), default='pending', nullable=False)
    source = Column(String(20), default='manual')
    note = Column(String(255))
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    team = relationship('Team', back_populates='aliases')
    league = relationship('League')

    __table_args__ = (
        UniqueConstraint('alias', name='uk_team_alias'),
        Index('idx_team_alias_team', 'team_id'),
        Index('idx_team_alias_status', 'status'),
    )


class Player(Base):
    """球员表"""
    __tablename__ = 'players'

    id = Column(String(30), primary_key=True)
    name = Column(String(100), nullable=False)
    short_name = Column(String(20))
    jersey_number = Column(Integer)
    position = Column(Enum('GK', 'CB', 'RB', 'LB', 'DM', 'CM', 'AM', 'RM', 'LM', 'RW', 'LW', 'ST'))
    team_id = Column(String(20), ForeignKey('teams.id'))
    nationality = Column(String(50))
    birth_date = Column(DATE)
    height = Column(Integer)
    weight = Column(Integer)
    foot = Column(Enum('left', 'right', 'both'))
    market_value = Column(DECIMAL(15, 2))
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    appearances = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    photo = Column(String(255))
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    team = relationship('Team', back_populates='players')

    __table_args__ = (
        Index('idx_players_team', 'team_id'),
        Index('idx_players_position', 'position'),
    )


class Match(Base):
    """赛事表"""
    __tablename__ = 'matches'

    id = Column(String(50), primary_key=True)
    league_id = Column(String(20), ForeignKey('leagues.id'))
    home_team_id = Column(String(20), ForeignKey('teams.id'), nullable=False)
    away_team_id = Column(String(20), ForeignKey('teams.id'), nullable=False)
    match_date = Column(DATE, nullable=False)
    match_time = Column(TIME)
    venue = Column(String(100))
    weather = Column(String(50))
    temperature = Column(String(20))
    pitch_condition = Column(String(20))
    status = Column(Enum('upcoming', 'live', 'finished'), default='upcoming')
    home_goals = Column(Integer, default=0)
    away_goals = Column(Integer, default=0)
    result = Column(Enum('H', 'A', 'D'))
    # 竞彩扩展字段（对标 500.com 列表）
    fixture_id = Column(String(30))
    process_id = Column(String(30))
    handicap = Column(Integer)
    odds_nspf_win = Column(DECIMAL(6, 2))
    odds_nspf_draw = Column(DECIMAL(6, 2))
    odds_nspf_lose = Column(DECIMAL(6, 2))
    odds_spf_win = Column(DECIMAL(6, 2))
    odds_spf_draw = Column(DECIMAL(6, 2))
    odds_spf_lose = Column(DECIMAL(6, 2))
    # 竞彩比分玩法 SP：JSON 映射 比分→赔率（含胜/平/负其它）
    odds_bf_json = Column(TEXT)
    # 半场胜平负三选一 SP（由半全场 9 项真实 SP 边际推导，来源标记 hh_derived，非官方直采）
    odds_hspf_win = Column(DECIMAL(6, 2))
    odds_hspf_draw = Column(DECIMAL(6, 2))
    odds_hspf_lose = Column(DECIMAL(6, 2))
    # 半全场 9 项原始真实 SP（胜胜/胜平/胜负/平胜/平平/平负/负胜/负平/负负），JSON
    odds_hh_json = Column(TEXT)
    is_single = Column(Boolean, default=False)
    buy_end_time = Column(String(30))
    # 竞彩比分列表（live.500.com/jczq.php）：半场比分 / 场次编号 / 采集来源
    half_score = Column(String(10))
    match_no = Column(String(20))
    source = Column(String(20))
    # 比分列中间亚盘盘口文案（平手/球半/受一球等，非竞彩整数让球）
    handicap_line = Column(String(30))
    stage = Column(
        Enum(
            'group', 'round_of_16', 'quarter_final', 'semi_final',
            'third_place', 'final', 'league', 'qualifying', 'knockout',
            'playoff', 'play_in',
        ),
        default='league',
    )
    group_name = Column(String(10))
    round_name = Column(String(20))
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    league = relationship('League', back_populates='matches')
    home_team = relationship('Team', foreign_keys=[home_team_id], back_populates='home_matches')
    away_team = relationship('Team', foreign_keys=[away_team_id], back_populates='away_matches')
    predictions = relationship('MatchPrediction', back_populates='match')
    risk_alerts = relationship('RiskAlert', back_populates='match')
    player_stats = relationship('MatchPlayerStat', back_populates='match')
    team_stats = relationship('MatchTeamStat', back_populates='match')


class MatchPlayerStat(Base):
    """赛事球员统计表"""
    __tablename__ = 'match_player_stats'

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(50), ForeignKey('matches.id'), nullable=False)
    player_id = Column(String(30), ForeignKey('players.id'), nullable=False)
    team_id = Column(String(20), ForeignKey('teams.id'))
    is_home = Column(Boolean, nullable=False)
    position = Column(Enum('GK', 'CB', 'RB', 'LB', 'DM', 'CM', 'AM', 'RM', 'LM', 'RW', 'LW', 'ST'))
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    shots = Column(Integer, default=0)
    shots_on_target = Column(Integer, default=0)
    passes = Column(Integer, default=0)
    pass_accuracy = Column(DECIMAL(5, 2))
    tackles = Column(Integer, default=0)
    interceptions = Column(Integer, default=0)
    clearances = Column(Integer, default=0)
    dribbles = Column(Integer, default=0)
    dribble_success = Column(Integer, default=0)
    fouls_committed = Column(Integer, default=0)
    fouls_suffered = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    minutes_played = Column(Integer, default=0)
    rating = Column(DECIMAL(3, 1))
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    match = relationship('Match', back_populates='player_stats')
    player = relationship('Player')
    team = relationship('Team')

    __table_args__ = (
        Index('idx_match_player_match', 'match_id'),
        Index('idx_match_player_player', 'player_id'),
        Index('idx_match_player_team', 'team_id'),
        UniqueConstraint('match_id', 'player_id', name='uq_match_player'),
    )


class MatchTeamStat(Base):
    """赛事球队技术统计（射门/射正等；供 xG 与 ESPN 缺球员行时兜底）"""
    __tablename__ = 'match_team_stats'

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(50), ForeignKey('matches.id'), nullable=False)
    team_id = Column(String(20), ForeignKey('teams.id'), nullable=False)
    is_home = Column(Boolean, nullable=False)
    shots = Column(Integer, default=0)
    shots_on_target = Column(Integer, default=0)
    possession = Column(DECIMAL(5, 2))
    corners = Column(Integer)
    source = Column(String(20), default='unknown')
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    match = relationship('Match', back_populates='team_stats')
    team = relationship('Team')

    __table_args__ = (
        Index('idx_match_team_match', 'match_id'),
        Index('idx_match_team_team', 'team_id'),
        UniqueConstraint('match_id', 'team_id', name='uq_match_team_stat'),
    )


class OddsSnapshot(Base):
    """赔率时序快照（分析用，非投注建议）"""
    __tablename__ = 'odds_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(50), ForeignKey('matches.id'), nullable=False)
    fixture_id = Column(String(30))
    source = Column(String(20), default='500_trade')
    captured_at = Column(TIMESTAMP, default=datetime.now, nullable=False)
    handicap = Column(Integer)
    odds_nspf_win = Column(DECIMAL(6, 2))
    odds_nspf_draw = Column(DECIMAL(6, 2))
    odds_nspf_lose = Column(DECIMAL(6, 2))
    odds_spf_win = Column(DECIMAL(6, 2))
    odds_spf_draw = Column(DECIMAL(6, 2))
    odds_spf_lose = Column(DECIMAL(6, 2))
    # 竞彩比分 SP。只在采集当时写入；赛果回写会覆盖 matches.odds_bf_json，不能倒推成赛前价
    odds_bf_json = Column(TEXT)
    # 半场胜平负三选一 SP（半全场边际推导，快照只记采集当时值）
    odds_hspf_win = Column(DECIMAL(6, 2))
    odds_hspf_draw = Column(DECIMAL(6, 2))
    odds_hspf_lose = Column(DECIMAL(6, 2))
    # 半全场 9 项原始真实 SP
    odds_hh_json = Column(TEXT)
    created_at = Column(TIMESTAMP, default=datetime.now)

    match = relationship('Match', backref='odds_snapshots')

    __table_args__ = (
        Index('idx_odds_snap_match_time', 'match_id', 'captured_at'),
        Index('idx_odds_snap_fixture', 'fixture_id'),
    )


class JingcaiMatchOdds(Base):
    """竞彩足球当前在售玩法的赔率视图（500 trade.500.com/jczq 采集）。

    与 odds_snapshots 分工：本表保存「某一销售日的当前在售玩法完整数据」，
    以 500 侧主键 process_id + process_date 唯一；只保留最近 N 个销售日。
    各玩法 SP 存 JSON（键为 500 data-value，如 bf "1:0" / bqc "3-3" / jqs "7"）。
    仅供学习研究，不构成投注建议。
    """
    __tablename__ = 'jingcai_match_odds'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 500 侧主键
    process_id = Column(String(20), nullable=False)
    process_date = Column(String(10), nullable=False)
    # 场次信息
    match_num = Column(String(20))          # 周二001
    fixture_id = Column(String(30))
    match_id_500 = Column(String(30))       # 500 的 matchid
    home_team_id = Column(String(20))
    away_team_id = Column(String(20))
    league_name = Column(String(100))
    league_rank = Column(String(30))
    home_name = Column(String(100), nullable=False)
    away_name = Column(String(100), nullable=False)
    match_date = Column(DATE)
    match_time = Column(String(10))
    buy_end_time = Column(String(30))
    is_end = Column(Boolean, default=False)
    handicap = Column(Integer)              # 让球盘口（主队让球数）
    kdg = Column(Boolean, default=False)    # 是否可单关
    # 各玩法单关/过关开关：{"spf":{"dg":true,"gg":true}, ...}
    subactive_json = Column(TEXT)
    # 各玩法 SP：{"spf":{"3":2.1,"1":3.2,"0":3.5}, ...}
    odds_json = Column(TEXT)
    # 赛果（历史对照用）
    home_goals = Column(Integer)
    away_goals = Column(Integer)
    result = Column(String(1))              # H/D/A
    source = Column(String(20), default='500_trade_mix')
    captured_at = Column(TIMESTAMP, default=datetime.now, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint('process_id', 'process_date', name='uq_jingcai_process'),
        Index('idx_jingcai_date', 'process_date'),
        Index('idx_jingcai_fixture', 'fixture_id'),
    )


class JingcaiSpChange(Base):
    """竞彩 SP 异动记录（轮询时对比前后 odds_json 生成）。

    记录单场某玩法某选项的赔率变化：old_sp → new_sp，供异动监测与告警。
    仅供学习研究，不构成投注建议。
    """
    __tablename__ = 'jingcai_sp_change'

    id = Column(Integer, primary_key=True, autoincrement=True)
    process_id = Column(String(20), nullable=False)
    process_date = Column(String(10), nullable=False)
    match_num = Column(String(20))
    home_name = Column(String(100))
    away_name = Column(String(100))
    league_name = Column(String(100))
    play = Column(String(10), nullable=False)      # spf/nspf/bf/jqs/bqc
    option = Column(String(10), nullable=False)    # 选项值，如 3/1/0、1:0、7
    old_sp = Column(DECIMAL(10, 3))
    new_sp = Column(DECIMAL(10, 3))
    change_pct = Column(DECIMAL(10, 4))            # (new-old)/old
    change_type = Column(String(10), default='normal')  # normal | spike
    alert = Column(Boolean, default=False)         # 是否触发阈值告警
    threshold = Column(DECIMAL(10, 4))             # 触发时的阈值
    detected_at = Column(TIMESTAMP, default=datetime.now, nullable=False)

    __table_args__ = (
        Index('idx_sp_change_process', 'process_id', 'process_date'),
        Index('idx_sp_change_detected', 'detected_at'),
        Index('idx_sp_change_alert', 'alert'),
    )


class MatchPrediction(Base):
    """赛事预测表"""
    __tablename__ = 'match_predictions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(50), ForeignKey('matches.id'), nullable=False)
    model_version = Column(String(20), default='v5.0.0')
    lambda_home = Column(DECIMAL(4, 2))
    lambda_away = Column(DECIMAL(4, 2))
    home_win_prob = Column(DECIMAL(6, 4))
    draw_prob = Column(DECIMAL(6, 4))
    away_win_prob = Column(DECIMAL(6, 4))
    main_score = Column(String(10))
    alt_scores = Column(TEXT)
    total_goals = Column(String(20))
    tendency = Column(String(200))
    confidence = Column(Enum('high', 'mid', 'low'))
    risk_level = Column(Enum('high', 'mid', 'low'))
    key_variables = Column(TEXT)
    analysis = Column(TEXT)
    score_matrix = Column(TEXT)
    meta_json = Column(TEXT)  # xG / 权重来源等扩展字段
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    match = relationship('Match', back_populates='predictions')


class SimulationHistory(Base):
    """模拟预测历史（参数 + 结果摘要）。仅回看用，非正式预测记录。"""
    __tablename__ = 'simulation_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(50), nullable=False)
    match_name = Column(String(200))
    simulations = Column(Integer)
    seed = Column(BigInteger)
    params_json = Column(TEXT)
    summary_json = Column(TEXT)
    elapsed_ms = Column(Integer)
    created_at = Column(TIMESTAMP, default=datetime.now)

    __table_args__ = (
        Index('idx_sim_history_created', 'created_at'),
        Index('idx_sim_history_match', 'match_id'),
    )


class SimulationBet(Base):
    """模拟投注单（一行一选项）。

    仅供学习/研究/数据分析，不构成投注建议、不接入真实资金。
    结算以 sp_at_create（下单时刻 SP）为准，避免赛时 SP 变动歧义。
    单关：combination_id IS NULL，独立结算。
    串关：同 combination_id 多行共享，组合整体结算（任一未中→整组 lost，
    全部命中→各腿 SP 乘积 × 2 × 倍数，封顶 PAYOUT_CAP_PARLAY）。
    """
    __tablename__ = 'simulation_bets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    match_id = Column(String(50), nullable=False)
    match_no = Column(String(20))
    match_name = Column(String(200))
    play_type = Column(Enum('spf', 'nspf', 'bf', 'tg', 'hspf'), nullable=False)
    selection = Column(String(30), nullable=False)
    sp_at_create = Column(DECIMAL(8, 2), nullable=False)
    sp_source_at_create = Column(Enum('snapshot', 'real', 'synthetic', 'manual'), nullable=False)
    stake = Column(DECIMAL(8, 2), nullable=False, default=2.00)
    multiple = Column(Integer, nullable=False, default=1)
    status = Column(
        Enum('pending', 'won', 'lost', 'void'),
        default='pending', nullable=False,
    )
    payout = Column(DECIMAL(10, 2), nullable=False, default=0)
    settle_note = Column(String(100))
    # 结算连续失败计数（赛果缺失等），达到阈值置 void
    settle_fail_count = Column(Integer, nullable=False, default=0)
    # 结算时使用的赛果快照（"hg:ag"），用于赛果改判竞态对比
    settle_score_snapshot = Column(String(10))
    settled_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, default=datetime.now)
    # 串关组合 ID：同组合多行共享；NULL = 单关（兼容既有行）
    combination_id = Column(String(40), index=True)
    is_parlay = Column(Boolean, default=False)

    user = relationship('User')

    __table_args__ = (
        Index('idx_sim_bet_user_created', 'user_id', 'created_at'),
        Index('idx_sim_bet_status', 'status'),
        Index('idx_sim_bet_match', 'match_id'),
        Index('idx_sim_bet_combination', 'user_id', 'combination_id'),
    )


class User(Base):
    """用户表"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    avatar = Column(String(255))
    level = Column(String(20), default='free')
    favorite_team_id = Column(String(20), ForeignKey('teams.id'))
    join_date = Column(DATE)
    total_analysis = Column(Integer, default=0)
    subscription_plan = Column(String(30), default='free')
    subscription_expire = Column(DATE)
    subscription_status = Column(Enum('active', 'expired', 'cancelled'), default='expired')
    is_active = Column(Boolean, default=True)
    # 首次登录必须改密码：生产初始化时用默认弱口令创建的账号置 1，
    # 改密成功后清零。NULL（未迁移的旧库）按 False 处理。
    must_change_password = Column(Boolean, default=False)
    last_login_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    favorite_team = relationship('Team')
    favorites = relationship('UserFavorite', back_populates='user')
    followed_leagues = relationship('UserFollowedLeague', back_populates='user', cascade='all, delete-orphan')
    history = relationship('UserHistory', back_populates='user')
    preferences = relationship('UserPreference', back_populates='user', uselist=False)
    roles = relationship('Role', secondary='user_roles', back_populates='users')


class SubscriptionPlan(Base):
    """订阅套餐定义（时长由套餐决定，features_json 为权益码列表）"""
    __tablename__ = 'subscription_plans'

    code = Column(String(30), primary_key=True)
    name = Column(String(50), nullable=False)
    tier = Column(String(20), nullable=False, default='free')  # free / pro / flagship
    duration_days = Column(Integer, default=0)  # 0 = 不限时长（免费版）
    price = Column(DECIMAL(10, 2), default=0)
    features_json = Column(TEXT)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)


class SubscriptionRecord(Base):
    """订阅流水（开通/续费/取消），任一时刻每用户至多一条 active"""
    __tablename__ = 'subscription_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    plan_code = Column(String(30), ForeignKey('subscription_plans.code'), nullable=False)
    start_date = Column(DATE, nullable=False)
    end_date = Column(DATE)  # free 套餐为 NULL
    status = Column(Enum('active', 'expired', 'cancelled'), default='active', nullable=False)
    source = Column(String(20), default='admin_grant')
    operator_id = Column(Integer, ForeignKey('users.id'))
    note = Column(String(255))
    created_at = Column(TIMESTAMP, default=datetime.now)

    user = relationship('User', foreign_keys=[user_id])
    operator = relationship('User', foreign_keys=[operator_id])
    plan = relationship('SubscriptionPlan')

    __table_args__ = (
        Index('idx_sub_records_user', 'user_id'),
        Index('idx_sub_records_status', 'status'),
    )


class UserFavorite(Base):
    """用户收藏表"""
    __tablename__ = 'user_favorites'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    match_id = Column(String(50), ForeignKey('matches.id'))
    team_id = Column(String(20), ForeignKey('teams.id'))
    type = Column(Enum('match', 'team'), nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.now)

    user = relationship('User', back_populates='favorites')
    match = relationship('Match')
    team = relationship('Team')

    __table_args__ = (
        UniqueConstraint('user_id', 'match_id', name='uk_fav_user_match'),
        UniqueConstraint('user_id', 'team_id', name='uk_fav_user_team'),
    )


class UserHistory(Base):
    """用户历史分析记录"""
    __tablename__ = 'user_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    match_id = Column(String(50), ForeignKey('matches.id'), nullable=False)
    match_name = Column(String(200))
    prediction = Column(String(20))
    actual = Column(String(20))
    result = Column(Enum('correct', 'partial', 'wrong'))
    created_at = Column(TIMESTAMP, default=datetime.now)

    user = relationship('User', back_populates='history')
    match = relationship('Match')


class UserFollowedLeague(Base):
    """用户关注的联赛（与收藏赛事/球队、默认联赛偏好分开）"""
    __tablename__ = 'user_followed_leagues'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    league_id = Column(String(20), ForeignKey('leagues.id'), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, default=datetime.now)

    user = relationship('User', back_populates='followed_leagues')
    league = relationship('League')

    __table_args__ = (
        UniqueConstraint('user_id', 'league_id', name='uk_user_followed_league'),
        Index('idx_followed_user', 'user_id'),
    )


class UserPreference(Base):
    """用户偏好设置"""
    __tablename__ = 'user_preferences'

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    push_notification = Column(Boolean, default=True)
    refresh_interval = Column(Integer, default=5)
    default_league_id = Column(String(20), ForeignKey('leagues.id'))
    follow_include_children = Column(Boolean, default=False)
    theme = Column(String(20), default='dark')
    language = Column(String(20), default='zh-CN')
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    user = relationship('User', back_populates='preferences')
    default_league = relationship('League')


class ModelVersion(Base):
    """模型版本表"""
    __tablename__ = 'model_versions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(20), unique=True, nullable=False)
    description = Column(TEXT)
    accuracy = Column(DECIMAL(5, 2))
    status = Column(Enum('current', 'archived'), default='current')
    training_data_start = Column(DATE)
    training_data_end = Column(DATE)
    weights_json = Column(TEXT)
    created_at = Column(TIMESTAMP, default=datetime.now)


class TrainingRecord(Base):
    """模型训练记录"""
    __tablename__ = 'training_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(Enum('running', 'success', 'failed'), default='running')
    message = Column(String(255))
    model_version = Column(String(20))
    total_matches = Column(Integer, default=0)
    data_start = Column(DATE)
    data_end = Column(DATE)
    accuracy = Column(DECIMAL(6, 4))
    duration_ms = Column(Integer, default=0)
    results_json = Column(TEXT)
    suggestions_json = Column(TEXT)
    snapshot_json = Column(TEXT)
    started_at = Column(TIMESTAMP, default=datetime.now)
    finished_at = Column(TIMESTAMP)

    __table_args__ = (
        Index('idx_training_records_started', 'started_at'),
    )


class RiskAlert(Base):
    """风险预警表"""
    __tablename__ = 'risk_alerts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(50), ForeignKey('matches.id'))
    match_name = Column(String(200))
    type = Column(Enum('data_abnormal', 'high_risk', 'weather', 'pitch', 'injury'), nullable=False)
    level = Column(Enum('high', 'mid', 'low'), nullable=False)
    description = Column(TEXT)
    recommended_action = Column(TEXT)
    is_processed = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=datetime.now)

    match = relationship('Match', back_populates='risk_alerts')


class Standing(Base):
    """积分榜"""
    __tablename__ = 'standings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(String(20), ForeignKey('leagues.id'), nullable=False)
    team_id = Column(String(20), ForeignKey('teams.id'), nullable=False)
    season = Column(String(20), nullable=False)
    rank = Column(Integer, default=0)
    played = Column(Integer, default=0)
    won = Column(Integer, default=0)
    drawn = Column(Integer, default=0)
    lost = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    goal_diff = Column(Integer, default=0)
    points = Column(Integer, default=0)
    update_date = Column(DATE)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint('league_id', 'team_id', 'season', name='uk_standings_league_team_season'),
    )


class TopScorer(Base):
    """射手榜"""
    __tablename__ = 'top_scorers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_name = Column(String(100), nullable=False)
    team_id = Column(String(20), ForeignKey('teams.id'))
    league_id = Column(String(20), ForeignKey('leagues.id'), nullable=False)
    season = Column(String(20), nullable=False)
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    games_played = Column(Integer, default=0)
    rank = Column(Integer, default=0)
    update_date = Column(DATE)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    team = relationship('Team')
    league = relationship('League')


class AccuracyTrend(Base):
    """模型准确率趋势"""
    __tablename__ = 'accuracy_trend'

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_version = Column(String(20), ForeignKey('model_versions.version'), nullable=False)
    date = Column(DATE, nullable=False)
    accuracy = Column(DECIMAL(5, 2))
    total_matches = Column(Integer, default=0)
    correct_matches = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('date', 'model_version', name='uk_trend_date_version'),
    )


class OperationLog(Base):
    """操作日志"""
    __tablename__ = 'operation_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(String(100))
    detail = Column(TEXT)
    ip_address = Column(String(50))
    created_at = Column(TIMESTAMP, default=datetime.now)

    user = relationship('User')


class AppSetting(Base):
    """运行时配置。页面可改的项写在这里，缺省时回退 config.yaml。"""
    __tablename__ = 'app_settings'

    key = Column(String(64), primary_key=True)
    value = Column(String(255), nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)


class ScheduledTaskStatus(Base):
    """定时任务状态表 - 持久化任务启用/停止状态，重启后据此恢复"""
    __tablename__ = 'scheduled_task_status'

    task_id = Column(String(50), primary_key=True)
    is_enabled = Column(Boolean, default=False, nullable=False)
    interval_minutes = Column(Integer, default=60)
    last_run_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)


class CrawlLog(Base):
    """采集日志"""
    __tablename__ = 'crawl_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    crawl_type = Column(String(20), default='manual', nullable=False)
    crawl_category = Column(String(20), default='match', nullable=False)
    league_id = Column(String(20))
    league_name = Column(String(100))
    found_count = Column(Integer, default=0)
    saved_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    status = Column(Enum('success', 'failed'), nullable=False)
    error_message = Column(TEXT)
    crawled_data = Column(TEXT)
    log_file = Column(String(500))
    started_at = Column(TIMESTAMP, nullable=False)
    finished_at = Column(TIMESTAMP)
    duration_ms = Column(Integer)

    __table_args__ = (
        Index('idx_crawl_logs_type', 'crawl_type'),
        Index('idx_crawl_logs_category', 'crawl_category'),
        Index('idx_crawl_logs_league', 'league_id'),
        Index('idx_crawl_logs_status', 'status'),
        Index('idx_crawl_logs_started_at', 'started_at'),
    )


class Role(Base):
    """角色表"""
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    is_system = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    permissions = relationship('Permission', secondary='role_permissions', back_populates='roles')
    users = relationship('User', secondary='user_roles', back_populates='roles')


class Permission(Base):
    """权限表"""
    __tablename__ = 'permissions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    code = Column(String(100), unique=True, nullable=False)
    type = Column(String(20), default='menu')
    parent_id = Column(Integer, default=0)
    path = Column(String(255))
    icon = Column(String(50))
    sort_order = Column(Integer, default=0)
    description = Column(String(255))
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)

    roles = relationship('Role', secondary='role_permissions', back_populates='permissions')


class RolePermission(Base):
    """角色权限关联表"""
    __tablename__ = 'role_permissions'

    role_id = Column(Integer, ForeignKey('roles.id'), primary_key=True)
    permission_id = Column(Integer, ForeignKey('permissions.id'), primary_key=True)
    created_at = Column(TIMESTAMP, default=datetime.now)


class UserRole(Base):
    """用户角色关联表"""
    __tablename__ = 'user_roles'

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    role_id = Column(Integer, ForeignKey('roles.id'), primary_key=True)
    created_at = Column(TIMESTAMP, default=datetime.now)
