"""hspf odds + parlay combination fields

Revision ID: 002_hspf_parlay
Revises: 001_perf_indexes
Create Date: 2026-11-12

半场胜平负（hspf）真实 SP 采集与串关落单（parlay）所需 schema：

- matches / odds_snapshots 各加 4 字段（odds_bf_json、odds_hspf_win/draw/lose、
  odds_hh_json），半场三选一由半全场 9 项边际推导。
- simulation_bets 加 combination_id / is_parlay，串关同组合多行共享。
- simulation_bets.play_type ENUM 扩 hspf（仅 MySQL；SQLite 为 TEXT 兼容）。

本迁移幂等：已通过 ensure_schema 补齐的列/索引自动跳过。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_hspf_parlay"
down_revision: Union[str, None] = "001_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        rows = bind.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r[1] == name for r in rows)
    rows = bind.execute(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (table, name),
    ).scalar()
    return bool(rows)


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        rows = bind.execute(
            f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='{table}'"
        ).fetchall()
        return any(r[0] == name for r in rows)
    rows = bind.execute(
        """
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s
        """,
        (table, name),
    ).scalar()
    return bool(rows)


# (table, column, typedef)
_ADD_COLUMNS = [
    ("matches", "odds_bf_json", sa.Text()),
    ("matches", "odds_hspf_win", sa.DECIMAL(6, 2)),
    ("matches", "odds_hspf_draw", sa.DECIMAL(6, 2)),
    ("matches", "odds_hspf_lose", sa.DECIMAL(6, 2)),
    ("matches", "odds_hh_json", sa.Text()),
    ("odds_snapshots", "odds_bf_json", sa.Text()),
    ("odds_snapshots", "odds_hspf_win", sa.DECIMAL(6, 2)),
    ("odds_snapshots", "odds_hspf_draw", sa.DECIMAL(6, 2)),
    ("odds_snapshots", "odds_hspf_lose", sa.DECIMAL(6, 2)),
    ("odds_snapshots", "odds_hh_json", sa.Text()),
    ("simulation_bets", "combination_id", sa.String(40)),
    ("simulation_bets", "is_parlay", sa.Boolean()),
]

PLAY_TYPE_ENUM = ("spf", "nspf", "bf", "tg", "hspf")


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, type_ in _ADD_COLUMNS:
        if not _column_exists(table, column):
            op.add_column(table, sa.Column(column, type_, nullable=True))

    if not _index_exists("simulation_bets", "idx_sim_bet_combination"):
        op.create_index(
            "idx_sim_bet_combination",
            "simulation_bets",
            ["user_id", "combination_id"],
            unique=False,
        )

    if bind.dialect.name == "mysql":
        # 扩 ENUM：仅当缺 hspf 时 MODIFY，避免与采集长事务争用元数据锁
        row = bind.execute(
            """
            SELECT COLUMN_TYPE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'simulation_bets' AND COLUMN_NAME = 'play_type'
            """
        ).fetchone()
        current = row[0] if row else ""
        if "hspf" not in current:
            enum_sql = ",".join(f"'{v}'" for v in PLAY_TYPE_ENUM)
            op.execute(f"ALTER TABLE simulation_bets MODIFY COLUMN play_type ENUM({enum_sql}) NOT NULL")


def downgrade() -> None:
    op.drop_index("idx_sim_bet_combination", table_name="simulation_bets")
    for table, column, _ in reversed(_ADD_COLUMNS):
        if _column_exists(table, column):
            op.drop_column(table, column)
