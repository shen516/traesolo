import re
import requests
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://liansai.500.com/"})

r = s.get("https://liansai.500.com/zuqiu-19906/", timeout=20)
text = r.content.decode("gbk", "replace")
soup = BeautifulSoup(text, "html.parser")
# any img
print("all img:")
for img in soup.find_all("img"):
    print(" ", img.get("src"), img.get("class"), img.get("id"))

print("png/jpg/gif in html:")
for m in re.finditer(r"https?:[^\"'\s>]+\.(?:png|jpg|gif|webp)", text, re.I):
    u = m.group(0)
    if "500logo" not in u and "ghs.png" not in u:
        print(" ", u[:150])
for m in re.finditer(r"//[^\"'\s>]+\.(?:png|jpg|gif|webp)", text, re.I):
    u = m.group(0)
    if "500logo" not in u and "ghs" not in u:
        print(" ", u[:150])

print("\npublic crests:")
for url in [
    "https://crests.football-data.org/PL.png",
    "https://crests.football-data.org/PD.png",
    "https://crests.football-data.org/BL1.png",
    "https://media.api-sports.io/football/leagues/39.png",
    "https://media.api-sports.io/football/teams/42.png",
]:
    rr = s.get(url, timeout=10)
    print(rr.status_code, rr.headers.get("content-type"), rr.headers.get("content-length"), url)
