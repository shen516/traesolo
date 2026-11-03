"""订阅服务：套餐定义、权益解析、开通/续费/取消、到期检查与字段级门控掩码"""
import json
import logging
import time
from datetime import date, timedelta
from typing import Optional, Set

from sqlalchemy.orm import Session

from db.models import User, SubscriptionPlan, SubscriptionRecord

logger = logging.getLogger(__name__)

# ===== 权益码 =====
FEATURE_PREDICTION_BASIC = "prediction:basic"
FEATURE_PREDICTION_FULL = "prediction:full"
FEATURE_PREDICTION_XG = "prediction:xg"
FEATURE_JINGCAI_BF = "jingcai:bf"
FEATURE_ODDS_SNAPSHOT = "odds:snapshot"
FEATURE_RISK_DETAIL = "risk:detail"
FEATURE_HISTORY_DEEP = "history:deep"

FREE_FEATURES = [FEATURE_PREDICTION_BASIC]
PRO_FEATURES = FREE_FEATURES + [
    FEATURE_PREDICTION_FULL,
    FEATURE_JINGCAI_BF,
    FEATURE_ODDS_SNAPSHOT,
    FEATURE_HISTORY_DEEP,
]
FLAG_FEATURES = PRO_FEATURES + [FEATURE_PREDICTION_XG, FEATURE_RISK_DETAIL]
ALL_FEATURES = list(dict.fromkeys(FLAG_FEATURES))

FEATURE_LABELS = {
    FEATURE_PREDICTION_BASIC: "基础胜平负预测",
    FEATURE_PREDICTION_FULL: "完整预测（备选比分/矩阵/关键变量/分析）",
    FEATURE_PREDICTION_XG: "xG 明细与融合权重",
    FEATURE_JINGCAI_BF: "竞彩比分 SP 全表",
    FEATURE_ODDS_SNAPSHOT: "赔率时序快照",
    FEATURE_RISK_DETAIL: "风控预警详情",
    FEATURE_HISTORY_DEEP: "历史赛事深度数据",
}

TIER_RANK = {"free": 0, "pro": 1, "flagship": 2}

PLAN_SEEDS = [
    {"code": "free", "name": "免费版", "tier": "free", "duration_days": 0, "price": 0,
     "features": FREE_FEATURES, "sort_order": 0, "description": "基础胜平负预测与赛事浏览"},
    {"code": "pro_month", "name": "专业版·月付", "tier": "pro", "duration_days": 30, "price": 29,
     "features": PRO_FEATURES, "sort_order": 1, "description": "完整预测字段、竞彩比分、赔率快照、历史深度数据"},
    {"code": "pro_quarter", "name": "专业版·季付", "tier": "pro", "duration_days": 90, "price": 79,
     "features": PRO_FEATURES, "sort_order": 2, "description": "完整预测字段、竞彩比分、赔率快照、历史深度数据"},
    {"code": "pro_year", "name": "专业版·年付", "tier": "pro", "duration_days": 365, "price": 299,
     "features": PRO_FEATURES, "sort_order": 3, "description": "完整预测字段、竞彩比分、赔率快照、历史深度数据"},
    {"code": "flag_month", "name": "旗舰版·月付", "tier": "flagship", "duration_days": 30, "price": 59,
     "features": FLAG_FEATURES, "sort_order": 4, "description": "含专业版全部权益，另加 xG 明细与风控详情"},
    {"code": "flag_quarter", "name": "旗舰版·季付", "tier": "flagship", "duration_days": 90, "price": 159,
     "features": FLAG_FEATURES, "sort_order": 5, "description": "含专业版全部权益，另加 xG 明细与风控详情"},
    {"code": "flag_year", "name": "旗舰版·年付", "tier": "flagship", "duration_days": 365, "price": 599,
     "features": FLAG_FEATURES, "sort_order": 6, "description": "含专业版全部权益，另加 xG 明细与风控详情"},
]

# 历史遗留 plan 值 → 新套餐码
LEGACY_PLAN_MAP = {"professional": "pro_year", "flagship": "flag_year"}

# ===== 套餐查询（带短 TTL 缓存，避免每请求查库） =====
_plans_cache = {"ts": 0.0, "rows": []}
_PLANS_CACHE_TTL = 300


def _parse_features(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []


def seed_subscription_plans(db: Session) -> None:
    """幂等写入套餐种子数据；已有行同步名称/时长/权益等字段。"""
    for seed in PLAN_SEEDS:
        existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.code == seed["code"]).first()
        payload = {
            "name": seed["name"],
            "tier": seed["tier"],
            "duration_days": seed["duration_days"],
            "price": seed["price"],
            "features_json": json.dumps(seed["features"], ensure_ascii=False),
            "description": seed["description"],
            "sort_order": seed["sort_order"],
        }
        if not existing:
            db.add(SubscriptionPlan(code=seed["code"], is_active=True, **payload))
        else:
            for field, value in payload.items():
                setattr(existing, field, value)
    db.commit()
    _plans_cache["ts"] = 0.0  # 种子变更后失效缓存


