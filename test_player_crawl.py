import requests
import re
import json
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

session = requests.Session()
session.headers.update(headers)

print("=== 查看500.com球队页面所有表格 ===")
try:
    url = 'https://liansai.500.com/team/16/'
    r = session.get(url, timeout=30)
    text = r.content.decode('gbk', errors='replace')
    soup = BeautifulSoup(text, 'html.parser')
    
    tables = soup.find_all('table')
    print(f"找到表格数量: {len(tables)}")
    
    for i, table in enumerate(tables):
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
        
        first_row = [c.text.strip() for c in rows[0].find_all(['td', 'th'])]
        print(f"\n表格 {i}: {first_row}")
        
        if len(rows) > 1:
            for row in rows[1:][:3]:
                cells = [c.text.strip() for c in row.find_all(['td', 'th'])]
                print(f"  {cells}")

except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()