import re
import requests
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Accept-Language": "zh-CN,zh;q=0.9",
})

urls = [
    ("league", "https://liansai.500.com/zuqiu-19906/"),
    ("team", "https://liansai.500.com/team/554/"),
    ("player", "https://liansai.500.com/player/554-50025/"),
    ("lineup", "https://liansai.500.com/team/554/teamlineup/"),
]

out = []
for label, url in urls:
    r = s.get(url, timeout=20)
    text = r.content.decode("gbk", "replace")
    soup = BeautifulSoup(text, "html.parser")
    imgs = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        alt = img.get("alt") or img.get("title") or ""
        if any(k in src.lower() for k in ["logo", "team", "player", "qiuy", "photo", "head", "flag", "league", "liansai", "soccer", ".png", ".jpg", ".gif", ".webp"]):
            imgs.append((src, alt, img.get("class")))
        elif src and "avatar" in src.lower():
            imgs.append((src, alt, img.get("class")))
    all_src = [img.get("src") or img.get("data-src") for img in soup.find_all("img")]
    out.append(f"===== {label} {url} status={r.status_code} imgs={len(all_src)} =====")
    for src in all_src[:40]:
        out.append(f"  {src}")
    # css background images
    for m in re.finditer(r"url\((['\"]?)([^)'\"]+)\1\)", text):
        u = m.group(2)
        if any(x in u.lower() for x in [".png", ".jpg", ".gif", "logo", "team", "player"]):
            out.append(f"  css {u[:120]}")

open("_imgs.txt", "w", encoding="utf-8").write("\n".join(out))
print("wrote", len(out), "lines")