def migrate_legacy_plans(db: Session) -> None:
    """把 users 表里的旧 plan 值映射到新套餐码。"""
    users = db.query(User).filter(User.subscription_plan.in_(list(LEGACY_PLAN_MAP))).all()
    for u in users:
        u.subscription_plan = LEGACY_PLAN_MAP.get(u.subscription_plan) or "free"
        if u.subscription_status == "active" and not u.subscription_expire:
            # 旧数据无到期日：给一个长周期，避免误伤
            u.subscription_expire = date.today() + timedelta(days=3650)
    # 免费版快照应对齐为 active + 无到期日
    free_users = db.query(User).filter(
        User.subscription_plan == "free",
        User.subscription_status != "active",
    ).all()
    for u in free_users:
        u.subscription_status = "active"
        u.subscription_expire = None
    if users or free_users:
        db.commit()
        logger.info(
            "Subscription: migrated %s legacy plan rows, %s free rows",
            len(users), len(free_users),
        )


def list_plans(db: Session, only_active: bool = True):
    query = db.query(SubscriptionPlan).order_by(SubscriptionPlan.sort_order)
    if only_active:
        query = query.filter(SubscriptionPlan.is_active == True)
    return query.all()


def _all_plans_cached(db: Session):
    now = time.time()
    if now - _plans_cache["ts"] < _PLANS_CACHE_TTL and _plans_cache["rows"]:
        return _plans_cache["rows"]
    rows = db.query(SubscriptionPlan).all()
    _plans_cache["ts"] = now
    _plans_cache["rows"] = rows
    return rows


def get_plan(db: Session, code: str) -> Optional[SubscriptionPlan]:
    for row in _all_plans_cached(db):
        if row.code == code:
            return row
    return None


def all_features(db: Session) -> Set[str]:
    """全量权益码（DB 套餐并集，空表时回退到种子常量）。"""
    feats = set()
    for row in _all_plans_cached(db):
        feats.update(_parse_features(row.features_json))
    return feats or set(ALL_FEATURES)


# ===== 用户订阅状态解析 =====

def lazy_expire_user(db: Session, user: User) -> bool:
    """懒过期：active 但到期日已过 → 落库 expired。返回是否发生了翻转。

    免费版 expire 为 NULL，不会被误判。
    """
    if not user:
        return False
    if user.subscription_status != "active":
        return False
    expire = user.subscription_expire
    if not expire:
        return False
    if expire >= date.today():
        return False
    try:
        user.subscription_status = "expired"
        db.query(SubscriptionRecord).filter(
            SubscriptionRecord.user_id == user.id,
            SubscriptionRecord.status == "active",
        ).update({"status": "expired"}, synchronize_session=False)
        db.commit()
        logger.info("Subscription: user %s expired (lazy)", user.id)
        return True
    except Exception as e:
        db.rollback()
        logger.warning("Subscription: lazy expire failed for user %s: %s", user.id, e)
        return False


def get_user_features(db: Session, user: User) -> Set[str]:
    """解析用户当前有效权益码集合（含懒过期检查）。"""
    if not user:
        return set(FREE_FEATURES)
    lazy_expire_user(db, user)
    plan_code = user.subscription_plan or "free"
    plan = get_plan(db, plan_code)
    if not plan or plan.tier == "free":
        return set(FREE_FEATURES)
    if user.subscription_status != "active":
        return set(FREE_FEATURES)
    feats = set(_parse_features(plan.features_json))
    return feats or set(FREE_FEATURES)


def get_user_subscription(db: Session, user: User) -> dict:
    """个人中心/前端展示用的订阅快照。"""
    lazy_expire_user(db, user)
    plan_code = user.subscription_plan or "free"
    plan = get_plan(db, plan_code)
    tier = plan.tier if plan else "free"
    features = sorted(get_user_features(db, user))
    remaining_days = None
    if user.subscription_expire and user.subscription_status == "active":
        remaining_days = max(0, (user.subscription_expire - date.today()).days + 1)
    # 免费版不限时长，展示层恒为 active
    display_status = "active" if tier == "free" else user.subscription_status
    return {
        "plan_code": plan_code,
        "plan_name": plan.name if plan else plan_code,
        "tier": tier,
        "status": display_status,
        "expire_date": user.subscription_expire.isoformat() if user.subscription_expire else None,
        "remaining_days": remaining_days,
        "features": features,
        "feature_labels": {code: FEATURE_LABELS.get(code, code) for code in features},
    }


# ===== 开通 / 续费 / 取消 =====

