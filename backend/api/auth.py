"""认证模块 - 登录/验证码/Token管理"""
import random
import secrets
import string
import time
import hashlib
import math
import zlib
import struct
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from db.database import get_db
from services import UserService
from api.deps import store_token, revoke_token, load_user_auth_payload, _parse_bearer, get_current_user
from services.captcha_store import captcha_store
import bcrypt
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

CAPTCHA_EXPIRE_SECONDS = captcha_store.ttl_seconds

# 5x7 位图字模（仅覆盖验证码字符集，无 Pillow 时用于放大渲染）
_BITFONT_5X7 = {
    '0': "01110,10001,10011,10101,11001,10001,01110",
    '2': "01110,10001,00001,00110,01000,10000,11111",
    '3': "01110,10001,00001,00110,00001,10001,01110",
    '4': "00010,00110,01010,10010,11111,00010,00010",
    '5': "01110,10001,00001,00110,00001,10001,01110",
    '6': "00110,01000,10000,11110,10001,10001,01110",
    '7': "11111,00001,00010,00100,01000,01000,01000",
    '8': "01110,10001,10001,01110,10001,10001,01110",
    '9': "01110,10001,10001,01111,00001,00010,01100",
    'A': "01110,10001,10001,11111,10001,10001,10001",
    'B': "11110,10001,10001,11110,10001,10001,11110",
    'C': "01110,10001,10000,10000,10000,10001,01110",
    'D': "11110,10001,10001,10001,10001,10001,11110",
    'E': "11111,10000,10000,11110,10000,10000,11111",
    'F': "11111,10000,10000,11110,10000,10000,10000",
    'G': "01110,10001,10000,10111,10001,10001,01111",
    'H': "10001,10001,10001,11111,10001,10001,10001",
    'J': "00111,00010,00010,00010,10010,10010,01100",
    'K': "10001,10010,10100,11000,10100,10010,10001",
    'L': "10000,10000,10000,10000,10000,10000,11111",
    'M': "10001,11011,10101,10101,10001,10001,10001",
    'N': "10001,11001,10101,10011,10001,10001,10001",
    'O': "01110,10001,10001,10001,10001,10001,01110",
    'P': "11110,10001,10001,11110,10000,10000,10000",
    'Q': "01110,10001,10001,10001,10101,10010,01101",
    'R': "11110,10001,10001,11110,10100,10010,10001",
    'S': "01111,10000,10000,01110,00001,00001,11110",
    'T': "11111,00100,00100,00100,00100,00100,00100",
    'U': "10001,10001,10001,10001,10001,10001,01110",
    'V': "10001,10001,10001,10001,10001,01010,00100",
    'W': "10001,10001,10001,10101,10101,11011,10001",
    'X': "10001,10001,01010,00100,01010,10001,10001",
    'Y': "10001,10001,01010,00100,00100,00100,00100",
    'Z': "11111,00001,00010,00100,01000,10000,11111",
}

# 背景色与配色（深色主题一致）
_BG_RGB = (26, 26, 46)
_TEXT_COLORS = [
    (255, 107, 107), (78, 205, 196), (69, 183, 209), (150, 206, 180),
    (255, 234, 167), (221, 160, 221), (135, 206, 235), (155, 89, 182),
]


def generate_captcha_text(length=4):
    """生成4位随机验证码"""
    chars = string.ascii_uppercase + string.digits
    # 排除容易混淆的字符
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '').replace('L', '')
    return ''.join(random.choices(chars, k=length))


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _png_from_rgb(buf: bytes, width: int, height: int) -> bytes:
    """把 RGB 像素缓冲编码为 PNG 二进制（IDAT 为 zlib 压缩的、每行前置滤镜 0 的扫描线）。"""
    stride = width * 3
    raw = bytearray(height * (stride + 1))
    for y in range(height):
        off = y * (stride + 1)
        raw[off] = 0
        raw[off + 1: off + 1 + stride] = buf[y * stride: (y + 1) * stride]
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _png_chunk(b"IEND", b"")
    )


