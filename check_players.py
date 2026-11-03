import requests

r = requests.get('http://localhost:8000/api/v1/players?league_id=WC&limit=50')
data = r.json()
players = data.get('players', [])

print(f'Total WC players: {len(players)}')
print('\nFirst 10 players:')
for p in players[:10]:
    print(f"{p['id']} {p['name']} team={p['team_id']} goals={p.get('goals', 0)} assists={p.get('assists', 0)}")

team_counts = {}
for p in players:
    team = p['team_id']
    team_counts[team] = team_counts.get(team, 0) + 1

print(f'\nPlayers per team:')
for team, count in sorted(team_counts.items(), key=lambda x: -x[1])[:10]:
    print(f'{team}: {count} players')
