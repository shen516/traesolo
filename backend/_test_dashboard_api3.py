import requests

print("=== 检查teamApi.getAll()返回结构 ===")
url = 'http://localhost:8000/api/v1/teams'
r = requests.get(url, timeout=10)
data = r.json()
print(f"状态码: {r.status_code}")
print(f"数据类型: {type(data)}")
print(f"键: {list(data.keys()) if isinstance(data, dict) else '数组'}")
if isinstance(data, dict):
    if 'teams' in data:
        print(f"teams数组长度: {len(data['teams'])}")
        if data['teams']:
            print(f"第一个球队: {data['teams'][0]}")

print("\n=== 检查leagueApi.getAll()返回结构 ===")
url = 'http://localhost:8000/api/v1/leagues?page_size=2000'
r = requests.get(url, timeout=10)
data = r.json()
print(f"状态码: {r.status_code}")
print(f"数据类型: {type(data)}")
print(f"键: {list(data.keys())}")
if 'leagues' in data:
    print(f"leagues数组长度: {len(data['leagues'])}")
    if data['leagues']:
        print(f"第一个联赛: {data['leagues'][0]}")

print("\n=== 检查matchApi.getUpcoming({page_size:5})返回结构 ===")
url = 'http://localhost:8000/api/v1/matches/upcoming?page_size=5'
r = requests.get(url, timeout=10)
data = r.json()
print(f"状态码: {r.status_code}")
print(f"数据类型: {type(data)}")
print(f"键: {list(data.keys())}")
if 'matches' in data:
    print(f"matches数组长度: {len(data['matches'])}")
    if data['matches']:
        print(f"第一个赛事: {data['matches'][0]}")
