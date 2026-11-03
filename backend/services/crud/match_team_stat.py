from services.crud._common import *


class MatchTeamStatService:
    @staticmethod
    def get_by_match(db: Session, match_id: str):
        return (
            db.query(MatchTeamStat)
            .filter(MatchTeamStat.match_id == match_id)
            .order_by(MatchTeamStat.is_home.desc())
            .all()
        )

    @staticmethod
    def upsert_for_match(db: Session, match_id: str, rows: list) -> int:
        """按 match_id+team_id 覆盖写入球队技术统计。"""
        if not rows:
            return 0
        saved = 0
        for raw in rows:
            team_id = raw.get("team_id")
            if not team_id:
                continue
            existing = (
                db.query(MatchTeamStat)
                .filter(MatchTeamStat.match_id == match_id, MatchTeamStat.team_id == team_id)
                .first()
            )
            payload = {
                "is_home": bool(raw.get("is_home")),
                "shots": int(raw.get("shots") or 0),
                "shots_on_target": int(raw.get("shots_on_target") or 0),
                "possession": raw.get("possession"),
                "corners": raw.get("corners"),
                "source": (raw.get("source") or "unknown")[:20],
            }
            if existing:
                for k, v in payload.items():
                    setattr(existing, k, v)
            else:
                db.add(MatchTeamStat(match_id=match_id, team_id=team_id, **payload))
            saved += 1
        db.commit()
        return saved

    @staticmethod
    def delete_by_match(db: Session, match_id: str):
        db.query(MatchTeamStat).filter(MatchTeamStat.match_id == match_id).delete()
        db.commit()