def _render_bitfont_glyph(text: str, x0: int, y_base: int, rotation: int, color, put, glyph_size: int):
    """5x7 点阵放大渲染。字模字符串按逗号分行。"""
    scale = max(2, glyph_size // 7)
    glyph = _BITFONT_5X7.get(text.upper())
    if not glyph:
        return
    # 切勿直接 enumerate 整串：逗号会变成空行，字形塌成竖条（看起来像 I/!）
    rows = [row for row in glyph.split(",") if row]
    ca, sa = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    cx, cy = x0 + 2 * scale, y_base + 3 * scale
    for dy, row_bits in enumerate(rows):
        for dx, bit in enumerate(row_bits):
            if bit != "1":
                continue
            for sy in range(scale):
                for sx in range(scale):
                    xi, yi = x0 + dx * scale + sx, y_base + dy * scale + sy
                    xr = int(round(cx + (xi - cx) * ca - (yi - cy) * sa))
                    yr = int(round(cy + (xi - cx) * sa + (yi - cy) * ca))
                    put(xr, yr, color, 1.0)


_TTF_CANDIDATES = (
    # Linux（需镜像内安装 fonts-dejavu-core 才有）
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # Windows 开发机
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
)


def _load_captcha_truetype(size: int):
    """仅在真实 TTF 可用时返回字体；否则 None（禁止 load_default，Linux 无字体时会画成空白）。"""
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for path in _TTF_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return None


def _render_glyph(text: str, x0: int, y_base: int, rotation: int, color, put, glyph_size: int):
    """渲染单字符：有可用 TTF 时用 Pillow；否则 5x7 点阵（Windows/Linux 一致可读）。"""
    font = _load_captcha_truetype(glyph_size + 6)
    if font is not None:
        try:
            from PIL import Image, ImageDraw
            fs = max(24, glyph_size * 2)
            img = Image.new("RGBA", (fs, fs), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((6, 2), text, fill=color + (255,), font=font)
            img = img.rotate(rotation, resample=Image.BICUBIC, expand=False)
            px = img.load()
            for yy in range(fs):
                for xx in range(fs):
                    a = px[xx, yy][3]
                    if a:
                        put(x0 + xx - 6, y_base + yy - 2, color, a / 255.0)
            return
        except Exception:
            pass

    _render_bitfont_glyph(text, x0, y_base, rotation, color, put, glyph_size)


def generate_captcha_image(text, width=160, height=52):
    """生成验证码 PNG 位图。

    字符只以像素形式存在，响应体里不含任何明文文本，无法靠解析文档内容反推答案。
    旧实现是 SVG，字符直接写在 <text> 标签里，前端一次 fetch 就能读出答案。
    """
    glyph_size = max(22, int(height * 0.62))
    buf = bytearray(width * height * 3)
    for i in range(width * height):
        buf[i * 3:i * 3 + 3] = _BG_RGB

    def put(x, y, color, alpha=1.0):
        if not (0 <= x < width and 0 <= y < height):
            return
        o = (y * width + x) * 3
        cr, cg, cb = color
        buf[o] = int(buf[o] + (cr - buf[o]) * alpha)
        buf[o + 1] = int(buf[o + 1] + (cg - buf[o + 1]) * alpha)
        buf[o + 2] = int(buf[o + 2] + (cb - buf[o + 2]) * alpha)

    def line(x1, y1, x2, y2, color, alpha):
        steps = abs(x2 - x1) + abs(y2 - y1) + 1
        for s in range(steps + 1):
            t = s / steps
            put(int(round(x1 + (x2 - x1) * t)), int(round(y1 + (y2 - y1) * t)), color, alpha)

    def dot(x, y, r, color, alpha):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    put(x + dx, y + dy, color, alpha)

    # 先画少量干扰，再画字符，避免噪点盖住字形（尤其 Linux 点阵路径）
    for _ in range(4):
        line(random.randint(0, width - 1), random.randint(0, height - 1),
             random.randint(0, width - 1), random.randint(0, height - 1),
             random.choice(_TEXT_COLORS), 0.28)
    for _ in range(36):
        dot(random.randint(0, width - 1), random.randint(0, height - 1),
            random.randint(1, 2), random.choice(_TEXT_COLORS), 0.4)

    char_w = width / ((len(text) or 1) + 0.6)
    scale = max(2, glyph_size // 7)
    glyph_h = 7 * scale
    for i, ch in enumerate(text):
        x0 = int(char_w * (i + 0.35))
        y_base = random.randint(4, max(5, height - glyph_h - 4))
        _render_glyph(ch, x0, y_base, random.randint(-12, 12), random.choice(_TEXT_COLORS), put, glyph_size)

    for _ in range(12):
        dot(random.randint(0, width - 1), random.randint(0, height - 1),
            1, random.choice(_TEXT_COLORS), 0.45)

    return _png_from_rgb(buf, width, height)


class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_id: str
    captcha_code: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.get("/captcha")
async def get_captcha():
    """获取图片验证码（PNG 位图，十六进制传输，接口形状与旧版一致）"""
    captcha_text = generate_captcha_text(4)
    # captcha_id 由密码学安全随机数生成，不复用文本派生的 md5
    captcha_id = secrets.token_hex(16)

    captcha_store.store(captcha_id, captcha_text, ttl=CAPTCHA_EXPIRE_SECONDS)

    return {
        "captcha_id": captcha_id,
        "captcha_image": generate_captcha_image(captcha_text).hex(),
        "expire_seconds": CAPTCHA_EXPIRE_SECONDS
    }


@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    from services.login_guard import clear_failures, is_locked, record_failure

    locked, wait_sec = is_locked(req.username)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"登录失败次数过多，请 {max(1, wait_sec // 60)} 分钟后再试",
        )

    # 1. 校验验证码
    stored = captcha_store.get(req.captcha_id)
    if not stored:
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")

    if req.captcha_code.upper() != stored["code"]:
        captcha_store.revoke(req.captcha_id)
        raise HTTPException(status_code=400, detail="验证码错误")

    captcha_store.revoke(req.captcha_id)

    # 2. 校验用户
    user = UserService.get_by_username(db, req.username)
    if not user:
        n, just_locked = record_failure(req.username)
        if just_locked:
            raise HTTPException(status_code=429, detail="登录失败次数过多，请 15 分钟后再试")
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    # 3. 校验密码
    if not bcrypt.checkpw(req.password.encode('utf-8'), user.password_hash.encode('utf-8')):
        n, just_locked = record_failure(req.username)
        if just_locked:
            raise HTTPException(status_code=429, detail="登录失败次数过多，请 15 分钟后再试")
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    clear_failures(req.username)

    # 4. 更新登录时间
    UserService.update_last_login(db, user.id)

    # 5. 获取用户角色和权限
    auth_payload = load_user_auth_payload(db, user)

    # 5b. 解析订阅权益（含懒过期检查）
    from api.deps import get_entitlements
    user._session_roles = auth_payload["roles"]
    features = sorted(get_entitlements(user, db))

    # 6. 生成并登记 Token（服务端可校验/吊销）
    token = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    store_token(
        token,
        user_id=user.id,
        username=user.username,
        roles=auth_payload["roles"],
        permissions=auth_payload["permissions"],
    )

    return {
        "message": "登录成功",
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "avatar": user.avatar,
            "level": user.level,
            "favorite_team_id": user.favorite_team_id,
            "join_date": str(user.join_date) if user.join_date else None,
            "total_analysis": user.total_analysis,
            "subscription_plan": user.subscription_plan,
            "subscription_status": user.subscription_status,
            "subscription_expire": str(user.subscription_expire) if user.subscription_expire else None,
            # 出厂弱口令账号：前端据此跳转账号安全页改密
            "must_change_password": bool(getattr(user, "must_change_password", False)),
        },
        "roles": auth_payload["roles"],
        "permissions": auth_payload["permissions"],
        "features": features,
    }


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """退出登录并吊销 Token"""
    try:
        token = _parse_bearer(authorization)
        revoke_token(token)
    except HTTPException:
        pass
    return {"message": "已退出登录"}


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """本人修改密码（不记操作日志的本人自助入口，与 /users/{id}/password 的管理员重置区分）。

    校验失败时把用户名记入登录失败计数，防止被当成爆破入口刷。
    """
    from api.deps import token_store
    from api.users import _assert_password_strength, hash_password, verify_password
    from services.login_guard import clear_failures, record_failure

    _assert_password_strength(req.new_password, "新密码")

    if req.old_password and verify_password(req.old_password, current.password_hash or ""):
        clear_failures(current.username)
    else:
        record_failure(current.username)
        raise HTTPException(status_code=400, detail="旧密码不正确")

    UserService.update(
        db, current.id,
        {"password_hash": hash_password(req.new_password), "must_change_password": False},
    )
    # 吊销旧会话，避免旧 token 在 24h TTL 内继续有效
    token_store.revoke_by_user(current.id)
    logger.info("AUDIT auth.change_password user=%s(id=%s)", current.username, current.id)
    return {"message": "密码已修改，请重新登录", "relogin_required": True}
