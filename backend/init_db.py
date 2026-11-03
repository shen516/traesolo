"""数据库初始化脚本 - 创建表 + 插入超级管理员 + 初始数据"""
import sys
import os
from datetime import date, timedelta
import bcrypt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import engine, SessionLocal
from db import models
from services import (
    LeagueService, TeamService, ModelService, MatchService, PlayerService
)

SUPER_ADMIN = {
    "username": "admin",
    "email": "admin@football-analytics.com",
    "password": "admin123",
    "level": "professional",
    "subscription_plan": "flag_year",
    "subscription_status": "active",
}

# 出厂弱口令。仅当 admin 仍在使用该口令（或与其相同）时才强制首次登录改密，
# 改过一次后 must_change_password 归零，不会被启动逻辑反复置回。
DEFAULT_ADMIN_PASSWORD = SUPER_ADMIN["password"]


def _skip_force_password() -> bool:
    """本地开发/测试可显式跳过强制改密（生产不要开）。"""
    return os.environ.get("TRAESOLO_SKIP_FORCE_PASSWORD", "").lower() in ("1", "true", "yes")

_INIT_DONE = False


def init_database(force: bool = False):
    """初始化数据库（进程内默认只跑一次，避免训练/二次 import 重复刷库）。"""
    global _INIT_DONE
    if _INIT_DONE and not force:
        return

    print("=" * 50)
    print("开始初始化数据库...")
    print("=" * 50)

    models.Base.metadata.create_all(bind=engine)
    print("[1/4] 数据表创建完成")

    _add_missing_columns()

    db = SessionLocal()

    try:
        _init_leagues(db)
        print("[2/4] 联赛数据初始化完成")

        # 插入球队数据
        _init_teams(db)
        print("[3/4] 球队数据初始化完成")

        # 创建超级管理员
        _init_super_admin(db)
        print("[4/4] 超级管理员创建完成")

        # 插入赛事数据
        _init_matches(db)
        print("[5/5] 赛事数据初始化完成")

        # 插入模型版本
        _init_model_versions(db)
        print("[附加] 模型版本数据初始化完成")

        # 插入球员数据
        _init_players(db)
        print("[附加] 球员数据初始化完成")

        # 初始化角色和权限
        _init_roles_permissions(db)
        print("[附加] 角色权限数据初始化完成")

        # 订阅套餐种子 + 旧 plan 值迁移
        _init_subscription_plans(db)
        print("[附加] 订阅套餐初始化完成")

        print("=" * 50)
        print("数据库初始化完成!")
        print(f"  超级管理员账号: {SUPER_ADMIN['username']}")
        print(f"  超级管理员密码: {SUPER_ADMIN['password']}")
        print("=" * 50)
        _INIT_DONE = True

    finally:
        db.close()


