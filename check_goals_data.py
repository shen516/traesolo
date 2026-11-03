import requests

url = 'https://raw.githubusercontent.com/openfootball/world-cup.json/master/2026/worldcup.json'
r = requests.get(url)
data = r.json()

matches = data.get('matches', [])
print(f"Total matches with goals data:")

goal_count = 0
for m in matches[:5]:
    goals1 = m.get('goals1', [])
    goals2 = m.get('goals2', [])
    print(f"{m['team1']} vs {m['team2']} - goals1: {len(goals1)}, goals2: {len(goals2)}")
    if goals1:
        print(f"  goals1 sample: {goals1[:2]}")
    if goals2:
        print(f"  goals2 sample: {goals2[:2]}")
    goal_count += len(goals1) + len(goals2)

print(f"\nTotal goals across all matches: {goal_count}")
