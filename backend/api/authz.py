"""常用鉴权依赖别名（路由 Depends 复用）。"""
from fastapi import Depends
from db.models import User
from api.deps import get_current_user, require_permissions

# --- 读权限 ---
RequireLogin = Depends(get_current_user)
RequireDashboard = Depends(require_permissions("dashboard:view"))
RequireMatchRead = Depends(require_permissions("match:upcoming", "match:finished", "match:jingcai_bf", "match:jingcai_bf_history", "match:jingcai_bf_summary", "jingcai:config", "match:manage"))
RequireJingcaiConfig = Depends(require_permissions("jingcai:config", "jingcai:manage"))
RequireLeagueRead = Depends(require_permissions("league:view", "league:manage", "league:config"))
RequireModelRead = Depends(require_permissions("model:manage", "dashboard:view"))
RequireProfile = Depends(require_permissions("profile:view"))

# --- 写 / 管理权限 ---
RequireMatchWrite = Depends(require_permissions("match:manage"))
RequireLeagueConfig = Depends(require_permissions("league:config"))
RequireModelManage = Depends(require_permissions("model:manage"))
RequireRiskManage = Depends(require_permissions("risk:manage"))
RequireScheduleManage = Depends(require_permissions("schedule:manage"))
RequireUserManage = Depends(require_permissions("user:manage"))
RequireUserCreate = Depends(require_permissions("user:create", "user:manage"))
RequireUserEdit = Depends(require_permissions("user:edit", "user:manage"))
RequireUserDelete = Depends(require_permissions("user:delete", "user:manage"))
RequireRoleManage = Depends(require_permissions("role:manage"))
RequirePredictionCalc = Depends(require_permissions("match:upcoming", "match:finished", "match:manage", "model:manage"))
RequirePredictionBatch = Depends(require_permissions("model:manage", "match:manage"))
