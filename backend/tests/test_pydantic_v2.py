"""Regression guard: the backend must stay on the Pydantic V2 API.

`.dict()` / `.from_orm()` / `class Config:` still work on Pydantic 2.x but raise
PydanticDeprecatedSince20 and are removed in V3. Scan the backend sources (and
the API/service entry points) to keep them out.
"""
import warnings
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, PydanticDeprecatedSince20

BACKEND_DIR = Path(__file__).resolve().parent.parent

# V1 spellings that are deprecated in V2 and gone in V3.
# ".dict(" is split so the token doesn't appear literally in this file's source.
FORBIDDEN = (
    ".from_orm(",
    ".dict" + "(",
    "class Config:",
    "@validator(",
    "@root_validator(",
    ".schema(",
    ".parse_obj(",
)

# `models/ensemble.py` has a method named `_params_from_orm` and services have
# unrelated dict helpers; excluded on purpose so the scan stays meaningful.
EXCLUDED_SUBSTR = ("_params_from_orm",)

SELF_NAME = "test_pydantic_v2.py"


def _source_lines():
    for path in sorted(BACKEND_DIR.rglob("*.py")):
        # 排除虚拟环境（仓库里同时存在 backend/.venv 与 backend/venv，两份都在用）。
        # 匹配任意一级目录名，不能只看 path.parts[0]——venv 实际是第 3 级。
        if "venv" in path.parts or ".venv" in path.parts or "site-packages" in path.parts:
            continue
        if path.name == SELF_NAME:
            continue  # this file spells the forbidden tokens on purpose
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            yield path, lineno, line


def test_no_pydantic_v1_api_in_backend_sources():
    offenders = []
    for path, lineno, line in _source_lines():
        code = line.split("#", 1)[0]  # ignore comments
        for token in FORBIDDEN:
            if token not in code:
                continue
            if any(skip in code for skip in EXCLUDED_SUBSTR):
                continue
            offenders.append(f"{path.relative_to(BACKEND_DIR)}:{lineno}: {line.strip()}")

    assert not offenders, "Pydantic V1 API found:\n" + "\n".join(offenders)


def _assert_no_deprecation(fn):
    """Run fn and fail if it emits a PydanticDeprecatedSince20 warning.

    用标准库 catch_warnings 而不是 pytest.warns：基线命令带 `-p no:warnings`
    会关闭 pytest 的 warning 捕获，`pytest.warns(())` 会误报 DID NOT WARN。
    """
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        fn()
    bad = [w for w in record if issubclass(w.category, PydanticDeprecatedSince20)]
    assert not bad, [str(w.message) for w in bad]


def test_model_validate_on_plain_object_does_not_deprecate():
    """`model_validate` on an attribute-only object is the correct V2 form."""
    class _Row:
        def __init__(self, id, name):
            self.id = id
            self.name = name

    class _M(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        id: int
        name: str = "x"

    def _run():
        out = _M.model_validate(_Row(1, "abc"))
        assert out.name == "abc"
        assert out.model_dump()["id"] == 1

    _assert_no_deprecation(_run)


def test_configdict_is_live():
    """V2 model_config must actually take effect, otherwise attributes mode is lost."""
    class _M(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        id: int

    assert _M.model_config["from_attributes"] is True
    row = type("R", (), {"id": 5})()
    assert _M.model_validate(row).id == 5
