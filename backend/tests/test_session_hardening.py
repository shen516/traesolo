"""Security regressions: captcha not machine-recoverable, session revocation on disable/delete."""
import struct
import zlib

from services import PreferenceService, UserService
from services.captcha_store import captcha_store
from api.deps import token_store
from db.database import SessionLocal

import bcrypt
from datetime import date

# Probe endpoint that only requires a valid session (no extra permission needed)
PROBE_URL = "/api/v1/subscription/my"

# CJK wording used in the API error messages, written as escapes so the source
# file stays ASCII-safe regardless of how editors/shells round-trip it.
# "captcha expired" = ??????
ERR_CAPTCHA_EXPIRED = "\u9a8c\u8bc1\u7801\u5df2\u8fc7\u671f"
# "session invalid" = ??
ERR_SESSION_INVALID = "\u5931\u6548"


def test_bitfont_glyph_is_not_a_vertical_bar():
    """5x7 字模必须按逗号分行；否则会画成竖条，肉眼像 I/!。"""
    from api.auth import _BG_RGB, _render_bitfont_glyph

    width, height = 40, 40
    buf = bytearray(width * height * 3)
    for i in range(width * height):
        buf[i * 3: i * 3 + 3] = _BG_RGB

    def put(x, y, color, alpha=1.0):
        if not (0 <= x < width and 0 <= y < height):
            return
        o = (y * width + x) * 3
        cr, cg, cb = color
        buf[o] = int(buf[o] + (cr - buf[o]) * alpha)
        buf[o + 1] = int(buf[o + 1] + (cg - buf[o + 1]) * alpha)
        buf[o + 2] = int(buf[o + 2] + (cb - buf[o + 2]) * alpha)

    _render_bitfont_glyph("A", 8, 8, 0, (255, 255, 255), put, 21)

    xs = [
        x
        for y in range(height)
        for x in range(width)
        if tuple(buf[(y * width + x) * 3: (y * width + x) * 3 + 3]) != _BG_RGB
    ]
    assert xs, "glyph painted no pixels"
    assert max(xs) - min(xs) >= 8, (
        f"glyph too thin (width={max(xs) - min(xs)}); likely missing split(',')"
    )


