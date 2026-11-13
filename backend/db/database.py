"""数据库连接配置和会话管理"""
import logging
import os
import re
from pathlib import Path

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

db_config = config.get("database", {})

DATABASE_URL = os.environ.get("DATABASE_URL") or db_config.get(
    "url",
    "sqlite:///./backend/data/football.db",
)

connect_args = {}
engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}
else:
    connect_args = {"charset": "utf8mb4"}
    engine_kwargs["pool_size"] = int(os.environ.get("DB_POOL_SIZE", "10"))
    engine_kwargs["max_overflow"] = int(os.environ.get("DB_MAX_OVERFLOW", "20"))

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# matches.stage 目标 ENUM（与 db.models.Match.stage 保持一致）
MATCH_STAGE_ENUM = (
    "group",
    "round_of_16",
    "quarter_final",
    "semi_final",
    "third_place",
    "final",
    "league",
    "qualifying",
    "knockout",
    "playoff",
    "play_in",
)

_SCHEMA_ENSURED = False


def _is_mysql() -> bool:
    return "mysql" in (DATABASE_URL or "").lower()


def _parse_mysql_enum_values(column_type: str) -> set:
    """从 COLUMN_TYPE（如 enum('a','b')）解析枚举值集合。"""
    if not column_type:
        return set()
    inner = re.search(r"enum\((.*)\)", column_type, re.I)
    if not inner:
        return set()
    return {m.group(1) for m in re.finditer(r"'((?:\\'|[^'])*)'", inner.group(1))}


def ensure_schema(force: bool = False):
    """为已有表补齐新增列 / ENUM（create_all 不会 ALTER）。

    重要：不要每次无条件 MODIFY ENUM。无条件 ALTER 会与采集长事务争用
    matches 表元数据锁，导致全库查询排队（API/训练全部卡住）。
    """
    global _SCHEMA_ENSURED
    if _SCHEMA_ENSURED and not force:
        return

    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    # 一次拉齐各表列名，后续缺失列比对走内存，避免逐表重复 inspect round-trip
    columns_by_table = {
        t: {c["name"] for c in inspector.get_columns(t)}
        for t in tables
    }

    def _add_columns(table: str, columns: dict):
        if table not in tables:
            return
        existing = columns_by_table.get(table) or set()
        missing = {n: t for n, t in columns.items() if n not in existing}
        if not missing:
            return
        with engine.begin() as conn:
            if _is_mysql():
                conn.execute(text("SET SESSION lock_wait_timeout = 5"))
            for name, typedef in missing.items():
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {typedef}"))
                    existing.add(name)
                    logger.info("Schema: added %s.%s", table, name)
                except Exception as e:
                    logger.warning("Schema: add %s.%s skipped: %s", table, name, e)
        columns_by_table[table] = existing

    _add_columns("odds_snapshots", {
        "odds_bf_json": "TEXT NULL",
        "odds_hspf_win": "DECIMAL(6,2) NULL",
        "odds_hspf_draw": "DECIMAL(6,2) NULL",
        "odds_hspf_lose": "DECIMAL(6,2) NULL",
        "odds_hh_json": "TEXT NULL",
    })
    _add_columns("matches", {
        "fixture_id": "VARCHAR(30) NULL",
        "process_id": "VARCHAR(30) NULL",
        "handicap": "INT NULL",
        "odds_nspf_win": "DECIMAL(6,2) NULL",
        "odds_nspf_draw": "DECIMAL(6,2) NULL",
        "odds_nspf_lose": "DECIMAL(6,2) NULL",
        "odds_spf_win": "DECIMAL(6,2) NULL",
        "odds_spf_draw": "DECIMAL(6,2) NULL",
        "odds_spf_lose": "DECIMAL(6,2) NULL",
        "odds_bf_json": "TEXT NULL",
        "odds_hspf_win": "DECIMAL(6,2) NULL",
        "odds_hspf_draw": "DECIMAL(6,2) NULL",
        "odds_hspf_lose": "DECIMAL(6,2) NULL",
        "odds_hh_json": "TEXT NULL",
        "is_single": "BOOLEAN NULL DEFAULT 0",
        "buy_end_time": "VARCHAR(30) NULL",
        "half_score": "VARCHAR(10) NULL",
        "match_no": "VARCHAR(20) NULL",
        "source": "VARCHAR(20) NULL",
        "handicap_line": "VARCHAR(30) NULL",
    })
    _add_columns("teams", {
        "xg_for": "DECIMAL(5,3) NULL DEFAULT 1.350",
        "xg_against": "DECIMAL(5,3) NULL DEFAULT 1.350",
    })
    _add_columns("match_predictions", {
        "meta_json": "TEXT NULL",
    })
    _add_columns("crawl_logs", {
        "log_file": "VARCHAR(500) NULL",
    })
    _add_columns("leagues", {
        "parent_id": "VARCHAR(20) NULL",
    })
    _add_columns("user_preferences", {
        "follow_include_children": "BOOLEAN NULL DEFAULT 0",
    })
    # DEFAULT 0：避免生产存量账号因列迁移成 NULL 而被误判为"必须改密"
    _add_columns("users", {
        "must_change_password": "BOOLEAN NULL DEFAULT 0",
    })
    # 串关组合：同 combination_id 多行共享；NULL = 单关（兼容既有行）
    _add_columns("simulation_bets", {
        "combination_id": "VARCHAR(40) NULL",
        "is_parlay": "BOOLEAN NULL DEFAULT 0",
    })

    _ensure_match_stage_enum(tables)
    _ensure_simulation_bet_play_type_enum(tables)
    _backfill_league_parents_if_needed(tables)
    _ensure_performance_indexes(tables)
    _activate_priority_leagues(tables)

    _SCHEMA_ENSURED = True


