from sqlalchemy import create_engine, text

engine = create_engine('sqlite:///e:/fuye/traesolo/backend/data/football.db')
with engine.connect() as conn:
    conn.execute(text('DELETE FROM match_player_stats WHERE player_id IN (SELECT id FROM players WHERE team_id IN (SELECT id FROM teams WHERE league_id = "WC"))'))
    conn.execute(text('DELETE FROM players WHERE team_id IN (SELECT id FROM teams WHERE league_id = "WC")'))
    conn.commit()
    print('Cleaned WC players')
