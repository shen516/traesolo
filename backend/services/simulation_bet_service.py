"""模拟投注单服务：创建 / 列表 / 详情 / 结算。

仅供学习、研究、数据分析，不构成投注建议，不接入真实资金。
所有金额为模拟数据，仅做展示与统计；结算以下单时刻 SP 为准。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from db.models import Match, SimulationBet, User
from services.prize_calculator import (
    BF_ALL_KEYS,
    PAYOUT_CAP_SINGLE,
    PAYOUT_MIN,
    TG_KEYS,
    _payout,
    _round2,
)

logger = logging.getLogger(__name__)

VALID_PLAY_TYPES = ("spf", "nspf", "bf", "tg", "hspf")
VALID_SOURCES = ("snapshot", "real", "synthetic", "manual")
SPF_SELECTIONS = ("win", "draw", "lose")
NSPF_SELECTIONS = ("win", "draw", "lose")


def _validate_selection(play_type: str, selection: str) -> bool:
    """按玩法校验选项 key 合法性（与 prize_calculator 选项空间一致）。"""
    if not selection:
        return False
    if play_type in ("spf", "nspf", "hspf"):
        return selection in SPF_SELECTIONS
    if play_type == "bf":
        return selection in BF_ALL_KEYS
    if play_type == "tg":
        return selection in TG_KEYS
    return False


def create_bet(
    db: Session,
    user: User,
    *,
    match_id: str,
    play_type: str,
    selection: str,
    sp: float,
    sp_source: str,
    stake: float = 2.0,
    multiple: int = 1,
) -> SimulationBet:
    """创建一行投注单。校验赛事为 upcoming、选项合法、参数边界。"""
    if play_type not in VALID_PLAY_TYPES:
        raise ValueError("无效玩法类型")
    if sp_source not in VALID_SOURCES:
        raise ValueError("无效 SP 来源")
    if not _validate_selection(play_type, selection):
        raise ValueError("无效投注选项")
    if sp is None or sp < 1.01:
        raise ValueError("SP 不能小于 1.01")
    if multiple is None or multiple < 1:
        raise ValueError("倍数不能小于 1")
    if multiple > 999:
        raise ValueError("倍数超出上限")
    if stake is None or stake < 2.0:
        raise ValueError("单注金额不能小于 2 元")
    if stake > 100000:
        raise ValueError("单注金额超出上限")

    match = db.query(Match).get(match_id)
    if not match:
        raise ValueError("赛事不存在")
    if match.status != "upcoming":
        raise ValueError("仅支持对未开赛赛事创建模拟投注单")

    # 防重复：同用户同赛事同玩法同选项的未作废投注单已存在则拒绝
    existing = (
        db.query(SimulationBet)
        .filter(
            SimulationBet.user_id == user.id,
            SimulationBet.match_id == match_id,
            SimulationBet.play_type == play_type,
            SimulationBet.selection == selection,
            SimulationBet.status != "void",
        )
        .first()
    )
    if existing:
        raise ValueError("该选项已加入模拟投注单，请勿重复提交")

    match_name = None
    home = getattr(match, "home_team", None)
    away = getattr(match, "away_team", None)
    if home and away:
        match_name = f"{home.name} vs {away.name}"

    bet = SimulationBet(
        user_id=user.id,
        match_id=match_id,
        match_no=match.match_no,
        match_name=match_name,
        play_type=play_type,
        selection=selection,
        sp_at_create=float(sp),
        sp_source_at_create=sp_source,
        stake=float(stake),
        multiple=int(multiple),
        status="pending",
        payout=0,
    )
    db.add(bet)
    db.commit()
    db.refresh(bet)
    return bet


def create_parlay(
    db: Session,
    user: User,
    *,
    legs: List[Dict[str, Any]],
    stake: float = 2.0,
    multiple: int = 1,
) -> List[SimulationBet]:
    """创建一组串关投注单（同 combination_id 多行共享，is_parlay=1）。

    legs: [{match_id, play_type, selection, sp, sp_source}]，2~8 项。
    单注 2 元 × 倍数；奖金整体结算（任一项未中 → 整组 lost）。
    返回创建的 leg 列表（按传入顺序）。
    """
    if not legs or len(legs) < 2:
        raise ValueError("串关至少需要 2 场赛事")
    if len(legs) > 8:
        raise ValueError("串关最多支持 8 场赛事")
    if stake is None or stake < 2.0:
        raise ValueError("单注金额不能小于 2 元")
    if stake > 100000:
        raise ValueError("单注金额超出上限")
    if multiple is None or multiple < 1:
        raise ValueError("倍数不能小于 1")
    if multiple > 999:
        raise ValueError("倍数超出上限")

    import uuid

    combination_id = f"pl_{uuid.uuid4().hex[:24]}"
    created = []
    for i, leg in enumerate(legs, start=1):
        match_id = leg.get("match_id")
        play_type = leg.get("play_type")
        selection = leg.get("selection")
        sp = leg.get("sp")
        sp_source = leg.get("sp_source")
        if play_type not in VALID_PLAY_TYPES:
            raise ValueError(f"第 {i} 项玩法类型无效")
        if not _validate_selection(play_type, selection):
            raise ValueError(f"第 {i} 项投注选项无效")
        if sp is None or sp < 1.01:
            raise ValueError(f"第 {i} 项 SP 不能小于 1.01")
        if sp_source not in VALID_SOURCES:
            raise ValueError(f"第 {i} 项 SP 来源无效")

        match = db.query(Match).get(match_id)
        if not match:
            raise ValueError(f"第 {i} 项赛事不存在")
        if match.status != "upcoming":
            raise ValueError(f"第 {i} 项赛事已开赛，无法投注")

        # 串关内同赛事不可重复（同玩法同选项），避免自相矛盾
        if any(
            c.match_id == match_id and c.play_type == play_type and c.selection == selection
            for c in created
        ):
            raise ValueError(f"第 {i} 项与串关内已有选项重复")

        match_name = None
        home = getattr(match, "home_team", None)
        away = getattr(match, "away_team", None)
        if home and away:
            match_name = f"{home.name} vs {away.name}"

        bet = SimulationBet(
            user_id=user.id,
            match_id=match_id,
            match_no=match.match_no,
            match_name=match_name,
            play_type=play_type,
            selection=selection,
            sp_at_create=float(sp),
            sp_source_at_create=sp_source,
            stake=float(stake),
            multiple=int(multiple),
            status="pending",
            payout=0,
            combination_id=combination_id,
            is_parlay=True,
        )
        db.add(bet)
        created.append(bet)
    db.commit()
    for b in created:
        db.refresh(b)
    return created


def list_bets(
    db: Session,
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    play_type: Optional[str] = None,
    match_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """投注单分页列表（本人）。date_from/date_to 按创建日期过滤（YYYY-MM-DD，含当天）。"""
    page = max(1, int(page or 1))
    page_size = max(1, min(100, int(page_size or 20)))

    q = db.query(SimulationBet).filter(SimulationBet.user_id == user.id)
    if status:
        q = q.filter(SimulationBet.status == status)
    if play_type:
        q = q.filter(SimulationBet.play_type == play_type)
    if match_id:
        q = q.filter(SimulationBet.match_id == match_id)
    if date_from:
        try:
            d0 = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(SimulationBet.created_at >= d0)
        except ValueError:
            pass
    if date_to:
        try:
            d1 = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            q = q.filter(SimulationBet.created_at <= d1)
        except ValueError:
            pass

    total = q.count()
    items = (
        q.order_by(SimulationBet.created_at.desc(), SimulationBet.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [bet_to_dict(b) for b in items],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
        },
    }


def get_bet(db: Session, user: User, bet_id: int) -> Optional[SimulationBet]:
    bet = db.query(SimulationBet).get(bet_id)
    if not bet or bet.user_id != user.id:
        return None
    return bet


def void_bet(db: Session, user: User, bet_id: int) -> Optional[SimulationBet]:
    """开赛前整单作废（status → void）。仅允许 pending 状态、且赛事未开赛。

    符合 §5.3.3 与 §12-9：取消需在开赛前，仅限整单作废，不支持改选。
    作废后该选项可重新提交（防重复检查排除 void）。

    串关组合（is_parlay=1）按 combination_id **整组作废**：任一腿赛事已开赛
    则整组不可作废；作废后整组状态统一为 void。
    """
    bet = get_bet(db, user, bet_id)
    if not bet:
        return None
    if bet.status != "pending":
        raise ValueError("仅待开赛状态可作废")

    # 串关：整组作废
    if bet.is_parlay and bet.combination_id:
        group = (
            db.query(SimulationBet)
            .filter(
                SimulationBet.user_id == user.id,
                SimulationBet.combination_id == bet.combination_id,
            )
            .all()
        )
        for b in group:
            if b.status != "pending":
                raise ValueError("串关组合已有结算项，不可作废")
            m = db.query(Match).filter(Match.id == b.match_id).first()
            if m and m.status != "upcoming":
                raise ValueError("串关内赛事已开赛或已结束，不可作废")
        for b in group:
            b.status = "void"
            note = (b.settle_note or "") + "；用户手动作废（开赛前）" if b.settle_note else "用户手动作废（开赛前）"
            b.settle_note = note
        db.commit()
        db.refresh(bet)
        return bet

    match = db.query(Match).filter(Match.id == bet.match_id).first()
    if match and match.status != "upcoming":
        raise ValueError("赛事已开赛或已结束，不可作废")
    bet.status = "void"
    bet.settle_note = (bet.settle_note or "") + "；用户手动作废（开赛前）" if bet.settle_note else "用户手动作废（开赛前）"
    db.commit()
    db.refresh(bet)
    return bet


def bet_to_dict(bet: SimulationBet) -> Dict[str, Any]:
    return {
        "id": bet.id,
        "user_id": bet.user_id,
        "match_id": bet.match_id,
        "match_no": bet.match_no,
        "match_name": bet.match_name,
        "play_type": bet.play_type,
        "selection": bet.selection,
        "sp_at_create": float(bet.sp_at_create or 0),
        "sp_source_at_create": bet.sp_source_at_create,
        "stake": float(bet.stake or 0),
        "multiple": bet.multiple,
        "status": bet.status,
        "payout": float(bet.payout or 0),
        "combination_id": bet.combination_id,
        "is_parlay": bool(bet.is_parlay),
        "settle_note": bet.settle_note,
        "settled_at": bet.settled_at.strftime("%Y-%m-%d %H:%M") if bet.settled_at else None,
        "created_at": bet.created_at.strftime("%Y-%m-%d %H:%M") if bet.created_at else None,
    }


def _payout_capped(sp: float, multiple: int) -> float:
    """单关单注奖金 = 2 × SP × 倍数，截断至单关封顶。"""
    amount = _payout(sp) * int(multiple or 1)
    return round(min(amount, PAYOUT_CAP_SINGLE), 2)


def _hit_spf(result: str, selection: str) -> bool:
    """赛果 result(H/A/D) → spf/nspf 选项命中。"""
    m = {"H": "win", "A": "lose", "D": "draw"}
    return m.get(result) == selection


def _hit_bf(home_goals: int, away_goals: int, selection: str) -> bool:
    """精确比分命中。"""
    if selection == "胜其它":
        return home_goals - away_goals > 0 and f"{home_goals}:{away_goals}" not in BF_ALL_KEYS
    if selection == "平其它":
        return home_goals == away_goals and f"{home_goals}:{away_goals}" not in BF_ALL_KEYS
    if selection == "负其它":
        return home_goals - away_goals < 0 and f"{home_goals}:{away_goals}" not in BF_ALL_KEYS
    return selection == f"{home_goals}:{away_goals}"


def _hit_tg(home_goals: int, away_goals: int, selection: str) -> bool:
    """总进球区间命中。"""
    total = home_goals + away_goals
    if selection == "7+":
        return total >= 7
    try:
        return total == int(selection)
    except ValueError:
        return False


def _hit(bet: SimulationBet, match: Match) -> bool:
    """按玩法将实际赛果映射到选项，判断命中。"""
    result = match.result
    hg = int(match.home_goals or 0)
    ag = int(match.away_goals or 0)
    if bet.play_type in ("spf", "nspf"):
        return _hit_spf(result, bet.selection)
    if bet.play_type == "bf":
        return _hit_bf(hg, ag, bet.selection)
    if bet.play_type == "tg":
        return _hit_tg(hg, ag, bet.selection)
    if bet.play_type == "hspf":
        return _hit_hspf(bet.selection, match)
    return False


def _hit_hspf(selection: str, match: Match) -> bool:
    """半场胜平负命中判定：解析 match.half_score（"H - A" 或 "H-A"）。

    命中需半场赛果（H/A/D）与选项一致；半场赛果缺失则抛 ValueError 触发失败计数。
    """
    if selection not in ("win", "draw", "lose"):
        raise ValueError(f"hspf 选项不合法: {selection}")
    raw = (match.half_score or "").strip()
    if not raw:
        raise ValueError("半场比分缺失，无法判定半场胜平负")
    parts = [p for p in raw.replace(" ", "").split("-") if p != ""]
    if len(parts) != 2:
        raise ValueError(f"半场比分格式异常: {raw}")
    try:
        hg = int(parts[0])
        ag = int(parts[1])
    except ValueError:
        raise ValueError(f"半场比分解析失败: {raw}")
    if hg > ag:
        outcome = "win"
    elif hg < ag:
        outcome = "lose"
    else:
        outcome = "draw"
    return outcome == selection


# 结算连续失败阈值：赛果缺失/解析异常累计达到该次数后置 void
SETTLE_FAIL_MAX = 3


def _score_key(hg, ag) -> str:
    return f"{hg}:{ag}"


def settle_bet(db: Session, bet: SimulationBet, match: Match) -> bool:
    """结算单张投注单。返回是否发生了状态变更（幂等）。

    - pending + 赛事 finished + 赛果齐全 → 命中/未中；
    - 赛果缺失/解析异常 → 计数 settle_fail_count，累计达 SETTLE_FAIL_MAX 置 void；
    - 已结算投注单若赛果快照与当前赛果不一致（改判）→ 置 void 并提示。
    """
    if match.status != "finished":
        return False
    if match.result is None or match.home_goals is None or match.away_goals is None:
        # 赛果缺失：保持 pending，累计失败计数，达阈值置 void
        if bet.status == "pending":
            bet.settle_fail_count = int(bet.settle_fail_count or 0) + 1
            if bet.settle_fail_count >= SETTLE_FAIL_MAX:
                bet.status = "void"
                bet.settle_note = f"赛果缺失，连续 {bet.settle_fail_count} 次结算失败已作废"
                bet.settled_at = datetime.now()
            db.commit()
        return False

    current_key = _score_key(int(match.home_goals), int(match.away_goals))

    # 已结算：检测赛果改判（最新赛果与结算时快照不一致）
    if bet.status in ("won", "lost", "void"):
        if bet.settle_score_snapshot and bet.settle_score_snapshot != current_key:
            bet.status = "void"
            bet.payout = 0
            bet.settle_note = "赛果更新，已重结算"
            # 快照同步为最新赛果，避免后续再次改判时被旧的结算快照误判
            bet.settle_score_snapshot = current_key
            db.commit()
            return True
        return False

    if bet.status != "pending":
        return False

    try:
        won = _hit(bet, match)
    except Exception as e:
        logger.warning("Settle bet %s failed to evaluate: %s", bet.id, e)
        bet.settle_fail_count = int(bet.settle_fail_count or 0) + 1
        if bet.settle_fail_count >= SETTLE_FAIL_MAX:
            bet.status = "void"
            bet.settle_note = "结算解析异常，连续失败已作废"
            bet.settled_at = datetime.now()
        db.commit()
        return False

    if won:
        bet.payout = _payout_capped(float(bet.sp_at_create or 0), bet.multiple)
        bet.status = "won"
        bet.settle_note = "命中"
    else:
        bet.payout = 0
        bet.status = "lost"
        bet.settle_note = "未中"
    bet.settle_score_snapshot = current_key
    bet.settled_at = datetime.now()
    db.commit()
    return True


def settle_pending(db: Session) -> Dict[str, Any]:
    """扫描待结算（pending）与已结算（won/lost/void，用于改判检测）且赛事 finished 的投注单。

    幂等：pending 命中/未中；已结算且赛果变化 → void 改判。
    串关（is_parlay=1）按 combination_id 分组整体结算：
      - 任一 leg 未中 → 整组 lost；
      - 全部命中 → 整组 won，奖金 = min(2 × ∏sp × multiple, PAYOUT_CAP_PARLAY)。
    """
    rows = (
        db.query(SimulationBet)
        .filter(SimulationBet.status.in_(("pending", "won", "lost", "void")))
        .all()
    )
    # 先单关；再按组合分组的串关
    single = [b for b in rows if not b.is_parlay]
    parlay_rows = [b for b in rows if b.is_parlay]
    settled = 0
    skipped = 0

    # 1) 单关逐行
    for bet in single:
        match = db.query(Match).get(bet.match_id)
        if not match:
            continue
        if match.status != "finished":
            continue
        if match.result is None or match.home_goals is None or match.away_goals is None:
            if bet.status == "pending":
                settle_bet(db, bet, match)
                skipped += 1
            continue
        if settle_bet(db, bet, match):
            settled += 1

    # 2) 串关按组合分组整体结算
    groups: Dict[str, List[SimulationBet]] = {}
    for b in parlay_rows:
        groups.setdefault(b.combination_id or f"_leg_{b.id}", []).append(b)
    for cid, legs in groups.items():
        r = _settle_parlay_group(db, cid, legs)
        settled += r["settled"]
        skipped += r["skipped"]
    return {"settled": settled, "skipped": skipped}


def _settle_parlay_group(db: Session, cid: str, legs: List[SimulationBet]) -> Dict[str, Any]:
    """串关组合整体结算（幂等）。

    仅当组合内所有 leg 的赛事均已 finished 且有赛果时才结算；
    任一赛事赛果缺失 → 全部保持 pending 并计数失败，达 SETTLE_FAIL_MAX 置 void。
    已结算组合若任一赛事赛果改判 → 整组置 void。
    """
    settled = 0
    skipped = 0
    from services.parlay_calculator import PAYOUT_CAP_PARLAY

    # 分组内所有 leg 共享同一 multiple / combination_id（以第一条为准）
    first = legs[0]
    multiple = int(first.multiple or 1)
    already_settled = any(b.status in ("won", "lost", "void") for b in legs)

    # 收集各组内赛事
    matches = {}
    for b in legs:
        m = db.query(Match).get(b.match_id)
        matches[b.match_id] = m

    # 任一赛事赛果缺失/异常
    incomplete = []
    for b in legs:
        m = matches.get(b.match_id)
        if not m or m.status != "finished":
            incomplete.append(b)
            continue
        if m.result is None or m.home_goals is None or m.away_goals is None:
            incomplete.append(b)
    # 半场玩法需半场比分；缺失视作待定（交由逐 leg 评估抛 ValueError 处理）
    if incomplete:
        if already_settled:
            return {"settled": 0, "skipped": 0}
        # 全组 pending：计数失败
        for b in legs:
            if b.status == "pending":
                b.settle_fail_count = int(b.settle_fail_count or 0) + 1
                if b.settle_fail_count >= SETTLE_FAIL_MAX:
                    b.status = "void"
                    b.settle_note = "赛果缺失，连续失败已作废"
                    b.settled_at = datetime.now()
        db.commit()
        return {"settled": 0, "skipped": len(incomplete)}

    # 检测改判：任一已结算 leg 的赛果快照与当前赛果不一致 → 整组 void
    if already_settled:
        changed = False
        for b in legs:
            m = matches[b.match_id]
            cur = _score_key(int(m.home_goals), int(m.away_goals))
            if b.settle_score_snapshot and b.settle_score_snapshot != cur:
                changed = True
                break
        if changed:
            for b in legs:
                b.status = "void"
                b.payout = 0
                b.settle_note = "赛果更新，已重结算（串关整组作废）"
                b.settle_score_snapshot = _score_key(
                    int(matches[b.match_id].home_goals), int(matches[b.match_id].away_goals)
                )
                b.settled_at = datetime.now()
            db.commit()
            return {"settled": len(legs), "skipped": 0}
        return {"settled": 0, "skipped": 0}

    # 待结算：评估每个 leg
    leg_hits = []
    leg_error = False
    for b in legs:
        try:
            leg_hits.append(_hit(b, matches[b.match_id]))
        except Exception as e:
            logger.warning("Parlay leg %s settle failed: %s", b.id, e)
            leg_error = True
            break
    if leg_error:
        for b in legs:
            if b.status == "pending":
                b.settle_fail_count = int(b.settle_fail_count or 0) + 1
                if b.settle_fail_count >= SETTLE_FAIL_MAX:
                    b.status = "void"
                    b.settle_note = "结算解析异常，连续失败已作废"
                    b.settled_at = datetime.now()
        db.commit()
        return {"settled": 0, "skipped": len(legs)}

    all_hit = all(leg_hits)
    # 组合赛果快照（用于改判检测）：以第一条 leg 的比分键为准
    snap_match = matches[legs[0].match_id]
    snap_key = _score_key(int(snap_match.home_goals), int(snap_match.away_goals))
    if all_hit:
        prod = 1.0
        for b in legs:
            prod *= float(b.sp_at_create or 0)
        payout = _round2(min(2.0 * prod * multiple, PAYOUT_CAP_PARLAY))
        for b in legs:
            b.status = "won"
            b.payout = payout
            b.settle_note = "命中（串关）"
            b.settle_score_snapshot = snap_key
            b.settled_at = datetime.now()
        db.commit()
        return {"settled": len(legs), "skipped": 0}
    else:
        for b in legs:
            b.status = "lost"
            b.payout = 0
            b.settle_note = "未中（串关任一关未中）"
            b.settle_score_snapshot = snap_key
            b.settled_at = datetime.now()
        db.commit()
        return {"settled": len(legs), "skipped": 0}


def settle_task() -> Dict[str, Any]:
    """定时结算任务入口（进程内调用）。"""
    from db.database import SessionLocal
    db = SessionLocal()
    try:
        return settle_pending(db)
    except Exception as e:
        logger.warning("Settle task error: %s", e)
        return {"settled": 0, "skipped": 0, "error": str(e)}
    finally:
        db.close()


def stats_for_user(db: Session, user: User) -> Dict[str, Any]:
    """本人累计模拟盈亏统计。

    串关组合（is_parlay=1）以 combination_id 为统计单元：组合内多行只计一次
    stake/payout/结果，避免重复统计。
    """
    rows = db.query(SimulationBet).filter(SimulationBet.user_id == user.id).all()
    total_stake = 0.0
    total_payout = 0.0
    settled = 0
    won = 0
    counted_combos = set()
    for b in rows:
        if b.is_parlay:
            cid = b.combination_id or f"_leg_{b.id}"
            if cid in counted_combos:
                continue
            counted_combos.add(cid)
        if b.status == "pending":
            continue
        total_stake += float(b.stake or 0) * int(b.multiple or 1)
        total_payout += float(b.payout or 0)
        settled += 1
        if b.status == "won":
            won += 1
    return {
        "total_stake": round(total_stake, 2),
        "total_payout": round(total_payout, 2),
        "profit": round(total_payout - total_stake, 2),
        "settled": settled,
        "won": won,
        "hit_rate": round(won / settled, 4) if settled else None,
    }
