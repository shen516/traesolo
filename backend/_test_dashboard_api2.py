import requests

apis = [
    ('首页', 'http://localhost:8000/'),
    ('赛事', 'http://localhost:8000/api/v1/matches/upcoming?page_size=5'),
    ('趋势', 'http://localhost:8000/api/v1/trend/recent/30'),
    ('积分榜', 'http://localhost:8000/api/v1/standings/league/EPL?season=2026-2027'),
    ('射手榜', 'http://localhost:8000/api/v1/scorers/league/EPL?season=2026-2027'),
    ('风险', 'http://localhost:8000/api/v1/risk'),
    ('联赛', 'http://localhost:8000/api/v1/leagues?page_size=5'),
    ('球队', 'http://localhost:8000/api/v1/teams?page_size=5'),
]

print("=== 测试Dashboard相关API ===")
for name, url in apis:
    try:
        r = requests.get(url, timeout=10)
        status = r.status_code
        if status == 200:
            data = r.json()
            if isinstance(data, dict):
                keys = list(data.keys())
                print(f"✅ {name}: {status} - 键: {keys}")
            else:
                print(f"✅ {name}: {status} - 数据长度: {len(data)}")
        else:
            print(f"❌ {name}: {status}")
    except Exception as e:
        print(f"❌ {name}: {e}")
