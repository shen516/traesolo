"""关注联赛：幂等关注、上限、空 league_ids 不回退全量。"""
from db.database import SessionLocal
from db.models import League
from services.crud.follow import MAX_FOLLOWED_LEAGUES


def _ensure_league(league_id="EPL", name="英超", parent_id=None, is_active=True):
    db = SessionLocal()
    try:
        row = db.query(League).filter(League.id == league_id).first()
        if not row:
            db.add(League(id=league_id, name=name, is_active=is_active, parent_id=parent_id))
        else:
            row.name = name
            row.is_active = is_active
            if parent_id is not None:
                row.parent_id = parent_id
        db.commit()
    finally:
        db.close()


def test_follow_list_follow_unfollow(client, auth_headers):
    _ensure_league()
    listed = client.get("/api/v1/follows/leagues", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    before = listed.json().get("ids") or []

    created = client.post("/api/v1/follows/leagues/EPL", headers=auth_headers)
    assert created.status_code == 200, created.text
    assert created.json()["league"]["id"] == "EPL"

    again = client.post("/api/v1/follows/leagues/EPL", headers=auth_headers)
    assert again.status_code == 200, again.text

    ids = client.get("/api/v1/follows/leagues/ids", headers=auth_headers)
    assert ids.status_code == 200
    assert "EPL" in ids.json()["ids"]

    missing = client.post("/api/v1/follows/leagues/NOT_A_LEAGUE", headers=auth_headers)
    assert missing.status_code == 400

    removed = client.delete("/api/v1/follows/leagues/EPL", headers=auth_headers)
    assert removed.status_code == 200, removed.text

    after = client.get("/api/v1/follows/leagues/ids", headers=auth_headers)
    assert "EPL" not in (after.json().get("ids") or [])

    # 恢复测试前状态
    for lid in before:
        client.post(f"/api/v1/follows/leagues/{lid}", headers=auth_headers)


def test_replace_and_empty_league_ids(client, auth_headers):
    _ensure_league("EPL", "英超")
    _ensure_league("LALIGA", "西甲")

    replaced = client.put(
        "/api/v1/follows/leagues",
        headers=auth_headers,
        json={"league_ids": ["EPL", "LALIGA"]},
    )
    assert replaced.status_code == 200, replaced.text
    assert set(replaced.json()["ids"]) == {"EPL", "LALIGA"}

    empty_ids = client.get(
        "/api/v1/matches/upcoming",
        headers=auth_headers,
        params={"league_ids": "", "page_size": 5},
    )
    assert empty_ids.status_code == 200, empty_ids.text
    assert empty_ids.json()["matches"] == []
    assert empty_ids.json()["pagination"]["total"] == 0

    filtered = client.get(
        "/api/v1/matches/upcoming",
        headers=auth_headers,
        params={"league_ids": "EPL", "page_size": 5},
    )
    assert filtered.status_code == 200, filtered.text


def test_follow_limit(client, auth_headers):
    db = SessionLocal()
    try:
        from db.models import User
        user = db.query(User).filter(User.username == "admin").first()
        if not user:
            return
        for i in range(MAX_FOLLOWED_LEAGUES + 1):
            lid = f"FL{i:02d}"
            if not db.query(League).filter(League.id == lid).first():
                db.add(League(id=lid, name=f"测试联赛{i}", is_active=True))
        db.commit()
    finally:
        db.close()

    ids = [f"FL{i:02d}" for i in range(MAX_FOLLOWED_LEAGUES)]
    ok = client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": ids})
    assert ok.status_code == 200, ok.text

    overflow = client.post("/api/v1/follows/leagues/FL20", headers=auth_headers)
    assert overflow.status_code == 400
    assert "最多关注" in overflow.json()["detail"]

    # 清掉测试关注，避免污染其它用例
    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": []})


def test_follow_summary_empty_and_populated(client, auth_headers):
    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": []})
    empty = client.get("/api/v1/follows/summary", headers=auth_headers)
    assert empty.status_code == 200, empty.text
    body = empty.json()
    assert body["ids"] == []
    assert body["matches"] == []
    assert body["boards"] == []

    _ensure_league("EPL", "英超")
    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": ["EPL"]})
    filled = client.get(
        "/api/v1/follows/summary",
        headers=auth_headers,
        params={"per_league_matches": 5, "match_limit": 8},
    )
    assert filled.status_code == 200, filled.text
    data = filled.json()
    assert data["ids"] == ["EPL"]
    assert isinstance(data["matches"], list)
    assert any(board["league_id"] == "EPL" for board in data["boards"])
    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": []})


def test_risk_followed_only_empty_not_fallback(client, auth_headers):
    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": []})
    res = client.get("/api/v1/risk/", headers=auth_headers, params={"followed_only": True})
    assert res.status_code == 200, res.text
    assert res.json()["alerts"] == []


def test_include_children_expands_filter_ids_not_follow_ids(client, auth_headers):
    _ensure_league("P3P", "三期父联赛")
    _ensure_league("P3C", "三期子联赛", parent_id="P3P")
    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": ["P3P"]})

    plain = client.get("/api/v1/follows/leagues/ids", headers=auth_headers)
    assert plain.status_code == 200, plain.text
    assert plain.json()["ids"] == ["P3P"]
    assert "P3C" not in (plain.json().get("filter_ids") or [])

    expanded = client.get(
        "/api/v1/follows/leagues/ids",
        headers=auth_headers,
        params={"include_children": True},
    )
    assert expanded.status_code == 200, expanded.text
    assert expanded.json()["ids"] == ["P3P"]
    assert "P3C" in expanded.json()["filter_ids"]
    assert expanded.json()["child_map"].get("P3P") == ["P3C"]

    summary = client.get(
        "/api/v1/follows/summary",
        headers=auth_headers,
        params={"include_children": True, "match_limit": 5},
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["ids"] == ["P3P"]
    assert "P3C" in summary.json()["filter_ids"]

    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": []})


def test_include_children_empty_not_fallback(client, auth_headers):
    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": []})
    res = client.get(
        "/api/v1/follows/leagues/ids",
        headers=auth_headers,
        params={"include_children": True},
    )
    assert res.status_code == 200, res.text
    assert res.json()["ids"] == []
    assert res.json()["filter_ids"] == []


def test_inactive_follow_excluded_from_filter_ids(client, auth_headers):
    _ensure_league("P3DEAD", "三期停用联赛", is_active=True)
    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": ["P3DEAD"]})
    _ensure_league("P3DEAD", "三期停用联赛", is_active=False)

    res = client.get("/api/v1/follows/leagues/ids", headers=auth_headers)
    assert res.status_code == 200, res.text
    assert "P3DEAD" in res.json()["ids"]
    assert "P3DEAD" not in (res.json().get("filter_ids") or [])

    listed = client.get("/api/v1/follows/leagues", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    item = next(x for x in listed.json()["leagues"] if x["id"] == "P3DEAD")
    assert item["is_active"] is False

    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": []})
    _ensure_league("P3DEAD", "三期停用联赛", is_active=True)


def test_delete_league_clears_follows(client, auth_headers):
    _ensure_league("P3DEL", "三期待删联赛")
    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": ["P3DEL"]})
    ids = client.get("/api/v1/follows/leagues/ids", headers=auth_headers)
    assert "P3DEL" in ids.json()["ids"]

    db = SessionLocal()
    try:
        from services.crud.league import LeagueService
        LeagueService.delete(db, "P3DEL")
    finally:
        db.close()

    after = client.get("/api/v1/follows/leagues/ids", headers=auth_headers)
    assert after.status_code == 200, after.text
    assert "P3DEL" not in (after.json().get("ids") or [])


def test_empty_follows_does_not_scope_unfiltered_upcoming(client, auth_headers):
    client.put("/api/v1/follows/leagues", headers=auth_headers, json={"league_ids": []})
    scoped = client.get(
        "/api/v1/matches/upcoming",
        headers=auth_headers,
        params={"league_ids": "", "page_size": 1},
    )
    unscoped = client.get(
        "/api/v1/matches/upcoming",
        headers=auth_headers,
        params={"page_size": 1},
    )
    assert scoped.status_code == 200
    assert unscoped.status_code == 200
    assert scoped.json()["matches"] == []
    assert scoped.json()["pagination"]["total"] == 0
    # 未传 league_ids 时不因空关注而强制为空（有数据则应能查出）
    if unscoped.json()["pagination"]["total"] > 0:
        assert unscoped.json()["matches"] != []
