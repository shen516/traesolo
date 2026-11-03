"""live.500.com/jczq.php 竞彩比分采集器：行解析与定时任务注册。"""

from datetime import date

from services.live_jingcai_crawler import LiveJingcaiCrawler
from services.scheduled_tasks import get_task_definitions

# 真实页面结构（抓取自 live.500.com/jczq.php，2026-10-28）
# - 14 列：场次/赛事/轮次/时间/状态/主队/比分/客队/半场/胜负奖金/胜负/直播/分析/置顶
# - <tr> 属性：fid / status（0=未开赛, 1=完赛）/ lid / gy / yy
# - liveOddsList = {fid: {'sp':[w,d,l], 'rqsp':[w,d,l], '0':[w,d,l]}}
MOCK_HTML = """
<html><body>
<script>
var liveOddsList = {"1473930":{"3":["1.65","3.80","4.10"],"5":["1.62","3.92","4.00"],"0":["1.65","3.84","4.44"],"sp":["1.57","3.98","4.15"],"rqsp":["2.74","3.55","2.07"]}};
</script>
<table width="100%" cellspacing="0" cellpadding="0" class="bf_tablelist01" id="table_match">
  <thead>
  <tr>
    <td width="80" align="center" class="td_title01">场次</td>
    <td width="70" align="center" class="td_title01">赛事</td>
    <td width="70" align="center" class="td_title01">轮次</td>
    <td width="90" align="center" class="td_title01">比赛时间</td>
    <td width="40" align="center" class="td_title01">状态</td>
    <td width="150" align="center" class="td_title01">主队</td>
    <td width="120" align="center" class="td_title01">比分</td>
    <td width="150" align="center" class="td_title01">客队</td>
    <td width="60" align="center" class="td_title01">半场</td>
    <td width="130" align="center" class="td_title01">胜负奖金</td>
    <td width="60" align="center" class="td_title01">胜负</td>
    <td align="center" class="td_title01">直播</td>
    <td align="center" class="td_title01">分析</td>
    <td width="40" align="center" class="td_title01">置顶</td>
  </tr>
  </thead>
  <tbody>
  <!-- 未开赛：有让球 + SP -->
  <tr id="a1473930" order="3001" status="0" gy="亚冠杯,大阪钢巴,布里兰" yy="亚冠杯,大阪飛腳,武里南聯" lid="170" fid="1473930" sid="19899" class="" infoid="166382" r="1">
    <td align="center" class=""><input type="checkbox" name="check_id[]" value="1473930" />周三001</td>
    <td bgcolor="#00A78D" class="ssbox_01"><a style="color:#fff" target="_blank" href="//liansai.500.com/zuqiu-19899/">亚冠杯</a></td>
    <td align="center">第3轮</td>
    <td align="center">10-28 18:00</td>
    <td align="center">未</td>
    <td align="right" class="p_lr01"><span class="gray">[05]</span><a target="_blank" href="//liansai.500.com/team/752/">大阪钢巴</a><span class="sp_rq">(-1)</span></td>
    <td align="center"><div class="pk"><a href="./detail.php?fid=1473930&r=1" target="_blank" class="clt1" ></a><a href="./detail.php?fid=1473930&r=1" target="_blank" class="fgreen" data-ao="半球/一球" data-pb="半球/一球">半球/一球</a><a href="./detail.php?fid=1473930&r=1" target="_blank" class="clt3" ></a></div></td>
    <td align="left" class="p_lr01"><a target="_blank" href="//liansai.500.com/team/6876/">布里兰</a><span class="gray">[12]</span></td>
    <td align="center" class="red"> - </td>
    <td align="center" class="bf_op">&nbsp;</td>
    <td align="center" class="red">&nbsp; </td>
    <td align="center"><a href="//odds.500.com/fenxi/stat-1473930.shtml?showAnimation=1" class="live_animate" title="动画" target="_blank"></a></td>
    <td align="center" class="td_warn"><a target="_blank" href="//odds.500.com/fenxi/shuju-1473930.shtml">析</a></td>
    <td align="center" class=""><a href="javascript:void(0)" class="icon_notop">置顶</a></td>
  </tr>
  <!-- 完赛：pk 内有主客比分 -->
  <tr id="a1502983" order="3002" status="1" gy="意甲,国际米兰,威尼斯" yy="意甲,国际米兰,威尼斯" lid="170" fid="1502983" sid="19826" class="" infoid="166382" r="1">
    <td align="center" class=""><input type="checkbox" name="check_id[]" value="1502983" />周三005</td>
    <td bgcolor="#0066FF" class="ssbox_01"><a style="color:#fff" target="_blank" href="//liansai.500.com/zuqiu-19826/">意甲</a></td>
    <td align="center">第9轮</td>
    <td align="center">10-28 03:45</td>
    <td align="center">完</td>
    <td align="right" class="p_lr01"><span class="gray">[20]</span><a target="_blank" href="//liansai.500.com/team/1249/">威尼斯</a><span class="sp_sr">(+1)</span></td>
    <td align="center"><div class="pk"><a href="./detail.php?fid=1502983" target="_blank" class="clt1" style="color:blue;">2</a><a href="./detail.php?fid=1502983" target="_blank" class="fgreen tdp20" data-ao="受球半" data-pb="受球半">受球半</a><a href="./detail.php?fid=1502983" target="_blank" class="clt3" style="color:blue;">4</a></div></td>
    <td align="left" class="p_lr01"><a target="_blank" href="//liansai.500.com/team/846/">国际米兰</a><span class="gray">[02]</span></td>
    <td align="center" class="red">1 - 0</td>
    <td align="center" class="bf_op">&nbsp;</td>
    <td align="center" class="red">&nbsp; </td>
    <td align="center"><a href="//odds.500.com/fenxi/stat-1502983.shtml?showAnimation=1" class="live_animate" title="动画" target="_blank"></a></td>
    <td align="center" class="td_warn"><a target="_blank" href="//odds.500.com/fenxi/shuju-1502983.shtml">析</a></td>
    <td align="center" class=""><a href="javascript:void(0)" class="icon_notop">置顶</a></td>
  </tr>
  </tbody>
</table>
</body></html>
"""