def _activate_priority_leagues(tables: set):
    """已有库激活 P2/P3 扩围联赛，并补齐 500 source_url；缺失行则插入。"""
    if "leagues" not in tables:
        return
    try:
        from services.real_team_crawler import (
            CANONICAL_FIVE00_URL,
            get_extended_leagues,
            get_p3_dual_leagues,
            get_priority_leagues,
        )
        activate_ids = list(dict.fromkeys([
            *get_priority_leagues(),
            *get_extended_leagues(),
            *get_p3_dual_leagues(),
        ]))
        # 新联赛元数据（仅当表中尚无该 id 时插入）
        seed_rows = {
            "ECH": {
                "name": "英冠联赛",
                "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
                "region": "欧洲",
                "level": 2,
                "avg_goals": 2.55,
            },
        }
        with engine.begin() as conn:
            if _is_mysql():
                conn.execute(text("SET SESSION lock_wait_timeout = 5"))
            for lid in activate_ids:
                url = CANONICAL_FIVE00_URL.get(lid) or ""
                meta = seed_rows.get(lid)
                if meta:
                    exists = conn.execute(
                        text("SELECT 1 FROM leagues WHERE id = :lid LIMIT 1"),
                        {"lid": lid},
                    ).fetchone()
                    if not exists:
                        conn.execute(
                            text(
                                "INSERT INTO leagues "
                                "(id, name, icon, region, level, avg_goals, is_active, source_url) "
                                "VALUES (:id, :name, :icon, :region, :level, :avg_goals, 1, :source_url)"
                            ),
                            {
                                "id": lid,
                                "name": meta["name"],
                                "icon": meta["icon"],
                                "region": meta["region"],
                                "level": meta["level"],
                                "avg_goals": meta["avg_goals"],
                                "source_url": url or None,
                            },
                        )
                conn.execute(
                    text(
                        "UPDATE leagues SET is_active = 1 "
                        "WHERE id = :lid AND (is_active = 0 OR is_active IS NULL)"
                    ),
                    {"lid": lid},
                )
                if url:
                    # 赛季页会换 ID：英冠等需强制对齐到当前 CANONICAL
                    if lid == "ECH":
                        conn.execute(
                            text(
                                "UPDATE leagues SET source_url = :url WHERE id = :lid "
                                "AND (source_url IS NULL OR source_url = '' OR source_url <> :url)"
                            ),
                            {"url": url, "lid": lid},
                        )
                    else:
                        conn.execute(
                            text(
                                "UPDATE leagues SET source_url = :url "
                                "WHERE id = :lid AND (source_url IS NULL OR source_url = '')"
                            ),
                            {"url": url, "lid": lid},
                        )
    except Exception as e:
        logger.warning("Schema: activate extended leagues skipped: %s", e)


