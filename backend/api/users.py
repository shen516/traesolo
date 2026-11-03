"""用户API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from db.database import get_db
from db.models import User, UserRole, Role, RolePermission, Permission
from services import UserService, PreferenceService
from api.deps import get_current_user, assert_self_or_permission, assert_self_only, user_has_any_permission
from api.authz import RequireUserManage, RequireUserCreate, RequireUserDelete, RequireProfile
from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from typing import Optional, List
import bcrypt
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# 密码强度：6-128 位。reset_password 已在 endpoint 内单独校验过，这里在 register 前显式拦。
PASSWORD_MIN_LEN = 6
PASSWORD_MAX_LEN = 128

def _assert_password_strength(password: str, field_name: str = "密码") -> None:
    if not password or len(password) < PASSWORD_MIN_LEN:
        raise HTTPException(status_code=400, detail=f"{field_name}长度不能少于{PASSWORD_MIN_LEN}位")
    if len(password) > PASSWORD_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"{field_name}长度不能超过{PASSWORD_MAX_LEN}位")


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    avatar: Optional[str] = None
    level: str = "free"
    favorite_team_id: Optional[str] = None
    subscription_plan: str = "free"
    subscription_status: str = "expired"
    role_ids: List[int] = []


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    avatar: Optional[str] = None
    level: Optional[str] = None
    favorite_team_id: Optional[str] = None
    subscription_plan: Optional[str] = None
    subscription_status: Optional[str] = None
    is_active: Optional[bool] = None
    role_ids: Optional[List[int]] = None


class PasswordReset(BaseModel):
    new_password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    avatar: Optional[str] = None
    level: str = "free"
    favorite_team_id: Optional[str] = None
    join_date: Optional[date] = None
    total_analysis: int = 0
    subscription_plan: str = "free"
    subscription_status: str = "expired"
    subscription_expire: Optional[date] = None
    is_active: bool = True
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# 管理员/超级管理员角色码：分配这些角色属于提权行为，必须持有 user:manage
_SYSTEM_ROLE_CODES = frozenset({"admin", "super_admin"})
# 用户编辑「自己」时受保护的字段：角色/启停/等级均属管理员权限
_SELF_PROTECTED_FIELDS = frozenset({"is_active", "role_ids", "level"})


def _is_admin_role(user: User) -> bool:
    """会话角色含 admin/super_admin 视为管理员，与 require_permissions 的放行语义一致。"""
    roles = {
        r.get("code")
        for r in (getattr(user, "_session_roles", []) or [])
        if isinstance(r, dict)
    }
    return bool(roles & _SYSTEM_ROLE_CODES)


def _filter_role_ids(db: Session, role_ids: List[int], current: User) -> List[int]:
    """校验并过滤拟分配的角色 id。

    无 user:manage（含 admin 角色）权限时静默剔除 admin/super_admin 系统角色，
    避免通过 register / update 的 role_ids 自我提权。
    """
    if not role_ids:
        return []
    if user_has_any_permission(current, "user:manage"):
        return list(role_ids)
    blocked = {
        r.id
        for r in db.query(Role).filter(
            Role.id.in_(role_ids), Role.code.in_(_SYSTEM_ROLE_CODES)
        ).all()
    }
    return [rid for rid in role_ids if rid not in blocked]


def _can_manage_user(current: User) -> bool:
    """是否可管理他人（含分配角色）：admin 角色或持有 user:edit/user:manage 之一。"""
    return _is_admin_role(current) or user_has_any_permission(current, "user:edit", "user:manage")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def get_user_roles(db: Session, user_id: int):
    """获取用户的角色列表"""
    role_ids = [ur.role_id for ur in db.query(UserRole).filter(UserRole.user_id == user_id).all()]
    if not role_ids:
        return [], []
    roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
    return roles, role_ids


def get_user_permissions(db: Session, user_id: int):
    """获取用户的所有权限编码（合并所有角色的权限）"""
    role_ids = [ur.role_id for ur in db.query(UserRole).filter(UserRole.user_id == user_id).all()]
    if not role_ids:
        return []
    perm_ids = [rp.permission_id for rp in db.query(RolePermission).filter(RolePermission.role_id.in_(role_ids)).all()]
    if not perm_ids:
        return []
    perms = db.query(Permission).filter(Permission.id.in_(perm_ids)).all()
    return [p.code for p in perms]


def assign_user_roles(db: Session, user_id: int, role_ids: List[int]):
    """分配用户角色"""
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    for rid in role_ids:
        role = db.query(Role).filter(Role.id == rid).first()
        if role:
            ur = UserRole(user_id=user_id, role_id=rid)
            db.add(ur)
    db.commit()


@router.get("/", dependencies=[RequireUserManage])
async def get_users(
    keyword: str = Query(None, description="搜索关键词（用户名/邮箱）"),
    level: str = Query(None, description="用户等级"),
    is_active: bool = Query(None, description="是否启用"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db)
):
    """获取用户列表（支持分页和搜索）"""
    query = db.query(User)

    if keyword:
        query = query.filter(or_(
            User.username.contains(keyword),
            User.email.contains(keyword)
        ))
    if level:
        query = query.filter(User.level == level)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total = query.count()
    users = query.order_by(User.created_at.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for u in users:
        user_data = UserResponse.model_validate(u).model_dump()
        roles, _ = get_user_roles(db, u.id)
        user_data['roles'] = [{'id': r.id, 'name': r.name, 'code': r.code} for r in roles]
        result.append(user_data)

    return {
        "users": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/all", dependencies=[RequireUserManage])
async def get_all_users(db: Session = Depends(get_db)):
    """获取所有用户（不分页，用于下拉选择等场景）"""
    users = UserService.get_all(db)
    return {"users": [UserResponse.model_validate(u) for u in users]}


@router.get("/stats/summary", dependencies=[RequireUserManage])
async def get_users_summary(db: Session = Depends(get_db)):
    """用户统计摘要"""
    total = db.query(User).count()
    active = db.query(User).filter(User.is_active == True).count()
    disabled = db.query(User).filter(User.is_active == False).count()
    professional = db.query(User).filter(User.level == 'professional').count()
    free = db.query(User).filter(User.level == 'free').count()

    today = date.today()
    new_today = db.query(User).filter(User.join_date == today).count()

    return {
        "total": total,
        "active": active,
        "disabled": disabled,
        "professional": professional,
        "free": free,
        "new_today": new_today
    }


@router.get("/{user_id}", dependencies=[RequireProfile])
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_or_permission(current, user_id, "user:manage")
    user = UserService.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user_data = UserResponse.model_validate(user).model_dump()
    roles, role_ids = get_user_roles(db, user_id)
    user_data['roles'] = [{'id': r.id, 'name': r.name, 'code': r.code} for r in roles]
    user_data['role_ids'] = role_ids
    return user_data


@router.post("/register", dependencies=[RequireUserCreate])
async def register_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    existing = UserService.get_by_username(db, data.username)
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    existing_email = UserService.get_by_email(db, data.email)
    if existing_email:
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user_data = data.model_dump()
    # 分配角色需 user:edit；仅 user:manage（含 admin 角色）能授 admin/super_admin
    raw_role_ids = user_data.pop("role_ids", []) or []
    allowed_role_ids = _filter_role_ids(db, raw_role_ids, current)
    if allowed_role_ids and not user_has_any_permission(current, "user:manage", "user:edit"):
        raise HTTPException(status_code=403, detail="无权限分配角色，需要 user:edit 权限")

    _assert_password_strength(data.password)
    user_data["password_hash"] = hash_password(user_data.pop("password"))
    user_data["join_date"] = date.today()
    user_data["is_active"] = True
    # 订阅走 grant API，新建账号一律免费版
    user_data["subscription_plan"] = "free"
    user_data["subscription_status"] = "active"
    user_data["subscription_expire"] = None

    user = UserService.create(db, user_data)
    PreferenceService.create_or_update(db, user.id, {})

    if allowed_role_ids:
        assign_user_roles(db, user.id, allowed_role_ids)

    # 审计：谁在何时创建了谁、授了哪些角色
    try:
        logger.info(
            "AUDIT user.create operator=%s new_user=%s(id=%s) role_ids=%s",
            getattr(current, "username", "?"), data.username, user.id,
            allowed_role_ids or [],
        )
    except Exception:
        pass

    return {"message": "用户创建成功", "user_id": user.id, "user": UserResponse.model_validate(user)}


@router.put("/{user_id}", dependencies=[RequireProfile])
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    update_data = data.model_dump(exclude_unset=True)
    role_ids = update_data.pop("role_ids", None)
    is_self = current.id == user_id

    if is_self:
        # 编辑本人：默认只允许改基础资料；角色/启停/等级必须显式持有 user:edit 或 admin 角色。
        # 不能走 assert_self_or_permission —— 它遇到 self-equality 会短路放行，恰好让本分支失效。
        sensitive = _SELF_PROTECTED_FIELDS.intersection(update_data.keys())
        if sensitive and not (user_has_any_permission(current, "user:edit") or _is_admin_role(current)):
            raise HTTPException(status_code=403, detail="无权修改敏感字段")
    else:
        if not _can_manage_user(current):
            assert_self_or_permission(current, user_id, "user:edit")

    if role_ids is not None:
        # 分配任何角色都要 user:edit；本人改角色还需 admin 角色（防自我提权循环）
        if is_self:
            if not _is_admin_role(current):
                raise HTTPException(status_code=403, detail="无权限变更本人角色")
        elif not user_has_any_permission(current, "user:edit"):
            assert_self_or_permission(current, user_id, "user:edit")
        # admin/super_admin 角色只有 user:manage（含 admin 角色）能授
        role_ids = _filter_role_ids(db, role_ids, current)

    user = UserService.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 订阅字段只能通过 /subscription/grant|cancel 变更
    update_data.pop("subscription_plan", None)
    update_data.pop("subscription_status", None)
    update_data.pop("subscription_expire", None)

    # 检查用户名和邮箱唯一性
    if update_data.get("username") and update_data["username"] != user.username:
        existing = UserService.get_by_username(db, update_data["username"])
        if existing:
            raise HTTPException(status_code=400, detail="用户名已存在")
    if update_data.get("email") and update_data["email"] != user.email:
        existing = UserService.get_by_email(db, update_data["email"])
        if existing:
            raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = UserService.update(db, user_id, update_data)

    if role_ids is not None:
        assign_user_roles(db, user_id, role_ids)

    return UserResponse.model_validate(user)


@router.put("/{user_id}/password", dependencies=[RequireProfile])
async def reset_password(
    user_id: int,
    data: PasswordReset,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """重置密码：本人可改；重置他人密码需 user:manage。"""
    if current.id == user_id:
        assert_self_only(current, user_id)
    else:
        assert_self_or_permission(current, user_id, "user:manage")
    user = UserService.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    _assert_password_strength(data.new_password, "新密码")
    new_hash = hash_password(data.new_password)
    UserService.update(db, user_id, {"password_hash": new_hash})
    try:
        logger.info(
            "AUDIT user.reset_password operator=%s target=%s(id=%s) self=%s",
            getattr(current, "username", "?"), getattr(user, "username", "?"),
            user_id, current.id == user_id,
        )
    except Exception:
        pass
    return {"message": "密码重置成功"}


@router.put("/{user_id}/status", dependencies=[RequireUserManage])
async def toggle_user_status(
    user_id: int,
    is_active: bool = Query(..., description="是否启用"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """启用/禁用用户"""
    user = UserService.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不允许禁用超级管理员
    if user.username == "admin" and not is_active:
        raise HTTPException(status_code=400, detail="不允许禁用超级管理员账号")

    # 不允许禁用自己（避免管理员把自己锁在门外）
    if user_id == current.id and not is_active:
        raise HTTPException(status_code=400, detail="不允许禁用当前登录账号")

    user = UserService.update(db, user_id, {"is_active": is_active})

    # 禁用后立刻吊销该用户的全部 token，避免其凭未过期会话继续访问
    revoked = 0
    if not is_active:
        try:
            from api.deps import token_store
            revoked = token_store.revoke_by_user(user_id)
        except Exception:
            logger.warning("revoke tokens on disable failed for user %s", user_id)

    return {
        "message": f"用户已{'启用' if is_active else '禁用'}",
        "is_active": is_active,
        "revoked_tokens": revoked,
    }


@router.delete("/{user_id}", dependencies=[RequireUserDelete])
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = UserService.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不允许删除超级管理员
    if user.username == "admin":
        raise HTTPException(status_code=400, detail="不允许删除超级管理员账号")

    # 先清理关联数据（避免外键约束失败）
    from db.models import UserFavorite, UserHistory, UserPreference, OperationLog
    db.query(UserFavorite).filter(UserFavorite.user_id == user_id).delete(synchronize_session=False)
    db.query(UserHistory).filter(UserHistory.user_id == user_id).delete(synchronize_session=False)
    db.query(UserPreference).filter(UserPreference.user_id == user_id).delete(synchronize_session=False)
    db.query(OperationLog).filter(OperationLog.user_id == user_id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()

    # 删除后吊销残留会话
    try:
        from api.deps import token_store
        token_store.revoke_by_user(user_id)
    except Exception:
        logger.warning("revoke tokens on delete failed for user %s", user_id)

    return {"message": "用户删除成功"}


@router.get("/{user_id}/stats", dependencies=[RequireProfile])
async def get_user_stats(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_or_permission(current, user_id, "user:manage")
    user = UserService.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "user_id": user.id,
        "total_analysis": user.total_analysis,
        "level": user.level,
        "subscription_status": user.subscription_status
    }


@router.put("/{user_id}/favorite", dependencies=[RequireProfile])
async def set_favorite_team(
    user_id: int,
    team_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_only(current, user_id)
    user = UserService.update(db, user_id, {"favorite_team_id": team_id})
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"message": "收藏球队更新成功", "team_id": team_id}


_REFRESH_LABEL_TO_MIN = {
    "realtime": 1,
    "5min": 5,
    "15min": 15,
    "30min": 30,
    "1hour": 60,
}
_REFRESH_MIN_TO_LABEL = {v: k for k, v in _REFRESH_LABEL_TO_MIN.items()}


class PreferenceUpdate(BaseModel):
    push_notification: Optional[bool] = None
    refresh_rate: Optional[str] = None  # realtime|5min|15min|30min|1hour
    default_league_id: Optional[str] = None
    follow_include_children: Optional[bool] = None
    theme: Optional[str] = None
    language: Optional[str] = None


def _preference_to_api(pref) -> dict:
    if not pref:
        return {
            "push_notification": True,
            "refresh_rate": "15min",
            "refresh_interval": 15,
            "default_league_id": "",
            "follow_include_children": False,
            "theme": "dark",
            "language": "zh-CN",
        }
    mins = int(pref.refresh_interval or 15)
    return {
        "push_notification": bool(pref.push_notification) if pref.push_notification is not None else True,
        "refresh_rate": _REFRESH_MIN_TO_LABEL.get(mins, "15min"),
        "refresh_interval": mins,
        "default_league_id": pref.default_league_id or "",
        "follow_include_children": bool(getattr(pref, "follow_include_children", False)),
        "theme": pref.theme or "dark",
        "language": pref.language or "zh-CN",
    }


@router.get("/{user_id}/preferences", dependencies=[RequireProfile])
async def get_preferences(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_or_permission(current, user_id, "user:manage")
    pref = PreferenceService.get_by_user(db, user_id)
    return _preference_to_api(pref)


@router.put("/{user_id}/preferences", dependencies=[RequireProfile])
async def update_preferences(
    user_id: int,
    body: PreferenceUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_or_permission(current, user_id, "user:manage")
    user = UserService.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    data = {}
    if body.push_notification is not None:
        data["push_notification"] = body.push_notification
    if body.refresh_rate is not None:
        if body.refresh_rate not in _REFRESH_LABEL_TO_MIN:
            raise HTTPException(status_code=400, detail="无效的刷新频率")
        data["refresh_interval"] = _REFRESH_LABEL_TO_MIN[body.refresh_rate]
    if body.default_league_id is not None:
        data["default_league_id"] = body.default_league_id or None
    if body.follow_include_children is not None:
        data["follow_include_children"] = body.follow_include_children
    if body.theme is not None:
        data["theme"] = body.theme
    if body.language is not None:
        data["language"] = body.language

    pref = PreferenceService.create_or_update(db, user_id, data)
    return {"message": "偏好已保存", "preferences": _preference_to_api(pref)}