def _init_leagues(db):
    """初始化联赛数据"""
    from services.real_team_crawler import CANONICAL_FIVE00_URL

    leagues = [
        {"id": "EPL", "name": "英超联赛", "icon": "🏴", "region": "欧洲", "level": 1, "avg_goals": 2.85, "is_active": True, "source_url": CANONICAL_FIVE00_URL["EPL"]},
        {"id": "LALIGA", "name": "西甲联赛", "icon": "🇪🇸", "region": "欧洲", "level": 1, "avg_goals": 2.50, "is_active": True, "source_url": CANONICAL_FIVE00_URL["LALIGA"]},
        {"id": "BUNDES", "name": "德甲联赛", "icon": "🇩🇪", "region": "欧洲", "level": 1, "avg_goals": 3.10, "is_active": True, "source_url": CANONICAL_FIVE00_URL["BUNDES"]},
        {"id": "SERIEA", "name": "意甲联赛", "icon": "🇮🇹", "region": "欧洲", "level": 1, "avg_goals": 2.60, "is_active": True, "source_url": CANONICAL_FIVE00_URL["SERIEA"]},
        {"id": "LIGUE1", "name": "法甲联赛", "icon": "🇫🇷", "region": "欧洲", "level": 1, "avg_goals": 2.70, "is_active": True, "source_url": CANONICAL_FIVE00_URL["LIGUE1"]},
        {"id": "UCL", "name": "欧冠联赛", "icon": "🏆", "region": "欧洲", "level": 1, "avg_goals": 2.80, "is_active": True, "source_url": CANONICAL_FIVE00_URL["UCL"]},
        {"id": "UEL", "name": "欧联杯", "icon": "🥈", "region": "欧洲", "level": 2, "parent_id": "UCL", "avg_goals": 2.55, "is_active": True, "source_url": CANONICAL_FIVE00_URL["UEL"]},
        {"id": "ECH", "name": "英冠联赛", "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "region": "欧洲", "level": 2, "avg_goals": 2.55, "is_active": True, "source_url": CANONICAL_FIVE00_URL.get("ECH")},
        {"id": "WC", "name": "世界杯", "icon": "🌍", "region": "国际", "level": 1, "avg_goals": 2.65, "is_active": True, "source_url": CANONICAL_FIVE00_URL.get("WC")},
        {"id": "EC", "name": "欧洲杯", "icon": "🇪🇺", "region": "欧洲", "level": 1, "avg_goals": 2.50, "is_active": False},
        {"id": "CA", "name": "美洲杯", "icon": "🌎", "region": "美洲", "level": 1, "avg_goals": 2.55, "is_active": False},
        {"id": "AFC", "name": "亚洲杯", "icon": "🌏", "region": "亚洲", "level": 1, "avg_goals": 2.60, "is_active": False},
        {"id": "K1", "name": "韩职联", "icon": "🇰🇷", "region": "亚洲", "level": 1, "avg_goals": 2.50, "is_active": True, "source_url": CANONICAL_FIVE00_URL.get("K1")},
        {"id": "SWE", "name": "瑞典超", "icon": "🇸🇪", "region": "欧洲", "level": 1, "avg_goals": 2.60, "is_active": True, "source_url": CANONICAL_FIVE00_URL.get("SWE")},
        {"id": "NOR", "name": "挪威超", "icon": "🇳🇴", "region": "欧洲", "level": 1, "avg_goals": 2.40, "is_active": True, "source_url": CANONICAL_FIVE00_URL.get("NOR")},
        {"id": "FIN", "name": "芬兰超", "icon": "🇫🇮", "region": "欧洲", "level": 1, "avg_goals": 2.50, "is_active": True, "source_url": CANONICAL_FIVE00_URL.get("FIN")},
        {"id": "BRA", "name": "巴甲联赛", "icon": "🇧🇷", "region": "美洲", "level": 1, "avg_goals": 2.70, "is_active": True, "source_url": CANONICAL_FIVE00_URL.get("BRA")},
        {"id": "MLS", "name": "美职联", "icon": "🇺🇸", "region": "美洲", "level": 1, "avg_goals": 2.60, "is_active": True, "source_url": CANONICAL_FIVE00_URL.get("MLS")},
    ]

    for league_data in leagues:
        existing = LeagueService.get_by_id(db, league_data["id"])
        if not existing:
            LeagueService.create(db, league_data)
        else:
            patch = {}
            if league_data.get("source_url") and not existing.source_url:
                patch["source_url"] = league_data["source_url"]
            if league_data.get("parent_id") and not existing.parent_id:
                patch["parent_id"] = league_data["parent_id"]
            # P2/P3：扩展与 NOR/K1 默认启用
            if league_data.get("is_active") and not existing.is_active:
                patch["is_active"] = True
            if patch:
                LeagueService.update(db, league_data["id"], patch)

    from services.league_parent import backfill_league_parents
    backfill_league_parents(db)


def _init_teams(db):
    """初始化球队数据"""
    teams = [
        # 俱乐部
        {"id": "MCI", "name": "曼彻斯特城", "short_name": "曼城", "logo": "🔵", "league_id": "EPL", "country": "英格兰", "elo_rating": 2085, "attack_strength": 1.350, "defense_strength": 0.750, "home_ground": "伊蒂哈德球场"},
        {"id": "ARS", "name": "阿森纳", "short_name": "阿森纳", "logo": "🔴", "league_id": "EPL", "country": "英格兰", "elo_rating": 2020, "attack_strength": 1.200, "defense_strength": 0.800, "home_ground": "酋长球场"},
        {"id": "LIV", "name": "利物浦", "short_name": "利物浦", "logo": "🔴", "league_id": "EPL", "country": "英格兰", "elo_rating": 2050, "attack_strength": 1.280, "defense_strength": 0.850, "home_ground": "安菲尔德球场"},
        {"id": "CHE", "name": "切尔西", "short_name": "切尔西", "logo": "🔵", "league_id": "EPL", "country": "英格兰", "elo_rating": 1880, "attack_strength": 1.000, "defense_strength": 0.950, "home_ground": "斯坦福桥球场"},
        {"id": "MUN", "name": "曼彻斯特联", "short_name": "曼联", "logo": "🔴", "league_id": "EPL", "country": "英格兰", "elo_rating": 1860, "attack_strength": 0.950, "defense_strength": 1.000, "home_ground": "老特拉福德球场"},
        {"id": "TOT", "name": "托特纳姆热刺", "short_name": "热刺", "logo": "⚪", "league_id": "EPL", "country": "英格兰", "elo_rating": 1900, "attack_strength": 1.100, "defense_strength": 0.920, "home_ground": "热刺球场"},
        {"id": "RMA", "name": "皇家马德里", "short_name": "皇马", "logo": "⚪", "league_id": "LALIGA", "country": "西班牙", "elo_rating": 2100, "attack_strength": 1.380, "defense_strength": 0.720, "home_ground": "伯纳乌球场"},
        {"id": "BAR", "name": "巴塞罗那", "short_name": "巴萨", "logo": "🔵", "league_id": "LALIGA", "country": "西班牙", "elo_rating": 2030, "attack_strength": 1.300, "defense_strength": 0.780, "home_ground": "诺坎普球场"},
        {"id": "ATM", "name": "马德里竞技", "short_name": "马竞", "logo": "🔴", "league_id": "LALIGA", "country": "西班牙", "elo_rating": 1950, "attack_strength": 1.100, "defense_strength": 0.850, "home_ground": "万达大都会球场"},
        {"id": "BAY", "name": "拜仁慕尼黑", "short_name": "拜仁", "logo": "🔴", "league_id": "BUNDES", "country": "德国", "elo_rating": 2090, "attack_strength": 1.420, "defense_strength": 0.700, "home_ground": "安联球场"},
        {"id": "DOR", "name": "多特蒙德", "short_name": "多特", "logo": "🟡", "league_id": "BUNDES", "country": "德国", "elo_rating": 1880, "attack_strength": 1.150, "defense_strength": 0.950, "home_ground": "信号伊杜纳公园球场"},
        {"id": "JUV", "name": "尤文图斯", "short_name": "尤文", "logo": "⚪", "league_id": "SERIEA", "country": "意大利", "elo_rating": 1920, "attack_strength": 1.050, "defense_strength": 0.880, "home_ground": "安联球场"},
        {"id": "INT", "name": "国际米兰", "short_name": "国米", "logo": "🔵", "league_id": "SERIEA", "country": "意大利", "elo_rating": 1960, "attack_strength": 1.180, "defense_strength": 0.820, "home_ground": "梅阿查球场"},
        {"id": "MIL", "name": "AC米兰", "short_name": "米兰", "logo": "🔴", "league_id": "SERIEA", "country": "意大利", "elo_rating": 1890, "attack_strength": 1.080, "defense_strength": 0.900, "home_ground": "圣西罗球场"},
        {"id": "PSG", "name": "巴黎圣日耳曼", "short_name": "巴黎", "logo": "🔵", "league_id": "LIGUE1", "country": "法国", "elo_rating": 2000, "attack_strength": 1.320, "defense_strength": 0.800, "home_ground": "王子公园球场"},
        # 世界杯国家队
        {"id": "BRA", "name": "巴西国家队", "short_name": "巴西", "logo": "🇧🇷", "league_id": "WC", "country": "巴西", "elo_rating": 2150, "attack_strength": 1.400, "defense_strength": 0.780, "home_ground": "马拉卡纳球场"},
        {"id": "ARG", "name": "阿根廷国家队", "short_name": "阿根廷", "logo": "🇦🇷", "league_id": "WC", "country": "阿根廷", "elo_rating": 2120, "attack_strength": 1.350, "defense_strength": 0.800, "home_ground": "纪念碑球场"},
        {"id": "FRA", "name": "法国国家队", "short_name": "法国", "logo": "🇫🇷", "league_id": "WC", "country": "法国", "elo_rating": 2100, "attack_strength": 1.330, "defense_strength": 0.760, "home_ground": "法兰西体育场"},
        {"id": "ENG", "name": "英格兰国家队", "short_name": "英格兰", "logo": "🏴", "league_id": "WC", "country": "英格兰", "elo_rating": 2070, "attack_strength": 1.280, "defense_strength": 0.790, "home_ground": "温布利球场"},
        {"id": "ESP", "name": "西班牙国家队", "short_name": "西班牙", "logo": "🇪🇸", "league_id": "WC", "country": "西班牙", "elo_rating": 2050, "attack_strength": 1.250, "defense_strength": 0.810, "home_ground": "伯纳乌球场"},
        {"id": "GER", "name": "德国国家队", "short_name": "德国", "logo": "🇩🇪", "league_id": "WC", "country": "德国", "elo_rating": 2010, "attack_strength": 1.220, "defense_strength": 0.830, "home_ground": "安联球场"},
        {"id": "NED", "name": "荷兰国家队", "short_name": "荷兰", "logo": "🇳🇱", "league_id": "WC", "country": "荷兰", "elo_rating": 1980, "attack_strength": 1.200, "defense_strength": 0.850, "home_ground": "克鲁伊夫竞技场"},
        {"id": "POR", "name": "葡萄牙国家队", "short_name": "葡萄牙", "logo": "🇵🇹", "league_id": "WC", "country": "葡萄牙", "elo_rating": 1960, "attack_strength": 1.180, "defense_strength": 0.860, "home_ground": "光明球场"},
        {"id": "ITA", "name": "意大利国家队", "short_name": "意大利", "logo": "🇮🇹", "league_id": "WC", "country": "意大利", "elo_rating": 1940, "attack_strength": 1.100, "defense_strength": 0.880, "home_ground": "奥林匹克球场"},
        {"id": "BEL", "name": "比利时国家队", "short_name": "比利时", "logo": "🇧🇪", "league_id": "WC", "country": "比利时", "elo_rating": 1920, "attack_strength": 1.120, "defense_strength": 0.870, "home_ground": "博杜安国王体育场"},
        {"id": "URU", "name": "乌拉圭国家队", "short_name": "乌拉圭", "logo": "🇺🇾", "league_id": "WC", "country": "乌拉圭", "elo_rating": 1930, "attack_strength": 1.100, "defense_strength": 0.900, "home_ground": "百年纪念球场"},
        {"id": "CRO", "name": "克罗地亚国家队", "short_name": "克罗地亚", "logo": "🇭🇷", "league_id": "WC", "country": "克罗地亚", "elo_rating": 1890, "attack_strength": 1.080, "defense_strength": 0.900, "home_ground": "马克西米尔球场"},
        {"id": "JPN", "name": "日本国家队", "short_name": "日本", "logo": "🇯🇵", "league_id": "WC", "country": "日本", "elo_rating": 1870, "attack_strength": 1.050, "defense_strength": 0.910, "home_ground": "国立竞技场"},
        {"id": "KOR", "name": "韩国国家队", "short_name": "韩国", "logo": "🇰🇷", "league_id": "WC", "country": "韩国", "elo_rating": 1840, "attack_strength": 1.000, "defense_strength": 0.930, "home_ground": "首尔世界杯球场"},
        {"id": "USA", "name": "美国国家队", "short_name": "美国", "logo": "🇺🇸", "league_id": "WC", "country": "美国", "elo_rating": 1850, "attack_strength": 1.020, "defense_strength": 0.920, "home_ground": "玫瑰碗球场"},
        {"id": "MEX", "name": "墨西哥国家队", "short_name": "墨西哥", "logo": "🇲🇽", "league_id": "WC", "country": "墨西哥", "elo_rating": 1830, "attack_strength": 0.990, "defense_strength": 0.940, "home_ground": "阿兹特克球场"},
        {"id": "MAR", "name": "摩洛哥国家队", "short_name": "摩洛哥", "logo": "🇲🇦", "league_id": "WC", "country": "摩洛哥", "elo_rating": 1860, "attack_strength": 1.030, "defense_strength": 0.920, "home_ground": "穆罕默德五世球场"},
        {"id": "SEN", "name": "塞内加尔国家队", "short_name": "塞内加尔", "logo": "🇸🇳", "league_id": "WC", "country": "塞内加尔", "elo_rating": 1830, "attack_strength": 0.990, "defense_strength": 0.940, "home_ground": "桑戈尔球场"},
        {"id": "DEN", "name": "丹麦国家队", "short_name": "丹麦", "logo": "🇩🇰", "league_id": "WC", "country": "丹麦", "elo_rating": 1840, "attack_strength": 1.000, "defense_strength": 0.940, "home_ground": "帕肯球场"},
        {"id": "SUI", "name": "瑞士国家队", "short_name": "瑞士", "logo": "🇨🇭", "league_id": "WC", "country": "瑞士", "elo_rating": 1850, "attack_strength": 1.020, "defense_strength": 0.930, "home_ground": "万克多夫球场"},
    ]

    for team_data in teams:
        existing = TeamService.get_by_id(db, team_data["id"])
        if not existing:
            TeamService.create(db, team_data)


def _init_super_admin(db):
    """创建超级管理员"""
    from services import UserService

    existing = UserService.get_by_username(db, SUPER_ADMIN["username"])
    if existing:
        # 老库 admin 对齐到旗舰版套餐（角色本身已绕过门控，此处仅为展示一致）
        if existing.subscription_plan != SUPER_ADMIN["subscription_plan"]:
            existing.subscription_plan = SUPER_ADMIN["subscription_plan"]
            existing.subscription_status = "active"
            if not existing.subscription_expire:
                existing.subscription_expire = date.today() + timedelta(days=3650)
        # 弱口令账号一律强制首次登录改密；用户改过一次后本标志为 0，不再反复置回。
        # 本地开发可设 TRAESOLO_SKIP_FORCE_PASSWORD=1 跳过（测试与 CI 也走这个开关）。
        if SUPER_ADMIN["password"] == DEFAULT_ADMIN_PASSWORD \
                and not _skip_force_password() \
                and not existing.must_change_password:
            existing.must_change_password = True
        db.commit()
        print(f"  超级管理员已存在 (username={SUPER_ADMIN['username']})")
        return

    password_hash = bcrypt.hashpw(
        SUPER_ADMIN["password"].encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    UserService.create(db, {
        "username": SUPER_ADMIN["username"],
        "email": SUPER_ADMIN["email"],
        "password_hash": password_hash,
        "level": SUPER_ADMIN["level"],
        "join_date": date.today(),
        "subscription_plan": SUPER_ADMIN["subscription_plan"],
        "subscription_status": SUPER_ADMIN["subscription_status"],
        "subscription_expire": date.today() + timedelta(days=3650),
        "is_active": True,
        "must_change_password": (
            not _skip_force_password() and SUPER_ADMIN["password"] == DEFAULT_ADMIN_PASSWORD
        ),
    })


def _init_model_versions(db):
    """初始化模型版本"""
    versions = [
        {"version": "v5.0.3", "description": "融合 ELO+泊松+蒙特卡洛，权重归一化", "accuracy": 73.5, "status": "current", "weights_json": '{"elo":0.35,"poisson":0.40,"monte_carlo":0.25}'},
        {"version": "v5.0.2", "description": "修复融合权重未归一化导致平局偏高", "accuracy": 71.2, "status": "archived", "weights_json": '{"elo":0.35,"poisson":0.40,"monte_carlo":0.25}'},
        {"version": "v5.0.1", "description": "新增ELO联赛等级系数动态调整", "accuracy": 70.8, "status": "archived", "weights_json": '{"elo":0.35,"poisson":0.35,"monte_carlo":0.30}'},
        {"version": "v5.0.0", "description": "初始职业版发布，集成泊松、ELO、蒙特卡洛", "accuracy": 69.5, "status": "archived", "weights_json": '{"elo":0.33,"poisson":0.34,"monte_carlo":0.33}'},
    ]

    for v in versions:
        existing = ModelService.get_by_version(db, v["version"])
        if not existing:
            ModelService.create(db, v)


def _init_matches(db):
    """不再写入过期演示赛事，真实赛程由采集任务写入。"""
    return


def _init_players(db):
    players = [
        {"id": "MCI-1", "name": "埃德森·莫赖斯", "short_name": "埃德森", "jersey_number": 31, "position": "GK", "team_id": "MCI", "nationality": "巴西", "birth_date": date(1993, 8, 17), "height": 188, "weight": 86, "foot": "right", "market_value": 35000000, "goals": 0, "assists": 0, "appearances": 28, "yellow_cards": 2, "red_cards": 0},
        {"id": "MCI-2", "name": "凯尔·沃克", "short_name": "沃克", "jersey_number": 2, "position": "RB", "team_id": "MCI", "nationality": "英格兰", "birth_date": date(1990, 5, 28), "height": 183, "weight": 78, "foot": "right", "market_value": 20000000, "goals": 1, "assists": 5, "appearances": 26, "yellow_cards": 4, "red_cards": 1},
        {"id": "MCI-3", "name": "鲁本·迪亚斯", "short_name": "迪亚斯", "jersey_number": 3, "position": "CB", "team_id": "MCI", "nationality": "葡萄牙", "birth_date": date(1997, 5, 14), "height": 187, "weight": 80, "foot": "right", "market_value": 80000000, "goals": 3, "assists": 1, "appearances": 30, "yellow_cards": 5, "red_cards": 0},
        {"id": "MCI-4", "name": "埃尔林·哈兰德", "short_name": "哈兰德", "jersey_number": 9, "position": "ST", "team_id": "MCI", "nationality": "挪威", "birth_date": date(2000, 7, 21), "height": 195, "weight": 94, "foot": "right", "market_value": 180000000, "goals": 36, "assists": 8, "appearances": 32, "yellow_cards": 2, "red_cards": 0},
        {"id": "MCI-5", "name": "凯文·德布劳内", "short_name": "德布劳内", "jersey_number": 17, "position": "AM", "team_id": "MCI", "nationality": "比利时", "birth_date": date(1991, 6, 28), "height": 181, "weight": 70, "foot": "right", "market_value": 100000000, "goals": 10, "assists": 18, "appearances": 25, "yellow_cards": 3, "red_cards": 0},
        {"id": "ARS-1", "name": "亚伦·拉姆斯代尔", "short_name": "拉姆斯代尔", "jersey_number": 1, "position": "GK", "team_id": "ARS", "nationality": "英格兰", "birth_date": date(1998, 5, 14), "height": 193, "weight": 86, "foot": "right", "market_value": 40000000, "goals": 0, "assists": 1, "appearances": 30, "yellow_cards": 1, "red_cards": 0},
        {"id": "ARS-2", "name": "威廉·萨利巴", "short_name": "萨利巴", "jersey_number": 4, "position": "CB", "team_id": "ARS", "nationality": "法国", "birth_date": date(2001, 3, 24), "height": 193, "weight": 82, "foot": "right", "market_value": 60000000, "goals": 4, "assists": 2, "appearances": 28, "yellow_cards": 3, "red_cards": 0},
        {"id": "ARS-3", "name": "马丁·厄德高", "short_name": "厄德高", "jersey_number": 8, "position": "CM", "team_id": "ARS", "nationality": "挪威", "birth_date": date(1998, 12, 17), "height": 178, "weight": 72, "foot": "left", "market_value": 70000000, "goals": 12, "assists": 8, "appearances": 31, "yellow_cards": 4, "red_cards": 0},
        {"id": "ARS-4", "name": "布卡约·萨卡", "short_name": "萨卡", "jersey_number": 7, "position": "RW", "team_id": "ARS", "nationality": "英格兰", "birth_date": date(2001, 9, 5), "height": 178, "weight": 70, "foot": "right", "market_value": 90000000, "goals": 14, "assists": 10, "appearances": 32, "yellow_cards": 2, "red_cards": 0},
        {"id": "ARS-5", "name": "加布里埃尔·热苏斯", "short_name": "热苏斯", "jersey_number": 9, "position": "ST", "team_id": "ARS", "nationality": "巴西", "birth_date": date(1997, 4, 3), "height": 175, "weight": 73, "foot": "right", "market_value": 50000000, "goals": 18, "assists": 6, "appearances": 27, "yellow_cards": 3, "red_cards": 0},
        {"id": "LIV-1", "name": "阿里森·贝克尔", "short_name": "阿里森", "jersey_number": 1, "position": "GK", "team_id": "LIV", "nationality": "巴西", "birth_date": date(1992, 10, 2), "height": 193, "weight": 91, "foot": "right", "market_value": 50000000, "goals": 1, "assists": 0, "appearances": 29, "yellow_cards": 0, "red_cards": 0},
        {"id": "LIV-2", "name": "维吉尔·范迪克", "short_name": "范迪克", "jersey_number": 4, "position": "CB", "team_id": "LIV", "nationality": "荷兰", "birth_date": date(1991, 7, 8), "height": 193, "weight": 92, "foot": "right", "market_value": 65000000, "goals": 5, "assists": 2, "appearances": 28, "yellow_cards": 2, "red_cards": 0},
        {"id": "LIV-3", "name": "穆罕默德·萨拉赫", "short_name": "萨拉赫", "jersey_number": 11, "position": "RW", "team_id": "LIV", "nationality": "埃及", "birth_date": date(1992, 6, 15), "height": 175, "weight": 71, "foot": "left", "market_value": 75000000, "goals": 25, "assists": 12, "appearances": 30, "yellow_cards": 1, "red_cards": 0},
        {"id": "LIV-4", "name": "达尔文·努涅斯", "short_name": "努涅斯", "jersey_number": 27, "position": "ST", "team_id": "LIV", "nationality": "乌拉圭", "birth_date": date(1999, 6, 24), "height": 187, "weight": 78, "foot": "right", "market_value": 70000000, "goals": 16, "assists": 5, "appearances": 26, "yellow_cards": 4, "red_cards": 1},
        {"id": "LIV-5", "name": "蒂亚戈·阿尔坎塔拉", "short_name": "蒂亚戈", "jersey_number": 6, "position": "CM", "team_id": "LIV", "nationality": "西班牙", "birth_date": date(1991, 4, 11), "height": 174, "weight": 70, "foot": "right", "market_value": 35000000, "goals": 3, "assists": 4, "appearances": 20, "yellow_cards": 2, "red_cards": 0},
        {"id": "BAY-1", "name": "曼努埃尔·诺伊尔", "short_name": "诺伊尔", "jersey_number": 1, "position": "GK", "team_id": "BAY", "nationality": "德国", "birth_date": date(1986, 3, 27), "height": 193, "weight": 90, "foot": "right", "market_value": 25000000, "goals": 0, "assists": 0, "appearances": 25, "yellow_cards": 1, "red_cards": 0},
        {"id": "BAY-2", "name": "约书亚·基米希", "short_name": "基米希", "jersey_number": 6, "position": "DM", "team_id": "BAY", "nationality": "德国", "birth_date": date(1995, 2, 8), "height": 176, "weight": 75, "foot": "right", "market_value": 80000000, "goals": 5, "assists": 12, "appearances": 30, "yellow_cards": 4, "red_cards": 0},
        {"id": "BAY-3", "name": "托马斯·穆勒", "short_name": "穆勒", "jersey_number": 25, "position": "AM", "team_id": "BAY", "nationality": "德国", "birth_date": date(1989, 9, 13), "height": 185, "weight": 80, "foot": "right", "market_value": 40000000, "goals": 12, "assists": 15, "appearances": 28, "yellow_cards": 2, "red_cards": 0},
        {"id": "BAY-4", "name": "哈里·凯恩", "short_name": "凯恩", "jersey_number": 9, "position": "ST", "team_id": "BAY", "nationality": "英格兰", "birth_date": date(1993, 7, 28), "height": 188, "weight": 86, "foot": "right", "market_value": 90000000, "goals": 28, "assists": 8, "appearances": 30, "yellow_cards": 1, "red_cards": 0},
        {"id": "BAY-5", "name": "贾马尔·穆西亚拉", "short_name": "穆西亚拉", "jersey_number": 42, "position": "AM", "team_id": "BAY", "nationality": "德国", "birth_date": date(2003, 2, 26), "height": 183, "weight": 70, "foot": "right", "market_value": 120000000, "goals": 10, "assists": 10, "appearances": 29, "yellow_cards": 1, "red_cards": 0},
        {"id": "BAR-1", "name": "马克-安德烈·特尔施特根", "short_name": "特尔施特根", "jersey_number": 1, "position": "GK", "team_id": "BAR", "nationality": "德国", "birth_date": date(1992, 4, 30), "height": 187, "weight": 84, "foot": "right", "market_value": 45000000, "goals": 0, "assists": 2, "appearances": 30, "yellow_cards": 0, "red_cards": 0},
        {"id": "BAR-2", "name": "罗纳德·阿劳霍", "short_name": "阿劳霍", "jersey_number": 4, "position": "CB", "team_id": "BAR", "nationality": "乌拉圭", "birth_date": date(1999, 3, 7), "height": 192, "weight": 88, "foot": "right", "market_value": 70000000, "goals": 4, "assists": 1, "appearances": 27, "yellow_cards": 5, "red_cards": 1},
        {"id": "BAR-3", "name": "佩德里", "short_name": "佩德里", "jersey_number": 8, "position": "CM", "team_id": "BAR", "nationality": "西班牙", "birth_date": date(2002, 11, 25), "height": 174, "weight": 68, "foot": "right", "market_value": 100000000, "goals": 8, "assists": 6, "appearances": 25, "yellow_cards": 3, "red_cards": 0},
        {"id": "BAR-4", "name": "加维", "short_name": "加维", "jersey_number": 6, "position": "CM", "team_id": "BAR", "nationality": "西班牙", "birth_date": date(2004, 8, 5), "height": 173, "weight": 65, "foot": "right", "market_value": 80000000, "goals": 5, "assists": 4, "appearances": 24, "yellow_cards": 4, "red_cards": 0},
        {"id": "BAR-5", "name": "罗伯特·莱万多夫斯基", "short_name": "莱万", "jersey_number": 9, "position": "ST", "team_id": "BAR", "nationality": "波兰", "birth_date": date(1988, 8, 21), "height": 185, "weight": 81, "foot": "right", "market_value": 45000000, "goals": 22, "assists": 5, "appearances": 28, "yellow_cards": 2, "red_cards": 0},
        {"id": "RM-1", "name": "蒂博·库尔图瓦", "short_name": "库尔图瓦", "jersey_number": 1, "position": "GK", "team_id": "RMA", "nationality": "比利时", "birth_date": date(1992, 5, 11), "height": 199, "weight": 96, "foot": "right", "market_value": 60000000, "goals": 0, "assists": 0, "appearances": 26, "yellow_cards": 1, "red_cards": 0},
        {"id": "RM-2", "name": "埃德尔·米利唐", "short_name": "米利唐", "jersey_number": 3, "position": "CB", "team_id": "RMA", "nationality": "巴西", "birth_date": date(1998, 1, 18), "height": 186, "weight": 86, "foot": "right", "market_value": 60000000, "goals": 2, "assists": 1, "appearances": 24, "yellow_cards": 4, "red_cards": 0},
        {"id": "RM-3", "name": "托尼·克罗斯", "short_name": "克罗斯", "jersey_number": 8, "position": "CM", "team_id": "RMA", "nationality": "德国", "birth_date": date(1990, 1, 4), "height": 182, "weight": 78, "foot": "right", "market_value": 50000000, "goals": 4, "assists": 8, "appearances": 25, "yellow_cards": 1, "red_cards": 0},
        {"id": "RM-4", "name": "卢卡·莫德里奇", "short_name": "莫德里奇", "jersey_number": 10, "position": "AM", "team_id": "RMA", "nationality": "克罗地亚", "birth_date": date(1985, 9, 9), "height": 174, "weight": 68, "foot": "right", "market_value": 30000000, "goals": 3, "assists": 6, "appearances": 22, "yellow_cards": 2, "red_cards": 0},
        {"id": "RM-5", "name": "裘德·贝林厄姆", "short_name": "贝林厄姆", "jersey_number": 5, "position": "CM", "team_id": "RMA", "nationality": "英格兰", "birth_date": date(2003, 6, 29), "height": 186, "weight": 75, "foot": "right", "market_value": 150000000, "goals": 16, "assists": 8, "appearances": 29, "yellow_cards": 3, "red_cards": 0},
        {"id": "PSG-1", "name": "詹路易吉·多纳鲁马", "short_name": "多纳鲁马", "jersey_number": 99, "position": "GK", "team_id": "PSG", "nationality": "意大利", "birth_date": date(1999, 2, 25), "height": 196, "weight": 90, "foot": "right", "market_value": 65000000, "goals": 0, "assists": 0, "appearances": 28, "yellow_cards": 0, "red_cards": 0},
        {"id": "PSG-2", "name": "马库斯·图拉姆", "short_name": "图拉姆", "jersey_number": 30, "position": "ST", "team_id": "PSG", "nationality": "法国", "birth_date": date(1997, 8, 6), "height": 192, "weight": 86, "foot": "right", "market_value": 50000000, "goals": 14, "assists": 6, "appearances": 26, "yellow_cards": 2, "red_cards": 0},
        {"id": "PSG-3", "name": "奥斯曼·登贝莱", "short_name": "登贝莱", "jersey_number": 10, "position": "RW", "team_id": "PSG", "nationality": "法国", "birth_date": date(1997, 5, 15), "height": 178, "weight": 68, "foot": "right", "market_value": 60000000, "goals": 8, "assists": 10, "appearances": 22, "yellow_cards": 1, "red_cards": 0},
        {"id": "INT-1", "name": "萨姆·厄德高", "short_name": "奥纳纳", "jersey_number": 24, "position": "GK", "team_id": "INT", "nationality": "喀麦隆", "birth_date": date(1996, 4, 2), "height": 190, "weight": 86, "foot": "right", "market_value": 50000000, "goals": 0, "assists": 1, "appearances": 28, "yellow_cards": 1, "red_cards": 1},
        {"id": "INT-2", "name": "马库斯·图拉姆", "short_name": "阿切尔比", "jersey_number": 15, "position": "CB", "team_id": "INT", "nationality": "意大利", "birth_date": date(1988, 2, 10), "height": 188, "weight": 80, "foot": "right", "market_value": 15000000, "goals": 2, "assists": 1, "appearances": 26, "yellow_cards": 4, "red_cards": 0},
        {"id": "INT-3", "name": "哈坎·恰尔汗奥卢", "short_name": "恰尔汗奥卢", "jersey_number": 20, "position": "CM", "team_id": "INT", "nationality": "土耳其", "birth_date": date(1994, 2, 8), "height": 178, "weight": 70, "foot": "right", "market_value": 40000000, "goals": 8, "assists": 10, "appearances": 27, "yellow_cards": 3, "red_cards": 0},
        {"id": "INT-4", "name": "劳塔罗·马丁内斯", "short_name": "劳塔罗", "jersey_number": 10, "position": "ST", "team_id": "INT", "nationality": "阿根廷", "birth_date": date(1997, 8, 22), "height": 174, "weight": 72, "foot": "right", "market_value": 100000000, "goals": 20, "assists": 5, "appearances": 30, "yellow_cards": 4, "red_cards": 0},
        {"id": "JUV-1", "name": "沃伊切赫·什琴斯尼", "short_name": "什琴斯尼", "jersey_number": 1, "position": "GK", "team_id": "JUV", "nationality": "波兰", "birth_date": date(1990, 4, 18), "height": 196, "weight": 90, "foot": "right", "market_value": 15000000, "goals": 0, "assists": 0, "appearances": 25, "yellow_cards": 1, "red_cards": 0},
        {"id": "JUV-2", "name": "杜桑·弗拉霍维奇", "short_name": "弗拉霍维奇", "jersey_number": 7, "position": "ST", "team_id": "JUV", "nationality": "塞尔维亚", "birth_date": date(2000, 1, 28), "height": 190, "weight": 81, "foot": "right", "market_value": 60000000, "goals": 16, "assists": 3, "appearances": 24, "yellow_cards": 3, "red_cards": 0},
        {"id": "BRA-1", "name": "埃弗森", "short_name": "埃弗森", "jersey_number": 12, "position": "GK", "team_id": "BRA", "nationality": "巴西", "birth_date": date(1998, 12, 22), "height": 191, "weight": 85, "foot": "right", "market_value": 20000000, "goals": 0, "assists": 0, "appearances": 5, "yellow_cards": 0, "red_cards": 0},
        {"id": "BRA-2", "name": "维利希莫", "short_name": "维利希莫", "jersey_number": 3, "position": "CB", "team_id": "BRA", "nationality": "巴西", "birth_date": date(2004, 6, 22), "height": 191, "weight": 83, "foot": "right", "market_value": 35000000, "goals": 1, "assists": 0, "appearances": 8, "yellow_cards": 1, "red_cards": 0},
        {"id": "BRA-3", "name": "布鲁诺·吉马良斯", "short_name": "布鲁诺", "jersey_number": 5, "position": "CM", "team_id": "BRA", "nationality": "巴西", "birth_date": date(1997, 11, 16), "height": 182, "weight": 78, "foot": "right", "market_value": 70000000, "goals": 3, "assists": 2, "appearances": 15, "yellow_cards": 2, "red_cards": 0},
        {"id": "BRA-4", "name": "罗德里戈", "short_name": "罗德里戈", "jersey_number": 11, "position": "RW", "team_id": "BRA", "nationality": "巴西", "birth_date": date(2001, 1, 9), "height": 174, "weight": 68, "foot": "right", "market_value": 90000000, "goals": 8, "assists": 4, "appearances": 12, "yellow_cards": 1, "red_cards": 0},
        {"id": "BRA-5", "name": "维尼修斯·儒尼奥尔", "short_name": "维尼修斯", "jersey_number": 20, "position": "LW", "team_id": "BRA", "nationality": "巴西", "birth_date": date(2000, 7, 12), "height": 176, "weight": 73, "foot": "left", "market_value": 120000000, "goals": 10, "assists": 6, "appearances": 18, "yellow_cards": 3, "red_cards": 0},
        {"id": "ARG-1", "name": "埃米利亚诺·马丁内斯", "short_name": "马丁内斯", "jersey_number": 23, "position": "GK", "team_id": "ARG", "nationality": "阿根廷", "birth_date": date(1992, 9, 2), "height": 195, "weight": 93, "foot": "right", "market_value": 45000000, "goals": 0, "assists": 0, "appearances": 15, "yellow_cards": 0, "red_cards": 0},
        {"id": "ARG-2", "name": "罗德里戈·德保罗", "short_name": "德保罗", "jersey_number": 7, "position": "CM", "team_id": "ARG", "nationality": "阿根廷", "birth_date": date(1994, 5, 24), "height": 180, "weight": 76, "foot": "right", "market_value": 40000000, "goals": 2, "assists": 5, "appearances": 18, "yellow_cards": 4, "red_cards": 0},
        {"id": "ARG-3", "name": "莱昂内尔·梅西", "short_name": "梅西", "jersey_number": 10, "position": "ST", "team_id": "ARG", "nationality": "阿根廷", "birth_date": date(1987, 6, 24), "height": 169, "weight": 67, "foot": "left", "market_value": 50000000, "goals": 98, "assists": 50, "appearances": 180, "yellow_cards": 10, "red_cards": 2},
        {"id": "ARG-4", "name": "安赫尔·迪马利亚", "short_name": "迪马利亚", "jersey_number": 11, "position": "RW", "team_id": "ARG", "nationality": "阿根廷", "birth_date": date(1988, 2, 14), "height": 178, "weight": 73, "foot": "left", "market_value": 15000000, "goals": 28, "assists": 25, "appearances": 120, "yellow_cards": 5, "red_cards": 0},
        {"id": "ARG-5", "name": "胡利安·阿尔瓦雷斯", "short_name": "阿尔瓦雷斯", "jersey_number": 9, "position": "ST", "team_id": "ARG", "nationality": "阿根廷", "birth_date": date(2000, 1, 31), "height": 170, "weight": 68, "foot": "right", "market_value": 60000000, "goals": 15, "assists": 5, "appearances": 25, "yellow_cards": 1, "red_cards": 0},
    ]

    for player_data in players:
        existing = PlayerService.get_by_id(db, player_data["id"])
        if not existing:
            PlayerService.create(db, player_data)


def _add_missing_columns():
    """添加缺失的数据库列（用于增量更新）"""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    existing = {}
    for table in ("leagues", "players"):
        try:
            existing[table] = {c["name"] for c in insp.get_columns(table)}
        except Exception:
            existing[table] = set()
    stmts = []
    if "logo" not in existing.get("leagues", set()):
        stmts.append("ALTER TABLE leagues ADD COLUMN logo VARCHAR(255) NULL")
    if "parent_id" not in existing.get("leagues", set()):
        stmts.append("ALTER TABLE leagues ADD COLUMN parent_id VARCHAR(20) NULL")
    if "photo" not in existing.get("players", set()):
        stmts.append("ALTER TABLE players ADD COLUMN photo VARCHAR(255) NULL")
    if "follow_include_children" not in existing.get("user_preferences", set()):
        stmts.append("ALTER TABLE user_preferences ADD COLUMN follow_include_children BOOLEAN NULL DEFAULT 0")
    # users 表也要查：首次登录必须改密码标记，旧库（含测试缓存库）缺该列
    try:
        existing["users"] = {c["name"] for c in insp.get_columns("users")}
    except Exception:
        existing["users"] = set()
    if "must_change_password" not in existing.get("users", set()):
        stmts.append("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NULL DEFAULT 0")
    if not stmts:
        return
    with engine.begin() as conn:
        try:
            conn.execute(text("SET SESSION lock_wait_timeout = 5"))
        except Exception:
            pass
        for sql in stmts:
            try:
                conn.execute(text(sql))
            except Exception:
                pass


def _init_roles_permissions(db):
    """初始化角色和权限数据"""
    from db.models import Role, Permission, RolePermission, UserRole
    from services import UserService

    permissions = [
        # 首页
        {"name": "首页", "code": "dashboard:view", "type": "menu", "parent_id": 0, "path": "/", "icon": "🏠", "sort_order": 1, "description": "首页仪表盘"},
        # 赛事管理
        {"name": "赛事管理", "code": "match:manage", "type": "menu", "parent_id": 0, "path": "", "icon": "⚽", "sort_order": 2, "description": "赛事管理菜单"},
        {"name": "未来赛事", "code": "match:upcoming", "type": "menu", "parent_id": 2, "path": "/matches", "icon": "⚽", "sort_order": 1, "description": "未来赛事列表"},
        {"name": "历史赛事", "code": "match:finished", "type": "menu", "parent_id": 2, "path": "/finished-matches", "icon": "📊", "sort_order": 2, "description": "历史赛事列表"},
        # 竞彩足球
        {"name": "竞彩足球", "code": "jingcai:manage", "type": "menu", "parent_id": 0, "path": "", "icon": "🎫", "sort_order": 3, "description": "竞彩足球菜单"},
        {"name": "竞彩比分", "code": "match:jingcai_live", "type": "menu", "parent_id": 0, "path": "/jingcai-live", "icon": "📋", "sort_order": 0, "description": "竞彩比分列表（live.500.com/jczq.php，分析用）"},
        {"name": "比分", "code": "match:jingcai_bf", "type": "menu", "parent_id": 0, "path": "/jingcai-bf", "icon": "🎯", "sort_order": 1, "description": "竞彩比分页投注区 SP（分析用）"},
        {"name": "历史比分", "code": "match:jingcai_bf_history", "type": "menu", "parent_id": 0, "path": "/jingcai-bf-history", "icon": "🏁", "sort_order": 2, "description": "历史竞彩比分列表与赛果核对（分析用）"},
        {"name": "分析汇总", "code": "match:jingcai_bf_summary", "type": "menu", "parent_id": 0, "path": "/jingcai-bf-summary", "icon": "📈", "sort_order": 3, "description": "历史比分上月与本月已出汇总（分析用）"},
        {"name": "竞彩足球配置", "code": "jingcai:config", "type": "menu", "parent_id": 0, "path": "/jingcai-config", "icon": "⚙️", "sort_order": 4, "description": "竞彩足球推荐比分数量等分析参数"},
        # 联赛管理
        {"name": "联赛管理", "code": "league:manage", "type": "menu", "parent_id": 0, "path": "", "icon": "🏆", "sort_order": 4, "description": "联赛管理菜单"},
        {"name": "联赛列表", "code": "league:view", "type": "menu", "parent_id": 5, "path": "/leagues", "icon": "🏆", "sort_order": 1, "description": "联赛列表"},
        {"name": "联赛配置", "code": "league:config", "type": "menu", "parent_id": 5, "path": "/league-manage", "icon": "⚙️", "sort_order": 2, "description": "联赛配置管理"},
        # 模型管理
        {"name": "模型管理", "code": "model:manage", "type": "menu", "parent_id": 0, "path": "/model", "icon": "🧠", "sort_order": 5, "description": "模型版本管理"},
        # 风控体系
        {"name": "风控体系", "code": "risk:manage", "type": "menu", "parent_id": 0, "path": "/risk", "icon": "🛡️", "sort_order": 6, "description": "风险预警管理"},
        # 定时任务
        {"name": "定时任务", "code": "schedule:manage", "type": "menu", "parent_id": 0, "path": "/schedule", "icon": "⏰", "sort_order": 7, "description": "定时任务管理"},
        # 系统管理
        {"name": "系统管理", "code": "system:manage", "type": "menu", "parent_id": 0, "path": "", "icon": "⚙️", "sort_order": 8, "description": "系统管理菜单"},
        {"name": "用户管理", "code": "user:manage", "type": "menu", "parent_id": 11, "path": "/users", "icon": "👥", "sort_order": 1, "description": "用户管理"},
        {"name": "角色权限", "code": "role:manage", "type": "menu", "parent_id": 11, "path": "/permissions", "icon": "🔐", "sort_order": 2, "description": "角色权限管理"},
        # 个人中心
        {"name": "个人中心", "code": "profile:view", "type": "menu", "parent_id": 0, "path": "/profile", "icon": "👤", "sort_order": 99, "description": "个人中心"},
        # 操作权限
        {"name": "用户新增", "code": "user:create", "type": "button", "parent_id": 12, "path": "", "icon": "", "sort_order": 1, "description": "创建用户"},
        {"name": "用户编辑", "code": "user:edit", "type": "button", "parent_id": 12, "path": "", "icon": "", "sort_order": 2, "description": "编辑用户"},
        {"name": "用户删除", "code": "user:delete", "type": "button", "parent_id": 12, "path": "", "icon": "", "sort_order": 3, "description": "删除用户"},
        {"name": "角色新增", "code": "role:create", "type": "button", "parent_id": 13, "path": "", "icon": "", "sort_order": 1, "description": "创建角色"},
        {"name": "角色编辑", "code": "role:edit", "type": "button", "parent_id": 13, "path": "", "icon": "", "sort_order": 2, "description": "编辑角色"},
        {"name": "角色删除", "code": "role:delete", "type": "button", "parent_id": 13, "path": "", "icon": "", "sort_order": 3, "description": "删除角色"},
        {"name": "权限分配", "code": "role:assign", "type": "button", "parent_id": 13, "path": "", "icon": "", "sort_order": 4, "description": "分配角色权限"},
    ]

    for perm_data in permissions:
        existing = db.query(Permission).filter(Permission.code == perm_data["code"]).first()
        if not existing:
            perm = Permission(**perm_data)
            db.add(perm)
        else:
            # 同步菜单路径/名称（升级时补齐）
            for field in ("name", "path", "icon", "description", "sort_order", "type"):
                if perm_data.get(field) is not None:
                    setattr(existing, field, perm_data[field])

    db.commit()

    # 已下线菜单：过期胜平负 / 胜平负让球（数据分别由历史比分、比分页承接）
    for code in ("match:jingcai_expired", "match:jingcai"):
        retired = db.query(Permission).filter(Permission.code == code).first()
        if retired:
            db.query(RolePermission).filter(RolePermission.permission_id == retired.id).delete(synchronize_session=False)
            db.delete(retired)
            db.commit()

    # parent_id 按 code 纠偏（避免硬编码 id 漂移）
    match_manage = db.query(Permission).filter(Permission.code == "match:manage").first()
    if match_manage:
        for code in ("match:upcoming", "match:finished"):
            child = db.query(Permission).filter(Permission.code == code).first()
            if child and child.parent_id != match_manage.id:
                child.parent_id = match_manage.id
        db.commit()

    jingcai_manage = db.query(Permission).filter(Permission.code == "jingcai:manage").first()
    if jingcai_manage:
        for code in ("match:jingcai_live", "match:jingcai_bf", "match:jingcai_bf_history", "match:jingcai_bf_summary", "jingcai:config"):
            child = db.query(Permission).filter(Permission.code == code).first()
            if child and child.parent_id != jingcai_manage.id:
                child.parent_id = jingcai_manage.id
        db.commit()

    league_manage = db.query(Permission).filter(Permission.code == "league:manage").first()
    if league_manage:
        for code in ("league:view", "league:config"):
            child = db.query(Permission).filter(Permission.code == code).first()
            if child and child.parent_id != league_manage.id:
                child.parent_id = league_manage.id
        db.commit()

    system_manage = db.query(Permission).filter(Permission.code == "system:manage").first()
    if system_manage:
        for code in ("user:manage", "role:manage"):
            child = db.query(Permission).filter(Permission.code == code).first()
            if child and child.parent_id != system_manage.id:
                child.parent_id = system_manage.id
        db.commit()
        for code in ("user:create", "user:edit", "user:delete"):
            child = db.query(Permission).filter(Permission.code == code).first()
            user_manage = db.query(Permission).filter(Permission.code == "user:manage").first()
            if child and user_manage and child.parent_id != user_manage.id:
                child.parent_id = user_manage.id
        for code in ("role:create", "role:edit", "role:delete", "role:assign"):
            child = db.query(Permission).filter(Permission.code == code).first()
            role_manage = db.query(Permission).filter(Permission.code == "role:manage").first()
            if child and role_manage and child.parent_id != role_manage.id:
                child.parent_id = role_manage.id
        db.commit()

    perm_map = {p.code: p.id for p in db.query(Permission).all()}

    roles = [
        {
            "name": "超级管理员",
            "code": "super_admin",
            "description": "拥有系统所有权限",
            "is_system": True,
            "permissions": list(perm_map.values())
        },
        {
            "name": "运营管理员",
            "code": "operator",
            "description": "赛事、联赛、风控管理权限",
            "is_system": False,
            "permissions": [
                perm_map["dashboard:view"],
                perm_map["match:manage"],
                perm_map["match:upcoming"],
                perm_map["match:finished"],
                perm_map["match:jingcai_bf_history"],
                perm_map["match:jingcai_bf_summary"],
                perm_map["jingcai:config"],
                perm_map["jingcai:manage"],
                perm_map["match:jingcai_bf"],
                perm_map["match:jingcai_live"],
                perm_map["league:manage"],
                perm_map["league:view"],
                perm_map["league:config"],
                perm_map["risk:manage"],
                perm_map["profile:view"]
            ]
        },
        {
            "name": "数据分析师",
            "code": "analyst",
            "description": "查看赛事、模型数据",
            "is_system": False,
            "permissions": [
                perm_map["dashboard:view"],
                perm_map["match:manage"],
                perm_map["match:upcoming"],
                perm_map["match:finished"],
                perm_map["match:jingcai_bf_history"],
                perm_map["match:jingcai_bf_summary"],
                perm_map["jingcai:config"],
                perm_map["jingcai:manage"],
                perm_map["match:jingcai_bf"],
                perm_map["match:jingcai_live"],
                perm_map["league:view"],
                perm_map["model:manage"],
                perm_map["profile:view"]
            ]
        },
        {
            "name": "普通用户",
            "code": "user",
            "description": "仅查看赛事和个人中心",
            "is_system": False,
            "permissions": [
                perm_map["dashboard:view"],
                perm_map["match:upcoming"],
                perm_map["match:finished"],
                perm_map["match:jingcai_bf_history"],
                perm_map["match:jingcai_bf_summary"],
                perm_map["jingcai:config"],
                perm_map["jingcai:manage"],
                perm_map["match:jingcai_bf"],
                perm_map["match:jingcai_live"],
                perm_map["league:view"],
                perm_map["profile:view"]
            ]
        }
    ]

    for role_data in roles:
        existing = db.query(Role).filter(Role.code == role_data["code"]).first()
        if not existing:
            role = Role(
                name=role_data["name"],
                code=role_data["code"],
                description=role_data["description"],
                is_system=role_data["is_system"]
            )
            db.add(role)
            db.flush()

            for pid in role_data["permissions"]:
                if not pid:
                    continue
                rp = RolePermission(role_id=role.id, permission_id=pid)
                db.add(rp)
        else:
            # 已有角色：补齐缺失权限（不删旧权限）
            have = {
                r.permission_id
                for r in db.query(RolePermission).filter(RolePermission.role_id == existing.id).all()
            }
            want = set(pid for pid in role_data["permissions"] if pid)
            if role_data["code"] == "super_admin":
                want |= set(perm_map.values())
            for pid in want:
                if pid not in have:
                    db.add(RolePermission(role_id=existing.id, permission_id=pid))
                    have.add(pid)

    db.commit()

    # 给超级管理员分配 super_admin 角色
    admin = UserService.get_by_username(db, SUPER_ADMIN["username"])
    if admin:
        admin_role = db.query(Role).filter(Role.code == "super_admin").first()
        if admin_role:
            existing_ur = db.query(UserRole).filter(
                UserRole.user_id == admin.id,
                UserRole.role_id == admin_role.id
            ).first()
            if not existing_ur:
                ur = UserRole(user_id=admin.id, role_id=admin_role.id)
                db.add(ur)
                db.commit()


def _init_subscription_plans(db):
    """订阅套餐种子 + 历史 plan 值迁移"""
    from services.subscription_service import seed_subscription_plans, migrate_legacy_plans
    seed_subscription_plans(db)
    migrate_legacy_plans(db)


if __name__ == "__main__":
    init_database()