def test_captcha_is_png_and_answer_is_not_plaintext(client):
    """Captcha must be a PNG bitmap; the answer must not appear in the image bytes.

    The previous implementation returned an SVG with the answer inside <text>
    tags, so the frontend could read it back with one fetch + DOMParser.
    """
    res = client.get("/api/v1/auth/captcha")
    assert res.status_code == 200
    body = res.json()

    raw = bytes.fromhex(body["captcha_image"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "captcha_image is not PNG"

    # Structural checks: valid IHDR, IDAT payload is zlib-compressed
    w, h = struct.unpack(">II", raw[16:24])
    assert w > 0 and h > 0
    assert raw[24] == 8 and raw[25] == 2  # 8-bit depth, RGB
    # IDAT layout: len(4) + "IDAT"(4) + data(len) + crc(4)
    name_offset = raw.index(b"IDAT")
    idat_len = struct.unpack(">I", raw[name_offset - 4: name_offset])[0]
    data_offset = name_offset + 4
    zlib.decompress(raw[data_offset: data_offset + idat_len])

    stored = captcha_store.get(body["captcha_id"])
    assert stored is not None
    answer_bytes = stored["code"].encode("utf-8")
    assert answer_bytes not in raw
    assert stored["code"] not in body["captcha_image"]


def test_captcha_is_single_use(client):
    """A captcha is single-use: the same captcha_id cannot be replayed."""
    res = client.get("/api/v1/auth/captcha")
    body = res.json()
    payload = {
        "username": "admin",
        "password": "definitely-wrong",
        "captcha_id": body["captcha_id"],
        "captcha_code": "ZZZZ",
    }
    first = client.post("/api/v1/auth/login", json=payload)
    assert first.status_code == 400
    second = client.post("/api/v1/auth/login", json=payload)
    assert second.status_code == 400
    # Second attempt must be rejected as expired, not as a wrong code:
    # proves the captcha is destroyed after a failed check.
    assert ERR_CAPTCHA_EXPIRED in second.json()["detail"]
    assert ERR_CAPTCHA_EXPIRED not in first.json()["detail"]


def _purge_user_rows(db, user_id):
    """Delete the rows that reference users.id before deleting the User itself.

    Mirrors api/users.py delete_user. Deleting the User with dependent rows
    still present makes SQLAlchemy raise on the user_preferences primary key.
    """
    from db.models import (
        OperationLog,
        SubscriptionRecord,
        UserFavorite,
        UserHistory,
        UserPreference,
        UserRole,
    )
    db.query(UserFavorite).filter(UserFavorite.user_id == user_id).delete(synchronize_session=False)
    db.query(UserHistory).filter(UserHistory.user_id == user_id).delete(synchronize_session=False)
    db.query(UserPreference).filter(UserPreference.user_id == user_id).delete(synchronize_session=False)
    db.query(OperationLog).filter(OperationLog.user_id == user_id).delete(synchronize_session=False)
    db.query(UserRole).filter(UserRole.user_id == user_id).delete(synchronize_session=False)
    db.query(SubscriptionRecord).filter(SubscriptionRecord.user_id == user_id).delete(synchronize_session=False)


def _create_test_user(db, username, password):
    """Create a throwaway user the way the register endpoint does. Returns user_id."""
    existing = UserService.get_by_username(db, username)
    if existing:
        _purge_user_rows(db, existing.id)
        db.delete(existing)
        db.commit()
    UserService.create(db, {
        "username": username,
        "email": f"{username}@test.local",
        "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        "join_date": date.today(),
        "subscription_plan": "free",
        "subscription_status": "active",
        "subscription_expire": None,
        "is_active": True,
    })
    db.commit()
    user = UserService.get_by_username(db, username)
    PreferenceService.create_or_update(db, user.id, {})
    return user.id


def _login_as(client, username, password):
    cap = client.get("/api/v1/auth/captcha")
    code = captcha_store.get(cap.json()["captcha_id"])["code"]
    res = client.post("/api/v1/auth/login", json={
        "username": username,
        "password": password,
        "captcha_id": cap.json()["captcha_id"],
        "captcha_code": code,
    })
    assert res.status_code == 200, res.text
    return res.json()["token"]


def test_disabling_user_revokes_sessions(client, admin_token):
    """Disabling a user immediately invalidates that user's live sessions."""
    db = SessionLocal()
    try:
        user_id = _create_test_user(db, "victim_session", "victim-pass-123")
        token = _login_as(client, "victim_session", "victim-pass-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get(PROBE_URL, headers=headers).status_code == 200

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        disable = client.put(
            f"/api/v1/users/{user_id}/status",
            params={"is_active": False},
            headers=admin_headers,
        )
        assert disable.status_code == 200, disable.text
        assert disable.json()["revoked_tokens"] >= 1

        after = client.get(PROBE_URL, headers=headers)
        assert after.status_code == 401, after.text
        assert ERR_SESSION_INVALID in after.json()["detail"]

        _purge_user_rows(db, user_id)
        db.delete(UserService.get_by_id(db, user_id))
        db.commit()
    finally:
        db.close()


def test_delete_user_revokes_sessions(client, admin_token):
    """Deleting a user also immediately invalidates that user's sessions."""
    db = SessionLocal()
    try:
        user_id = _create_test_user(db, "doomed_session", "doomed-pass-123")
        token = _login_as(client, "doomed_session", "doomed-pass-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get(PROBE_URL, headers=headers).status_code == 200

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        deleted = client.delete(f"/api/v1/users/{user_id}", headers=admin_headers)
        assert deleted.status_code == 200, deleted.text

        after = client.get(PROBE_URL, headers=headers)
        assert after.status_code == 401, after.text

        token_store.revoke(token)
    finally:
        db.close()


def test_admin_cannot_disable_self(client, admin_token):
    """A manager cannot disable the account they are currently logged in with."""
    db = SessionLocal()
    try:
        admin = UserService.get_by_username(db, "admin")
        res = client.put(
            f"/api/v1/users/{admin.id}/status",
            params={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 400, res.text
    finally:
        db.close()