def grant(db: Session, user_id: int, plan_code: str, operator_id: Optional[int] = None,
          note: Optional[str] = None) -> SubscriptionRecord:
    """开通/续费/变更套餐。

    - 同档续费：到期日顺延叠加（max(今天, 当前到期) + 时长）
    - 升级：立即生效，到期日 = 今天 + 时长
    - 降档：立即生效，到期日保持原值（仍有效时）
    - free：到期日置空、状态 active
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("用户不存在")
    plan = get_plan(db, plan_code)
    if not plan:
        raise ValueError("套餐不存在")
    if not plan.is_active:
        raise ValueError("套餐已下架")

    today = date.today()
    old_plan = get_plan(db, user.subscription_plan or "free")
    old_tier = old_plan.tier if old_plan else "free"
    duration = int(plan.duration_days or 0)

    if duration <= 0:
        new_expire = None
    else:
        currently_valid = (
            user.subscription_status == "active"
            and user.subscription_expire
            and user.subscription_expire >= today
        )
        same_tier = old_tier == plan.tier
        is_downgrade = TIER_RANK.get(plan.tier, 0) < TIER_RANK.get(old_tier, 0)
        if same_tier and currently_valid:
            new_expire = user.subscription_expire + timedelta(days=duration)
        elif is_downgrade and currently_valid:
            new_expire = user.subscription_expire
        else:
            new_expire = today + timedelta(days=duration)

    # 旧 active 流水全部关闭，保持任一时刻至多一条 active
    db.query(SubscriptionRecord).filter(
        SubscriptionRecord.user_id == user_id,
        SubscriptionRecord.status == "active",
    ).update({"status": "expired"}, synchronize_session=False)

    record = SubscriptionRecord(
        user_id=user_id,
        plan_code=plan.code,
        start_date=today,
        end_date=new_expire,
        status="active",
        source="admin_grant",
        operator_id=operator_id,
        note=note,
    )
    db.add(record)

    user.subscription_plan = plan.code
    user.subscription_status = "active"
    user.subscription_expire = new_expire
    db.commit()
    db.refresh(record)
    logger.info(
        "Subscription: granted %s to user %s by %s (expire=%s)",
        plan.code, user_id, operator_id, new_expire,
    )
    return record


def cancel(db: Session, user_id: int, operator_id: Optional[int] = None,
           note: Optional[str] = None) -> None:
    """取消订阅：快照置 cancelled，权益回落到免费版。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("用户不存在")
    db.query(SubscriptionRecord).filter(
        SubscriptionRecord.user_id == user_id,
        SubscriptionRecord.status == "active",
    ).update({"status": "cancelled"}, synchronize_session=False)
    user.subscription_status = "cancelled"
    db.commit()
    logger.info("Subscription: cancelled user %s by %s (%s)", user_id, operator_id, note or "")


