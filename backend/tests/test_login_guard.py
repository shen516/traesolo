"""登录限流单元测试。"""

from services import login_guard


def test_login_guard_lock_after_failures():
    user = "rate_limit_test_user"
    login_guard.clear_failures(user)
    locked, _ = login_guard.is_locked(user)
    assert locked is False

    for _ in range(login_guard.MAX_FAILURES - 1):
        n, just = login_guard.record_failure(user)
        assert just is False
        assert n >= 1

    n, just = login_guard.record_failure(user)
    assert just is True
    locked, wait = login_guard.is_locked(user)
    assert locked is True
    assert wait > 0

    login_guard.clear_failures(user)
    locked, _ = login_guard.is_locked(user)
    assert locked is False
