import requests

headers = {
    'Origin': 'http://localhost:5173',
    'Referer': 'http://localhost:5173/'
}

try:
    r = requests.get('http://localhost:8000/api/v1/crawler/status', headers=headers, timeout=5)
    print(f'Status: {r.status_code}')
    print(f'Headers: {dict(r.headers)}')
    print(f'Content: {r.text}')
except Exception as e:
    print(f'Error: {e}')
