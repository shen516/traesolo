"""角色与权限管理API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from db.database import get_db
from db.models import Role, Permission, RolePermission, UserRole
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from api.authz import RequireRoleManage

router = APIRouter(dependencies=[RequireRoleManage])


class RoleCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None


class PermissionCreate(BaseModel):
    name: str
    code: str
    type: str = 'menu'
    parent_id: int = 0
    path: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int = 0
    description: Optional[str] = None


class PermissionUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    type: Optional[str] = None
    parent_id: Optional[int] = None
    path: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    description: Optional[str] = None


class RolePermissionsUpdate(BaseModel):
    permission_ids: List[int]


# ===== 角色管理 =====

@router.get("/roles")
async def get_roles(
    keyword: str = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db)
):
    """获取角色列表（支持分页和搜索）"""
    query = db.query(Role)

    if keyword:
        query = query.filter(or_(
            Role.name.contains(keyword),
            Role.code.contains(keyword)
        ))

    total = query.count()
    roles = query.order_by(Role.id.asc()) \
        .offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for role in roles:
        perm_count = db.query(RolePermission).filter(RolePermission.role_id == role.id).count()
        result.append({
            'id': role.id,
            'name': role.name,
            'code': role.code,
            'description': role.description,
            'is_system': role.is_system,
            'permission_count': perm_count,
            'created_at': role.created_at,
            'updated_at': role.updated_at
        })

    return {
        "roles": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/roles/all")
async def get_all_roles(db: Session = Depends(get_db)):
    """获取所有角色（用于下拉选择）"""
    roles = db.query(Role).order_by(Role.id.asc()).all()
    return {"roles": [{'id': r.id, 'name': r.name, 'code': r.code} for r in roles]}


@router.get("/roles/{role_id}")
async def get_role(role_id: int, db: Session = Depends(get_db)):
    """获取角色详情"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    perm_ids = [rp.permission_id for rp in db.query(RolePermission).filter(RolePermission.role_id == role_id).all()]

    return {
        'id': role.id,
        'name': role.name,
        'code': role.code,
        'description': role.description,
        'is_system': role.is_system,
        'permission_ids': perm_ids,
        'created_at': role.created_at,
        'updated_at': role.updated_at
    }


@router.post("/roles")
async def create_role(data: RoleCreate, db: Session = Depends(get_db)):
    """创建角色"""
    existing = db.query(Role).filter(Role.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="角色编码已存在")

    role = Role(
        name=data.name,
        code=data.code,
        description=data.description
    )
    db.add(role)
    db.commit()
    db.refresh(role)

    return {"message": "角色创建成功", "role_id": role.id}


@router.put("/roles/{role_id}")
async def update_role(role_id: int, data: RoleUpdate, db: Session = Depends(get_db)):
    """更新角色"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if role.is_system:
        raise HTTPException(status_code=400, detail="系统内置角色不允许修改")

    update_data = data.model_dump(exclude_unset=True)

    if 'code' in update_data and update_data['code'] != role.code:
        existing = db.query(Role).filter(Role.code == update_data['code']).first()
        if existing:
            raise HTTPException(status_code=400, detail="角色编码已存在")

    for key, value in update_data.items():
        setattr(role, key, value)

    db.commit()
    return {"message": "角色更新成功"}


@router.delete("/roles/{role_id}")
async def delete_role(role_id: int, db: Session = Depends(get_db)):
    """删除角色"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if role.is_system:
        raise HTTPException(status_code=400, detail="系统内置角色不允许删除")

    user_count = db.query(UserRole).filter(UserRole.role_id == role_id).count()
    if user_count > 0:
        raise HTTPException(status_code=400, detail=f"该角色下还有 {user_count} 个用户，无法删除")

    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    db.delete(role)
    db.commit()

    return {"message": "角色删除成功"}


@router.get("/roles/{role_id}/permissions")
async def get_role_permissions(role_id: int, db: Session = Depends(get_db)):
    """获取角色的权限列表"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    perm_ids = [rp.permission_id for rp in db.query(RolePermission).filter(RolePermission.role_id == role_id).all()]
    permissions = db.query(Permission).filter(Permission.id.in_(perm_ids)).all() if perm_ids else []

    return {"permissions": permissions, "permission_ids": perm_ids}


@router.put("/roles/{role_id}/permissions")
async def update_role_permissions(role_id: int, data: RolePermissionsUpdate, db: Session = Depends(get_db)):
    """更新角色权限分配"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()

    for pid in data.permission_ids:
        perm = db.query(Permission).filter(Permission.id == pid).first()
        if perm:
            rp = RolePermission(role_id=role_id, permission_id=pid)
            db.add(rp)

    db.commit()
    return {"message": "角色权限更新成功"}


