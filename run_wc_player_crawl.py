import requests

r = requests.post('http://localhost:8000/api/v1/crawler/players/run?league_id=WC')
print(r.status_code)
print(r.json())
