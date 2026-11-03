"""API 鉴权依赖：Token 校验与权限检查"""
import time
from typing import Optional, List, Set
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import User, UserRole, Role, RolePermission, Permission
from services import UserService
from services.subscription_service import (
    all_features as subscription_all_features,
    get_user_features,
    lazy_expire_user,
)
from services.token_store import token_store

# 兼容旧引用：内存视图（实际读写走 token_store）
TOKEN_TTL_SECONDS = token_store.ttl_seconds

def store_token(token: str, user_id: int, username: str, roles: list, permissions: list):
    token_store.store(token, user_id, username, roles, permissions)


def revoke_token(token: str):
    token_store.revoke(token)


def _parse_bearer(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录或 Token 缺失")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Authorization 格式无效")
    return parts[1].strip()


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    token = _parse_bearer(authorization)
    data = token_store.get(token)
    if not data:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    if time.time() > float(data.get("expires") or 0):
        token_store.revoke(token)
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    user = UserService.get_by_id(db, data["user_id"])
    if not user or not user.is_active:
        token_store.revoke(token)
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    # 订阅懒过期：active 但到期日已过 → 落库 expired（定时任务之外的正确性保证）
    lazy_expire_user(db, user)
    # 附加会话信息供路由使用
    user._session_roles = data.get("roles") or []
    user._session_permissions = data.get("permissions") or []
    user._session_token = token
    return user


def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not authorization:
        return None
    try:
        return get_current_user(authorization=authorization, db=db)
    except HTTPException:
        return None


def require_permissions(*codes: str):
    """要求当前用户拥有所列权限之一（空列表则仅需登录）。"""

    def _checker(user: User = Depends(get_current_user)):
        if not codes:
            return user
        if user_has_any_permission(user, *codes):
            return user
        raise HTTPException(status_code=403, detail="无权限执行此操作")

    return _checker


def user_has_any_permission(user: User, *codes: str) -> bool:
    """检查用户是否拥有任一权限（super_admin/admin 角色直接放行）。"""
    if not codes:
        return True
    roles = {r.get("code") for r in (getattr(user, "_session_roles", []) or []) if isinstance(r, dict)}
    if "super_admin" in roles or "admin" in roles:
        return True
    perms = set(getattr(user, "_session_permissions", []) or [])
    return bool(perms.intersection(codes))


def assert_self_only(user: User, target_user_id: int) -> None:
    """仅本人可访问；他人一律 403，即使本人持有 user:manage 也不能替他人操作。

    用于「操作目标是 current 自身」语义的路由（改自己的偏好、给自己加收藏、
    给自己记历史等）。想表达「本人或有权限者」请用 `assert_self_or_permission`。
    """
    if user.id != target_user_id:
        raise HTTPException(status_code=403, detail="无权访问该用户资源")


def assert_self_or_permission(user: User, target_user_id: int, *codes: str) -> None:
    """本人或具备所列任一权限方可访问目标用户资源。

    注意：如果调用点只想要「仅限本人」，请用 `assert_self_only` —— 本函数在
    self-equality 时会直接放行，忽略 codes，用于防止调用方漏写权限码导致
    「本人访问」被误当成「任意权限都放行」（`user_has_any_permission` 空 codes 返回 True）。

    - 空 codes：仅本人可通过；他人 403。
    - 有 codes：本人 or 具备任一权限码。
    """
    if user.id == target_user_id:
        return
    if not codes:
        raise HTTPException(status_code=403, detail="无权访问该用户资源")
    if user_has_any_permission(user, *codes):
        return
    raise HTTPException(status_code=403, detail="无权限访问该用户资源")


# ===== 订阅权益门控 =====

def get_entitlements(user: User, db: Session) -> Set[str]:
    """解析当前用户的有效订阅权益码。super_admin/admin 角色直接放行全集。"""
    roles = {r.get("code") for r in (getattr(user, "_session_roles", []) or []) if isinstance(r, dict)}
    if "super_admin" in roles or "admin" in roles:
        return subscription_all_features(db)
    return get_user_features(db, user)


def get_current_entitlements(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Set[str]:
    """FastAPI 依赖：返回当前用户权益码集合（供路由内做字段级掩码）。"""
    return get_entitlements(user, db)


def require_feature(*codes: str):
    """要求当前用户订阅权益包含所列之一（整接口级门控）。

    被拦时返回 403 + 结构化 detail（code=FEATURE_LOCKED），前端据此弹升级引导。
    """

    def _checker(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if not codes:
            return user
        entitlements = get_entitlements(user, db)
        if set(codes) & entitlements:
            return user
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FEATURE_LOCKED",
                "feature": codes[0],
                "message": "该功能需要更高等级订阅，请升级后使用",
            },
        )

    return _checker


def load_user_auth_payload(db: Session, user: User) -> dict:
    role_ids = [ur.role_id for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]
    roles = []
    permissions = []
    if role_ids:
        roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
        perm_ids = [
            rp.permission_id
            for rp in db.query(RolePermission).filter(RolePermission.role_id.in_(role_ids)).all()
        ]
        if perm_ids:
            permissions = db.query(Permission).filter(Permission.id.in_(perm_ids)).all()
    return {
        "roles": [{"id": r.id, "code": r.code, "name": r.name} for r in roles],
        "permissions": [p.code for p in permissions],
    }