def _parse_all(html=MOCK_HTML):
    crawler = LiveJingcaiCrawler()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    odds_map = crawler._parse_live_odds(html)
    table = soup.find('table', class_='bf_tablelist01')
    out = []
    for row in table.find_all('tr'):
        if not row.get('id') or not str(row.get('id', '')).startswith('a'):
            continue
        item = crawler._parse_match_row(row, odds_map)
        if item:
            out.append(item)
    return out


def test_live_odds_parse():
    odds = LiveJingcaiCrawler._parse_live_odds(MOCK_HTML)
    assert "1473930" in odds
    assert odds["1473930"]["sp"] == ["1.57", "3.98", "4.15"]
    assert odds["1473930"]["rqsp"] == ["2.74", "3.55", "2.07"]


def test_upcoming_row_parse():
    matches = _parse_all()
    assert len(matches) == 2
    m = next(x for x in matches if x["fixture_id"] == "1473930")
    assert m["status"] == "upcoming"
    assert m["home_team_id"] == "T752"
    assert m["away_team_id"] == "T6876"
    assert m["home_team_name"] == "大阪钢巴"
    assert m["away_team_name"] == "布里兰"
    assert m["league_id"] == "LS19899"
    assert m["match_no"] == "周三001"
    assert m["half_score"] == "-"
    assert m["source"] == "live_jingcai"
    assert m["handicap"] == -1
    assert m["handicap_line"] == "半球/一球"
    # 胜平负 SP
    assert m["odds_spf_win"] == 1.57
    assert m["odds_spf_draw"] == 3.98
    assert m["odds_spf_lose"] == 4.15
    # 让球 SP
    assert m["odds_nspf_win"] == 2.74
    assert m["odds_nspf_draw"] == 3.55
    assert m["odds_nspf_lose"] == 2.07
    assert m["home_goals"] is None


def test_finished_row_parse():
    matches = _parse_all()
    m = next(x for x in matches if x["fixture_id"] == "1502983")
    assert m["status"] == "finished"
    assert m["home_goals"] == 2
    assert m["away_goals"] == 4
    assert m["result"] == "A"
    assert m["half_score"] == "1 - 0"
    assert m["handicap"] == 1
    assert m["handicap_line"] == "受球半"
    # 无 SP 数据（不在 liveOddsList）
    assert m["odds_spf_win"] is None
    assert m["odds_nspf_win"] is None


def test_date_parse_cross_year():
    crawler = LiveJingcaiCrawler()
    d, t = crawler._parse_match_time("10-29 01:30")
    assert d.year == date.today().year
    assert d.month == 10 and d.day == 29


def test_live_jingcai_task_registered():
    from services.crawler_service import crawler_service
    defs = {d[0]: d for d in get_task_definitions(crawler_service)}
    assert "live_jingcai_crawl" in defs
    assert defs["live_jingcai_crawl"][2] == 30
    assert defs["live_jingcai_crawl"][4] == "odds"


def test_save_matches_persists_new_columns(monkeypatch):
    """端到端：_save_matches 落库 half_score/match_no/source + SP 赔率。"""
    import sys
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.models import Base as ModelsBase, Match
    import db.models  # noqa: F401  确保所有模型注册到 models.Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    ModelsBase.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    monkeypatch.setattr(sys.modules["services.crawler_service"], "SessionLocal", TestSession)

    from services.crawler_service import crawler_service

    matches = _parse_all()
    upcoming = next(x for x in matches if x["fixture_id"] == "1473930")
    finished = next(x for x in matches if x["fixture_id"] == "1502983")
    saved, updated = crawler_service._save_matches([upcoming, finished])
    assert saved == 2, f"expected 2 saved, got {saved}"

    db = TestSession()
    try:
        m = db.query(Match).filter(Match.fixture_id == "1473930").first()
        assert m is not None
        assert m.half_score == "-"
        assert m.match_no == "周三001"
        assert m.source == "live_jingcai"
        assert m.status == "upcoming"
        assert m.handicap == -1
        assert m.handicap_line == "半球/一球"
        assert float(m.odds_spf_win) == 1.57
        assert float(m.odds_nspf_lose) == 2.07
        assert m.home_team_id is not None and m.away_team_id is not None

        fin = db.query(Match).filter(Match.fixture_id == "1502983").first()
        assert fin is not None
        assert fin.status == "finished"
        assert fin.home_goals == 2
        assert fin.away_goals == 4
        assert fin.half_score == "1 - 0"
        assert fin.handicap_line == "受球半"
        assert fin.source == "live_jingcai"
    finally:
        db.close()

