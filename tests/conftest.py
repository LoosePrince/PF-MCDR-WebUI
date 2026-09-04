"""pytest 会话级夹具。

guguwebui.constant 在导入时读取根目录 ./config.yml（MCDR 运行环境才有该文件），
任何经 constant 导入的模块（routers / panel_merge.proxy 等）在仓库根目录跑测试时都会失败。
这里在会话开始时按需生成最小 config.yml，结束后仅删除本次创建的文件。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_YML = _ROOT / "config.yml"

_config_created = False
if not _CONFIG_YML.exists():
    try:
        _CONFIG_YML.write_text("working_directory: server\n", encoding="utf-8")
        _config_created = True
    except OSError:
        pass


def pytest_sessionfinish(session, exitstatus):
    if _config_created:
        try:
            _CONFIG_YML.unlink()
        except OSError:
            pass
