"""生产弱口令 fail-fast 与 TRAESOLO_ADMIN_PASSWORD 注入。"""

from __future__ import annotations

import os

import pytest


def test_production_rejects_default_password(monkeypatch):
    monkeypatch.setenv("TRAESOLO_PRODUCTION", "1")
    monkeypatch.delenv("TRAESOLO_ADMIN_PASSWORD", raising=False)
    from init_db import DEFAULT_ADMIN_PASSWORD, _assert_production_admin_password

    with pytest.raises(RuntimeError, match="TRAESOLO_ADMIN_PASSWORD"):
        _assert_production_admin_password(DEFAULT_ADMIN_PASSWORD)


def test_production_rejects_explicit_default_password(monkeypatch):
    monkeypatch.setenv("TRAESOLO_PRODUCTION", "1")
    monkeypatch.setenv("TRAESOLO_ADMIN_PASSWORD", "admin123")
    from init_db import DEFAULT_ADMIN_PASSWORD, _assert_production_admin_password, _resolve_admin_password

    pwd = _resolve_admin_password()
    assert pwd == DEFAULT_ADMIN_PASSWORD
    with pytest.raises(RuntimeError, match="弱口令"):
        _assert_production_admin_password(pwd)


def test_production_accepts_strong_password(monkeypatch):
    monkeypatch.setenv("TRAESOLO_PRODUCTION", "1")
    monkeypatch.setenv("TRAESOLO_ADMIN_PASSWORD", "Str0ng!Prod#Pass")
    from init_db import _assert_production_admin_password, _resolve_admin_password

    pwd = _resolve_admin_password()
    assert pwd == "Str0ng!Prod#Pass"
    _assert_production_admin_password(pwd)


def test_dev_allows_default_password(monkeypatch):
    monkeypatch.setenv("TRAESOLO_PRODUCTION", "0")
    monkeypatch.delenv("TRAESOLO_ADMIN_PASSWORD", raising=False)
    from init_db import DEFAULT_ADMIN_PASSWORD, _assert_production_admin_password, _resolve_admin_password

    pwd = _resolve_admin_password()
    assert pwd == DEFAULT_ADMIN_PASSWORD
    _assert_production_admin_password(pwd)
