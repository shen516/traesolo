import requests

headers = {
    'Content-Type': 'application/json'
}

try:
    r = requests.get('http://localhost:8000/api/v1/crawler/logs/stats', headers=headers, timeout=5)
    print(f'Status: {r.status_code}')
    print(f'Headers: {dict(r.headers)}')
    print(f'Content: {r.text}')
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')
