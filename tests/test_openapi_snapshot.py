"""OpenAPI 快照对比：防止路由/参数/响应模型被无意改动。

挂载方式与 tests/test_proxy_local.py、tests/test_contract.py 完全一致
（镜像 web_server.py 的 12 个 router，不含 @app 级登录/页面端点）。

- 默认：生成当前路由表 OpenAPI 并与 tests/snapshots/openapi_routers.json 逐键比较；
- 差异且设置环境变量 UPDATE_SNAPSHOT=1：覆盖写快照（开发期主动变更契约后使用），
  然后照常断言通过；
- 与契约基线 docs/WebApi.md 配套：文档声明以 OpenAPI /openapi.json 为准。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI

from guguwebui.panel_merge.routes import router as panel_merge_router
from guguwebui.routers.audit_router import router as audit_router
from guguwebui.routers.chat_router import router as chat_router
from guguwebui.routers.config_router import router as config_router
from guguwebui.routers.monitor_router import router as monitor_router
from guguwebui.routers.mod_router import router as mod_router
from guguwebui.routers.pim_router import router as pim_router
from guguwebui.routers.pip_router import router as pip_router
from guguwebui.routers.player_router import router as player_router
from guguwebui.routers.plugin_management_router import (
    router as plugin_management_router,
)
from guguwebui.routers.plugin_proxy_router import router as plugin_proxy_router
from guguwebui.routers.server_router import router as server_router

_SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "openapi_routers.json"

_ROUTERS = [
    panel_merge_router,
    plugin_management_router,
    config_router,
    server_router,
    monitor_router,
    plugin_proxy_router,
    pim_router,
    pip_router,
    chat_router,
    player_router,
    mod_router,
    audit_router,
]


def _deterministic_unique_id(route) -> str:
    """默认 operationId 对同名路由的消歧依赖进程内构建次序，改为确定性派生。"""
    methods = "_".join(sorted(route.methods or [])) or "any"
    return f"{route.name}__{route.path.replace('/', '_')}__{methods}"


def _build_app() -> FastAPI:
    app = FastAPI(
        title="guguwebui routers snapshot",
        version="test",
        generate_unique_id_function=_deterministic_unique_id,
    )
    for r in _ROUTERS:
        app.include_router(r, prefix="/api")
    return app


def test_openapi_routes_snapshot():
    schema = _build_app().openapi()
    update = os.environ.get("UPDATE_SNAPSHOT") == "1"
    if update:
        _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT.write_text(
            json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if not _SNAPSHOT.exists():
        raise AssertionError(
            f"快照不存在: {_SNAPSHOT}（先运行 UPDATE_SNAPSHOT=1 生成）"
        )
    previous = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    assert schema == previous, (
        "OpenAPI 契约与快照不一致。若为有意变更，运行：\n"
        "  UPDATE_SNAPSHOT=1 python -m pytest tests/test_openapi_snapshot.py -q\n"
        "并复核 docs/WebApi.md 是否需要同步。"
    )
