"""baseline schema indexes (matches / match_predictions)

Revision ID: 001_perf_indexes
Revises:
Create Date: 2026-09-02

现有库若已通过 ensure_schema 建索引，本迁移幂等跳过。
新环境请配合 create_all / init_db 使用；后续 schema 变更请用 alembic revision --autogenerate。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "001_perf_indexes"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def upgrade() -> None:
    if not _index_exists("matches", "idx_matches_status_date_league"):
        op.create_index(
            "idx_matches_status_date_league",
            "matches",
            ["status", "match_date", "league_id"],
            unique=False,
        )
    if not _index_exists("match_predictions", "idx_predictions_match_created"):
        op.create_index(
            "idx_predictions_match_created",
            "match_predictions",
            ["match_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("idx_predictions_match_created", table_name="match_predictions")
    op.drop_index("idx_matches_status_date_league", table_name="matches")
