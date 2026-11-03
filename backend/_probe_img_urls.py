import requests

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://liansai.500.com/"})

candidates = [
    "https://liansai.500.com/static/soccerdata/images/TeamPic/teamsignnew_554.png",
    "https://liansai.500.com/static/soccerdata/images/CharacterPic/characterpic1_50025.png",
    "https://liansai.500.com/static/soccerdata/images/CharacterPic/characterpic1_10.png",
    "https://liansai.500.com/static/soccerdata/images/LeaguePic/19906.png",
    "https://liansai.500.com/static/soccerdata/images/LeaguePic/league_19906.png",
    "https://odds.500.com/static/soccerdata/images/LeaguePic/19906.png",
    "https://odds.500.com/static/soccerdata/images/LeaguePic/19906.gif",
    "https://liansai.500.com/static/soccerdata/images/LeaguePic/leaguesignnew_19906.png",
    "https://www.500cache.com/liansai/images/league/19906.png",
    "https://liansai.500.com/static/images/league/19906.png",
    "https://odds.500.com/static/soccerdata/images/TeamPic/teamsignnew_554.png",
]

for url in candidates:
    try:
        r = s.head(url, timeout=10, allow_redirects=True)
        ct = r.headers.get("content-type", "")
        cl = r.headers.get("content-length", "")
        print(r.status_code, ct, cl, url[-70:])
        if r.status_code == 405:
            r2 = s.get(url, timeout=10, stream=True)
            print("  GET", r2.status_code, r2.headers.get("content-type"), r2.headers.get("content-length"))
            r2.close()
    except Exception as e:
        print("ERR", url[-50:], e)
