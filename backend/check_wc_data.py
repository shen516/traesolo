from db.database import get_db
from db.models import Match, League, Team

db = next(get_db())

wc_matches = db.query(Match).filter(Match.league_id == 'WC').order_by(Match.match_date, Match.match_time).all()
print(f"世界杯赛事总数: {len(wc_matches)}")
print("\n--- 所有世界杯赛事 ---")
for m in wc_matches:
    home_team = db.query(Team).filter(Team.id == m.home_team_id).first()
    away_team = db.query(Team).filter(Team.id == m.away_team_id).first()
    status = {'upcoming': '未开始', 'live': '进行中', 'finished': '已结束'}[m.status]
    print(f"  [{m.match_date} {m.match_time}] {home_team.name if home_team else m.home_team_id} VS {away_team.name if away_team else m.away_team_id}")
    print(f"      阶段: {m.round_name} ({m.stage}), 状态: {status}, 比分: {m.home_goals}-{m.away_goals}")