def list_records(db: Session, user_id: Optional[int] = None, page: int = 1, page_size: int = 20):
    query = db.query(SubscriptionRecord)
    if user_id is not None:
        query = query.filter(SubscriptionRecord.user_id == user_id)
    total = query.count()
    rows = query.order_by(SubscriptionRecord.created_at.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return total, rows


def record_to_dict(record: SubscriptionRecord) -> dict:
    return {
        "id": record.id,
        "user_id": record.user_id,
        "username": record.user.username if record.user else None,
        "plan_code": record.plan_code,
        "plan_name": record.plan.name if record.plan else record.plan_code,
        "start_date": record.start_date.isoformat() if record.start_date else None,
        "end_date": record.end_date.isoformat() if record.end_date else None,
        "status": record.status,
        "source": record.source,
        "operator_id": record.operator_id,
        "operator_name": record.operator.username if record.operator else None,
        "note": record.note,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


# ===== 到期批量检查（定时任务） =====

def expire_overdue(db: Session) -> dict:
    """批量把到期订阅置为 expired（懒检查之外的兜底）。"""
    from sqlalchemy import text
    try:
        db.execute(text("SET SESSION lock_wait_timeout = 5"))
    except Exception:
        pass
    today = date.today()
    users_n = db.query(User).filter(
        User.subscription_status == "active",
        User.subscription_expire.isnot(None),
        User.subscription_expire < today,
    ).update({"subscription_status": "expired"}, synchronize_session=False)
    records_n = db.query(SubscriptionRecord).filter(
        SubscriptionRecord.status == "active",
        SubscriptionRecord.end_date.isnot(None),
        SubscriptionRecord.end_date < today,
    ).update({"status": "expired"}, synchronize_session=False)
    db.commit()
    return {"users_expired": users_n, "records_expired": records_n}


def expire_overdue_subscriptions_task():
    """调度器入口（无参，自开会话）。"""
    from db.database import SessionLocal
    db = SessionLocal()
    try:
        result = expire_overdue(db)
        if result["users_expired"] or result["records_expired"]:
            logger.info("Subscription expire check: %s", result)
        else:
            logger.debug("Subscription expire check: nothing to expire")
    except Exception as e:
        db.rollback()
        logger.error("Subscription expire check failed: %s", e)
    finally:
        db.close()


# ===== 字段级门控掩码 =====

# 预测字段 → 权益码（full=深度结论；xg=融合/xG 明细）
PREDICTION_FIELD_MAP = {
    "alt_scores": FEATURE_PREDICTION_FULL,
    "score_matrix": FEATURE_PREDICTION_FULL,
    "key_variables": FEATURE_PREDICTION_FULL,
    "analysis": FEATURE_PREDICTION_FULL,
    "scenarios": FEATURE_PREDICTION_FULL,
    "ensemble_probs": FEATURE_PREDICTION_FULL,
    "scenario_order": FEATURE_PREDICTION_FULL,
    "xg_home": FEATURE_PREDICTION_XG,
    "xg_away": FEATURE_PREDICTION_XG,
    "xg_coverage": FEATURE_PREDICTION_XG,
    "weights_used": FEATURE_PREDICTION_XG,
    "weight_source": FEATURE_PREDICTION_XG,
    "elo_home": FEATURE_PREDICTION_XG,
    "elo_away": FEATURE_PREDICTION_XG,
    "hyperparams_used": FEATURE_PREDICTION_XG,
    "env_adjust": FEATURE_PREDICTION_XG,
    "soft_priors": FEATURE_PREDICTION_XG,
    "espn_pipeline": FEATURE_PREDICTION_XG,
}

RISK_ALERT_FIELD_MAP = {
    "description": FEATURE_RISK_DETAIL,
    "recommended_action": FEATURE_RISK_DETAIL,
}

# 竞彩比分免费版可见的「其它」键
BF_FREE_KEYS = ("胜其它", "平其它", "负其它")


def mask_fields(payload: dict, entitlements: Set[str], field_map: dict) -> dict:
    """无权益字段置 None，并在 payload['locked_fields'] 记录（掩码而非剔除）。

    即使字段原本缺失也会写入 None + locked_fields，方便前端原位渲染锁标。
    """
    if not isinstance(payload, dict) or not field_map:
        return payload
    locked = []
    for field, feature in field_map.items():
        if feature in entitlements:
            continue
        payload[field] = None
        locked.append(field)
    if locked:
        existing = payload.get("locked_fields") or []
        payload["locked_fields"] = sorted(set(existing) | set(locked))
    return payload


def mask_prediction(prediction: dict, entitlements: Set[str]) -> dict:
    return mask_fields(prediction, entitlements, PREDICTION_FIELD_MAP)


def mask_prediction_list(items: list, entitlements: Set[str]) -> list:
    if not items:
        return items
    return [mask_prediction(item, entitlements) if isinstance(item, dict) else item for item in items]


def mask_odds_bf(odds_bf, entitlements: Set[str]):
    """竞彩比分 SP：免费版仅保留胜/平/负其它三项。返回 (masked, locked)。"""
    if not isinstance(odds_bf, dict):
        return odds_bf, False
    if FEATURE_JINGCAI_BF in entitlements:
        return odds_bf, False
    masked = {k: v for k, v in odds_bf.items() if k in BF_FREE_KEYS}
    return masked, len(masked) < len(odds_bf)


def mask_score_top3_list(items: list, entitlements: Set[str]) -> list:
    """竞彩比分 Top3：与比分 SP 同权益，免费版仅保留第 1 个比分。"""
    if not items or FEATURE_JINGCAI_BF in entitlements:
        return items
    for item in items:
        if not isinstance(item, dict):
            continue
        top = item.get("top3") or []
        if len(top) > 1:
            item["top3"] = top[:1]
            item["top3_locked"] = True
            if "hit" in item:
                item["hit"] = None
    return items


def mask_match_list(items: list, entitlements: Set[str]) -> list:
    """列表序列化出口的统一门控：odds_bf 部分掩码 + 预测字段掩码。"""
    if not items:
        return items
    for item in items:
        if not isinstance(item, dict):
            continue
        if "odds_bf" in item:
            masked, locked = mask_odds_bf(item.get("odds_bf"), entitlements)
            item["odds_bf"] = masked
            if locked:
                item["odds_bf_locked"] = True
        pred = item.get("prediction")
        if isinstance(pred, dict):
            mask_prediction(pred, entitlements)
    return items


def mask_risk_alerts(alerts: list, entitlements: Set[str]) -> list:
    if not alerts:
        return alerts
    for alert in alerts:
        if isinstance(alert, dict):
            mask_fields(alert, entitlements, RISK_ALERT_FIELD_MAP)
    return alerts