# ===== 权限管理 =====

@router.get("/permissions")
async def get_permissions(
    keyword: str = Query(None, description="搜索关键词"),
    type: str = Query(None, description="权限类型：menu/button/api"),
    db: Session = Depends(get_db)
):
    """获取权限列表（树状结构）"""
    query = db.query(Permission)

    if keyword:
        query = query.filter(or_(
            Permission.name.contains(keyword),
            Permission.code.contains(keyword)
        ))
    if type:
        query = query.filter(Permission.type == type)

    permissions = query.order_by(Permission.sort_order.asc(), Permission.id.asc()).all()

    perm_list = [
        {
            'id': p.id,
            'name': p.name,
            'code': p.code,
            'type': p.type,
            'parent_id': p.parent_id,
            'path': p.path,
            'icon': p.icon,
            'sort_order': p.sort_order,
            'description': p.description,
            'created_at': p.created_at,
            'updated_at': p.updated_at
        } for p in permissions
    ]

    id_map = {p['id']: p for p in perm_list}
    roots = []

    for p in perm_list:
        if p['parent_id'] and p['parent_id'] in id_map:
            parent = id_map[p['parent_id']]
            if 'children' not in parent:
                parent['children'] = []
            parent['children'].append(p)
        else:
            roots.append(p)

    return {"permissions": roots, "flat": perm_list}


@router.get("/permissions/all")
async def get_all_permissions(db: Session = Depends(get_db)):
    """获取所有权限（扁平列表，用于分配权限时选择）"""
    permissions = db.query(Permission).order_by(Permission.sort_order.asc(), Permission.id.asc()).all()
    return {
        "permissions": [
            {
                'id': p.id,
                'name': p.name,
                'code': p.code,
                'type': p.type,
                'parent_id': p.parent_id,
                'path': p.path,
                'icon': p.icon,
                'sort_order': p.sort_order,
                'description': p.description
            } for p in permissions
        ]
    }


@router.post("/permissions")
async def create_permission(data: PermissionCreate, db: Session = Depends(get_db)):
    """创建权限"""
    existing = db.query(Permission).filter(Permission.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="权限编码已存在")

    perm = Permission(
        name=data.name,
        code=data.code,
        type=data.type,
        parent_id=data.parent_id,
        path=data.path,
        icon=data.icon,
        sort_order=data.sort_order,
        description=data.description
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)

    return {"message": "权限创建成功", "permission_id": perm.id}


@router.put("/permissions/{permission_id}")
async def update_permission(permission_id: int, data: PermissionUpdate, db: Session = Depends(get_db)):
    """更新权限"""
    perm = db.query(Permission).filter(Permission.id == permission_id).first()
    if not perm:
        raise HTTPException(status_code=404, detail="权限不存在")

    update_data = data.model_dump(exclude_unset=True)

    if 'code' in update_data and update_data['code'] != perm.code:
        existing = db.query(Permission).filter(Permission.code == update_data['code']).first()
        if existing:
            raise HTTPException(status_code=400, detail="权限编码已存在")

    for key, value in update_data.items():
        setattr(perm, key, value)

    db.commit()
    return {"message": "权限更新成功"}


@router.delete("/permissions/{permission_id}")
async def delete_permission(permission_id: int, db: Session = Depends(get_db)):
    """删除权限"""
    perm = db.query(Permission).filter(Permission.id == permission_id).first()
    if not perm:
        raise HTTPException(status_code=404, detail="权限不存在")

    child_count = db.query(Permission).filter(Permission.parent_id == permission_id).count()
    if child_count > 0:
        raise HTTPException(status_code=400, detail=f"该权限下还有 {child_count} 个子权限，无法删除")

    db.query(RolePermission).filter(RolePermission.permission_id == permission_id).delete()
    db.delete(perm)
    db.commit()

    return {"message": "权限删除成功"}