def _ensure_performance_indexes(tables: set):
    """补齐高频查询索引（幂等）。"""
    if not tables:
        return
    indexes = [
        ("matches", "idx_matches_status_date_league", "status, match_date, league_id"),
        ("match_predictions", "idx_predictions_match_created", "match_id, created_at"),
        ("leagues", "idx_leagues_parent_id", "parent_id"),
        ("simulation_bets", "idx_sim_bet_combination", "user_id, combination_id"),
    ]
    from sqlalchemy import inspect

    inspector = inspect(engine)
    with engine.begin() as conn:
        if _is_mysql():
            conn.execute(text("SET SESSION lock_wait_timeout = 5"))
        for table, idx_name, columns in indexes:
            if table not in tables:
                continue
            existing = {i["name"] for i in inspector.get_indexes(table)}
            if idx_name in existing:
                continue
            try:
                conn.execute(text(f"CREATE INDEX {idx_name} ON {table} ({columns})"))
                logger.info("Schema: created index %s on %s", idx_name, table)
            except Exception as e:
                logger.warning("Schema: index %s skipped: %s", idx_name, e)


def _backfill_league_parents_if_needed(tables: set):
    """补齐联赛 parent_id（幂等，仅处理未设置的次级联赛）。"""
    if "leagues" not in tables:
        return
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("leagues")}
        if "parent_id" not in cols:
            return
        from services.league_parent import backfill_league_parents
        db = SessionLocal()
        try:
            n = backfill_league_parents(db)
            if n:
                logger.info("Schema: backfilled parent_id for %s leagues", n)
        finally:
            db.close()
    except Exception as e:
        logger.warning("Schema: league parent backfill deferred: %s", e)


def _ensure_match_stage_enum(tables: set):
    """仅当缺少 playoff/play_in 等值时才 ALTER matches.stage。"""
    if "matches" not in tables or not _is_mysql():
        return

    needed = set(MATCH_STAGE_ENUM)
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'matches' AND COLUMN_NAME = 'stage'"
            )).fetchone()
        current = _parse_mysql_enum_values(row[0] if row else "")
        missing = needed - current
        if not missing:
            logger.debug("Schema: matches.stage ENUM already up to date")
            return

        enum_sql = ",".join(f"'{v}'" for v in MATCH_STAGE_ENUM)
        with engine.begin() as conn:
            # 短等待：拿不到锁就放弃，避免堵死全库
            conn.execute(text("SET SESSION lock_wait_timeout = 5"))
            conn.execute(text(
                "ALTER TABLE matches MODIFY COLUMN stage "
                f"ENUM({enum_sql}) DEFAULT 'league'"
            ))
        logger.info(
            "Schema: updated matches.stage ENUM (added %s)",
            ",".join(sorted(missing)),
        )
    except Exception as e:
        # 常见：Lock wait timeout — 采集占用 matches 时不硬等
        logger.warning(
            "Schema: matches.stage ENUM update deferred (will retry next boot): %s",
            e,
        )


# simulation_bets.play_type 目标 ENUM（与 db.models.SimulationBet.play_type 一致）
SIMULATION_BET_PLAY_TYPE_ENUM = (
    "spf",
    "nspf",
    "bf",
    "tg",
    "hspf",
)


def _ensure_simulation_bet_play_type_enum(tables: set):
    """仅当缺少 hspf 值时才 ALTER simulation_bets.play_type。"""
    if "simulation_bets" not in tables or not _is_mysql():
        return

    needed = set(SIMULATION_BET_PLAY_TYPE_ENUM)
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'simulation_bets' AND COLUMN_NAME = 'play_type'"
            )).fetchone()
        current = _parse_mysql_enum_values(row[0] if row else "")
        missing = needed - current
        if not missing:
            logger.debug("Schema: simulation_bets.play_type ENUM already up to date")
            return

        enum_sql = ",".join(f"'{v}'" for v in SIMULATION_BET_PLAY_TYPE_ENUM)
        with engine.begin() as conn:
            conn.execute(text("SET SESSION lock_wait_timeout = 5"))
            conn.execute(text(
                "ALTER TABLE simulation_bets MODIFY COLUMN play_type "
                f"ENUM({enum_sql}) NOT NULL"
            ))
        logger.info(
            "Schema: updated simulation_bets.play_type ENUM (added %s)",
            ",".join(sorted(missing)),
        )
    except Exception as e:
        logger.warning(
            "Schema: simulation_bets.play_type ENUM update deferred "
            "(will retry next boot): %s",
            e,
        )


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
