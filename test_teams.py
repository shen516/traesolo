import requests

print('=== 查看英格兰球员 ===')
r = requests.get('http://localhost:8000/api/v1/players?team=ENG')
players = r.json().get('players', [])
print(f'英格兰球员数量: {len(players)}')
if players:
    for p in players[:5]:
        print(f"  {p['name']} - team_id: {p.get('team_id')}")

print('\n=== 查看阿根廷球员 ===')
r2 = requests.get('http://localhost:8000/api/v1/players?team=ARG')
players2 = r2.json().get('players', [])
print(f'阿根廷球员数量: {len(players2)}')
if players2:
    for p in players2[:5]:
        print(f"  {p['name']} - team_id: {p.get('team_id')}")

print('\n=== 查看球员的team_id分布 ===')
r3 = requests.get('http://localhost:8000/api/v1/players?league=WC')
all_players = r3.json().get('players', [])
team_counts = {}
for p in all_players:
    tid = p.get('team_id', 'unknown')
    team_counts[tid] = team_counts.get(tid, 0) + 1

print('球员按team_id分布:')
for tid, cnt in sorted(team_counts.items(), key=lambda x: -x[1]):
    print(f'  {tid}: {cnt} 名球员')