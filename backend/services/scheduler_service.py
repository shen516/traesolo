"""定时任务调度服务 - 状态持久化到数据库

设计：
- 任务元信息（func、默认间隔、名称等）通过 register_task() 在应用启动时注册到内存。
- enable/disable 时同步写入 scheduled_task_status 表。
- 应用重启时调用 restore_from_db() 从数据库读取状态：
  - is_enabled=True 的任务自动恢复运行
  - is_enabled=False 的任务保持停止
"""
import schedule
import threading
import time
import logging
from datetime import datetime
from typing import Callable, Optional, Dict

from db.database import SessionLocal
from db.models import ScheduledTaskStatus

logger = logging.getLogger(__name__)


class SchedulerService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._running = False
        self._thread = None
        # 内存中正在运行的任务
        self._tasks: Dict[str, dict] = {}
        # 任务元信息注册表（不参与调度，仅记录以便恢复）
        self._registry: Dict[str, dict] = {}
        self._initialized = True

    # ===== 调度器线程控制 =====
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self._thread.start()
        logger.info("Scheduler service started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler service stopped")

    def _run_scheduler(self):
        while self._running:
            schedule.run_pending()
            time.sleep(1)

    # ===== 任务元信息注册 =====
    def register_task(self, task_id: str, func: Callable, default_interval: int,
                      name: str = "", category: str = "", description: str = ""):
        """注册任务元信息（不启动任务，仅记录到内存注册表）"""
        self._registry[task_id] = {
            'func': func,
            'default_interval': default_interval,
            'name': name or task_id,
            'category': category,
            'description': description,
        }
        logger.info(f"Registered task: {task_id} ({name})")

    # ===== 任务调度管理 =====
    def is_task_enabled(self, task_id: str) -> bool:
        """是否已启用：内存在跑，或以 DB is_enabled 为准。"""
        if task_id in self._tasks:
            return True
        db = SessionLocal()
        try:
            status = db.query(ScheduledTaskStatus).filter(
                ScheduledTaskStatus.task_id == task_id
            ).first()
            return bool(status and status.is_enabled)
        except Exception as e:
            logger.debug("is_task_enabled(%s) failed: %s", task_id, e)
            return False
        finally:
            db.close()

    def add_interval_task(self, task_id: str, func: Callable, interval_minutes: int):
        """启用间隔任务并持久化为 enabled=True"""
        from services.scheduled_tasks import RETIRED_TASK_IDS

        if task_id in RETIRED_TASK_IDS:
            raise ValueError(f"Task '{task_id}' is retired and cannot be scheduled")
        if task_id not in self._registry:
            self._registry[task_id] = {
                'func': func,
                'default_interval': interval_minutes,
                'name': task_id,
                'category': 'unknown',
                'description': '',
            }
            logger.warning(
                "Task %s was not pre-registered at startup; auto-registered from API call",
                task_id,
            )
        self._add_task_to_schedule(task_id, func, interval_minutes)
        self._persist_status(task_id, is_enabled=True, interval_minutes=interval_minutes)
        logger.info(f"Added interval task: {task_id} (every {interval_minutes} minutes)")

    def add_hourly_task(self, task_id: str, func: Callable, minutes_past_hour: int = 0):
        """启用小时任务并持久化为 enabled=True"""
        self.remove_task(task_id, persist=False)
        schedule.every().hour.at(f"{minutes_past_hour:02d}:00").do(
            self._wrap_task(task_id, func)
        ).tag(task_id)
        self._tasks[task_id] = {
            'type': 'hourly',
            'interval': 60,
            'minutes_past_hour': minutes_past_hour,
            'func': func,
            'next_run': self._get_next_run_for_task(task_id)
        }
        self._persist_status(task_id, is_enabled=True, interval_minutes=60)
        logger.info(f"Added hourly task: {task_id} (runs at {minutes_past_hour}:00 past each hour)")

    def remove_task(self, task_id: str, persist: bool = True):
        """停止任务并可选持久化为 enabled=False"""
        if task_id in self._tasks:
            schedule.clear(task_id)
            del self._tasks[task_id]
            logger.info(f"Removed task: {task_id}")
        if persist:
            # 保留 interval_minutes，只更新 is_enabled=False
            current_interval = self._get_db_interval(task_id)
            self._persist_status(task_id, is_enabled=False, interval_minutes=current_interval)

    def restore_from_db(self):
        """应用启动时从数据库恢复任务状态

        遍历已注册的任务元信息，根据 scheduled_task_status 表中的 is_enabled 决定是否启动。
        - 若表无记录：使用默认行为（按 register 时不启动，等待用户手动 enable）
        - 若 is_enabled=True：用数据库记录的 interval 启动任务
        - 若 is_enabled=False：保持停止
        """
        if not self._registry:
            logger.warning("Task registry is empty, nothing to restore")
            return

        db = SessionLocal()
        try:
            db_statuses: Dict[str, ScheduledTaskStatus] = {
                s.task_id: s for s in db.query(ScheduledTaskStatus).all()
            }
        except Exception as e:
            logger.error(f"Failed to load scheduled_task_status: {e}")
            db.close()
            return
        finally:
            try:
                db.close()
            except Exception:
                logger.warning("close scheduled_task_status session failed", exc_info=True)

        for task_id, info in self._registry.items():
            status = db_statuses.get(task_id)
            if status and status.is_enabled:
                interval = status.interval_minutes or info['default_interval']
                self._add_task_to_schedule(task_id, info['func'], interval)
                logger.info(f"Restored task '{task_id}' as ENABLED (every {interval} min)")
            else:
                logger.info(f"Task '{task_id}' remains DISABLED (db_enabled={status.is_enabled if status else 'no record'})")

    def cleanup_orphan_tasks(self):
        """移除已下线的定时任务（注册表外）并清理数据库记录。"""
        if not self._registry:
            return
        valid = set(self._registry.keys())
        for task_id in list(self._tasks.keys()):
            if task_id not in valid:
                self.remove_task(task_id, persist=False)
        db = SessionLocal()
        try:
            orphans = db.query(ScheduledTaskStatus).filter(
                ~ScheduledTaskStatus.task_id.in_(valid)
            ).all()
            for row in orphans:
                schedule.clear(row.task_id)
                db.delete(row)
                logger.info("Removed orphan scheduled task: %s", row.task_id)
            if orphans:
                db.commit()
        except Exception as e:
            logger.error("Failed to cleanup orphan tasks: %s", e)
            db.rollback()
        finally:
            db.close()

    # ===== 内部辅助 =====
    def _add_task_to_schedule(self, task_id: str, func: Callable, interval_minutes: int):
        """将任务实际加入 schedule 库（不写数据库）"""
        self.remove_task(task_id, persist=False)
        schedule.every(interval_minutes).minutes.do(
            self._wrap_task(task_id, func)
        ).tag(task_id)
        self._tasks[task_id] = {
            'type': 'interval',
            'interval': interval_minutes,
            'func': func,
            'next_run': self._get_next_run_for_task(task_id)
        }

    def _persist_status(self, task_id: str, is_enabled: bool, interval_minutes: Optional[int]):
        """持久化任务状态到数据库"""
        db = SessionLocal()
        try:
            status = db.query(ScheduledTaskStatus).filter(
                ScheduledTaskStatus.task_id == task_id
            ).first()
            default_interval = self._registry.get(task_id, {}).get('default_interval', 60)
            if not status:
                status = ScheduledTaskStatus(
                    task_id=task_id,
                    is_enabled=is_enabled,
                    interval_minutes=interval_minutes if interval_minutes is not None else default_interval,
                )
                db.add(status)
            else:
                status.is_enabled = is_enabled
                if interval_minutes is not None:
                    status.interval_minutes = interval_minutes
            db.commit()
        except Exception as e:
            logger.error(f"Failed to persist status for {task_id}: {e}")
            db.rollback()
        finally:
            db.close()

    def _get_db_interval(self, task_id: str) -> Optional[int]:
        """读取数据库中记录的 interval_minutes"""
        db = SessionLocal()
        try:
            status = db.query(ScheduledTaskStatus).filter(
                ScheduledTaskStatus.task_id == task_id
            ).first()
            return status.interval_minutes if status else None
        except Exception as e:
            logger.error(f"Failed to get db interval for {task_id}: {e}")
            return None
        finally:
            db.close()

    def _update_last_run(self, task_id: str):
        """更新任务最后运行时间"""
        db = SessionLocal()
        try:
            status = db.query(ScheduledTaskStatus).filter(
                ScheduledTaskStatus.task_id == task_id
            ).first()
            if status:
                status.last_run_at = datetime.now()
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update last_run for {task_id}: {e}")
            db.rollback()
        finally:
            db.close()

    def _get_next_run_for_task(self, task_id: str) -> Optional[datetime]:
        for job in schedule.get_jobs():
            if task_id in job.tags:
                return job.next_run
        return None

    def dispatch_task(self, task_id: str) -> str:
        """到点或手动触发：只入队，不在调度线程里执行任务体。

        返回 queued / busy / missing / error。
        """
        if task_id not in self._registry and task_id not in self._tasks:
            return "missing"
        from services.job_queue import enqueue_crawler
        from services.task_run_lock import task_run_lock

        if task_run_lock.is_locked(task_id):
            logger.info("Task %s already in progress, skip dispatch", task_id)
            return "busy"
        token = task_run_lock.acquire(task_id)
        if not token:
            return "busy"
        task_run_lock.write_status(task_id, {
            "phase": "queued",
            "in_progress": True,
            "message": "已入队",
        })
        try:
            queued = enqueue_crawler(task_id, lock_token=token)
        except Exception:
            logger.exception("Failed to enqueue scheduled task: %s", task_id)
            task_run_lock.release(task_id, token)
            return "error"
        status = (queued or {}).get("status")
        if status not in ("queued", "started"):
            task_run_lock.release(task_id, token)
            logger.error("Enqueue scheduled task %s rejected: %s", task_id, queued)
            return "error"
        logger.info(
            "Dispatched task %s via %s job=%s",
            task_id, queued.get("mode"), queued.get("job_id"),
        )
        return "queued"

    def run_now(self, task_id: str) -> bool:
        """手动触发。已入队返回 True；未注册或正在执行返回 False。"""
        if task_id not in self._tasks and task_id in self._registry:
            logger.info("Task %s is disabled, dispatching one-off via registry", task_id)
        return self.dispatch_task(task_id) == "queued"

    def _wrap_task(self, task_id: str, _func: Callable) -> Callable:
        """schedule 回调只负责入队，立刻返回，避免堵住其它到点任务。"""

        def wrapper():
            outcome = self.dispatch_task(task_id)
            if outcome == "busy":
                self._log_busy_skip(task_id)
            elif outcome != "queued":
                logger.error("Scheduled tick failed to dispatch %s: %s", task_id, outcome)
        return wrapper

    @staticmethod
    def _log_busy_skip(task_id: str) -> None:
        """到点跳过时记录锁持有情况；排队停滞过久升级 WARNING，提示 worker 可能未消费队列。"""
        held_seconds = None
        phase = None
        try:
            from services.task_run_lock import task_run_lock
            status = task_run_lock.read_status(task_id) or {}
            phase = status.get("phase")
            updated_at = status.get("updated_at")
            if updated_at:
                import time as _time
                from datetime import datetime as _dt
                try:
                    held_seconds = max(0, int(_time.time() - _dt.strptime(str(updated_at), "%Y-%m-%dT%H:%M:%S").timestamp()))
                except (ValueError, TypeError):
                    held_seconds = None
        except Exception as e:
            logger.debug("busy-skip status lookup failed for %s: %s", task_id, e)

        if phase == "queued":
            # 排队中却一直没被 worker 接手，多半是队列无人消费
            logger.warning(
                "Scheduled tick skipped, %s still queued (status untouched for %ss) — worker 可能未消费队列",
                task_id, held_seconds if held_seconds is not None else ">=0",
            )
        else:
            logger.info("Scheduled tick skipped, %s still in progress", task_id)

    # ===== 状态查询 =====
    def get_task_status(self, task_id: str) -> Optional[dict]:
        return self.get_all_tasks().get(task_id)

    def get_all_tasks(self) -> dict:
        """合并内存运行状态与数据库持久化状态，供 API 返回"""
        db = SessionLocal()
        try:
            db_statuses: Dict[str, ScheduledTaskStatus] = {
                s.task_id: s for s in db.query(ScheduledTaskStatus).all()
            }
        except Exception as e:
            logger.error(f"Failed to load db statuses: {e}")
            db_statuses = {}
        finally:
            db.close()

        result = {}
        all_task_ids = set(self._registry.keys()) | set(db_statuses.keys()) | set(self._tasks.keys())
        for task_id in sorted(all_task_ids):
            info = self._registry.get(task_id, {})
            db_info = db_statuses.get(task_id)
            in_memory = task_id in self._tasks

            if in_memory:
                interval = self._tasks[task_id].get('interval')
                next_run = self._get_next_run_for_task(task_id)
            else:
                interval = db_info.interval_minutes if db_info else info.get('default_interval')
                next_run = None

            result[task_id] = {
                'type': self._tasks[task_id].get('type', 'interval') if in_memory else 'interval',
                'interval': interval,
                'next_run': next_run,
                # is_enabled 以数据库为准（无记录时按内存中是否已挂上调度判断）
                'is_enabled': db_info.is_enabled if db_info is not None else in_memory,
                # running 保持原意：已挂进调度循环。是否正在跑看 in_progress
                'running': in_memory,
                'in_progress': False,
                'last_run_at': db_info.last_run_at if db_info else None,
                'name': info.get('name', task_id),
                'category': info.get('category', 'unknown'),
                'description': info.get('description', ''),
                'registered': task_id in self._registry,
            }
        try:
            from services.task_run_lock import task_run_lock
            held = task_run_lock.locked_ids(result.keys())
            for task_id in held:
                result[task_id]["in_progress"] = True
                try:
                    lock_status = task_run_lock.read_status(task_id) or {}
                    result[task_id]["phase"] = lock_status.get("phase")
                    result[task_id]["status_message"] = lock_status.get("message")
                    updated_at = str(lock_status.get("updated_at") or "")
                    if updated_at:
                        import time as _time
                        from datetime import datetime as _dt
                        try:
                            result[task_id]["status_age_seconds"] = max(
                                0, int(_time.time() - _dt.strptime(updated_at, "%Y-%m-%dT%H:%M:%S").timestamp())
                            )
                        except (ValueError, TypeError):
                            pass
                except Exception:
                    logger.warning("task lock status enrich failed for %s", task_id, exc_info=True)
        except Exception as e:
            logger.debug("task in_progress lookup failed: %s", e)
        return result

    def is_running(self) -> bool:
        return self._running


scheduler = SchedulerService()
