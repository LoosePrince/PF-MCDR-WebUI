"""回归测试：主服代理的管理员判定必须由真实路由元数据推导。

历史实现用硬编码路径清单（panel_merge/proxy.py::is_admin_api_path）近似复刻
路由上的 Depends(get_current_admin)，曾漏掉 /api/players/*、/api/save_web_config 等
管理员路由，导致主服普通用户可把请求代理到子服执行管理操作。

断言目标：
1. 关键安全路径被识别为管理员路由（含此前漏配的 players / save_web_config）；
2. 全量遍历实际路由表：凡声明 get_current_admin 的路由，lookup 必须返回 True，
   其余返回 False，不存在 None（未匹配）的“漏网”管理员路由。
"""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from guguwebui.panel_merge.proxy import _route_requires_admin, \
    _route_requires_admin_for_request, iter_api_routes
from guguwebui.panel_merge.routes import router as panel_merge_router
from guguwebui.routers.audit_router import router as audit_router
from guguwebui.routers.chat_router import router as chat_router
from guguwebui.routers.config_router import router as config_router
from guguwebui.routers.monitor_router import router as monitor_router
from guguwebui.routers.mod_router import router as mod_router
from guguwebui.routers.pim_router import router as pim_router
from guguwebui.routers.pip_router import router as pip_router
from guguwebui.routers.player_router import router as player_router
from guguwebui.routers.plugin_management_router import \
    router as plugin_management_router
from guguwebui.routers.plugin_proxy_router import router as plugin_proxy_router
from guguwebui.routers.server_router import router as server_router


def _build_app() -> FastAPI:
    """镜像 web_server.py 的挂载方式（不含 @app 级页面路由）。"""
    app = FastAPI()
    routers = [
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
    for r in routers:
        app.include_router(r, prefix="/api")
    return app


def _make_request(app: FastAPI, method: str, path: str) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
        "app": app,
        "scheme": "http",
        "server": ("test", 80),
        "client": ("127.0.0.1", 1),
        "root_path": "",
        "http_version": "1.1",
    }
    return Request(scope)


def _concrete_path(path: str) -> str:
    """把路由模板转成可匹配的示例路径：{a} / {a:path} -> x。"""
    return re.sub(r"\{[^}]*\}", "x", path)


def test_previously_missing_admin_routes_are_detected():
    app = _build_app()
    cases = [
        # （此前漏配的）玩家管理写操作（REST 子资源路径）
        ("POST", "/api/players/x/ban", True),
        ("POST", "/api/players/x/unban", True),
        ("POST", "/api/players/x/kick", True),
        ("PUT", "/api/players/x/op", True),
        ("DELETE", "/api/players/x/op", True),
        ("PUT", "/api/players/whitelist", True),
        ("POST", "/api/players/whitelist/reload", True),
        ("PUT", "/api/players/whitelist/x", True),
        ("DELETE", "/api/players/whitelist/x", True),
        ("GET", "/api/players", True),
        ("GET", "/api/players/bots", True),
        ("GET", "/api/players/whitelist", True),
        ("GET", "/api/players/ops", True),
        ("GET", "/api/players/bans", True),
        # （此前漏配的）Web 配置
        ("PUT", "/api/web-config", True),
        # 对照：只读/普通用户路由
        ("GET", "/api/plugins", False),
        ("GET", "/api/server/status", False),
        ("GET", "/api/monitor/overview", False),
        # chat 域读接口公开（GET /chat/messages 无管理员依赖）
        ("GET", "/api/chat/messages", False),
        ("GET", "/api/chat/session/x", False),
        # 清空聊天消息仅管理员（DELETE /chat/messages）
        ("DELETE", "/api/chat/messages", True),
        # 面板合并/配对域：读/写接口的权限要求
        ("GET", "/api/servers", False),  # 仅登录
        ("GET", "/api/panel_merge_config", True),
        ("PUT", "/api/panel_merge_config", True),
        ("GET", "/api/pairing/pending", True),
        ("POST", "/api/pairing/accept", True),
        ("POST", "/api/pairing/deny", True),
        ("POST", "/api/pairing/connect_request", True),
        ("GET", "/api/pairing/connect_status", True),
        # 无需登录的公开握手（窗口内有效，权限由状态机控制）
        ("POST", "/api/pairing/request", False),
        ("GET", "/api/pairing/status", False),
        # 已下线的旧路径无本地路由 -> None
        ("GET", "/api/chat/get_messages", None),
        # 未知路径：无本地路由 -> None
        ("GET", "/api/definitely-not-a-route", None),
    ]
    for method, path, expected in cases:
        got = _route_requires_admin_for_request(_make_request(app, method, path))
        assert got == expected, f"{method} {path}: got {got}, expected {expected}"


def test_full_route_table_matches_admin_metadata():
    """遍历真实路由表：lookup 结果必须与路由声明的 get_current_admin 完全一致。"""
    app = _build_app()

    checked = 0
    for route, prefix in iter_api_routes(app):
        # 每个路由的所有方法逐一验证（排除含方法语义冲突的 HEAD/OPTIONS 扫描）
        methods = [m for m in route.methods if m in {"GET", "POST", "PUT", "PATCH", "DELETE"}]
        if not methods:
            continue
        full_path = (prefix or "") + (route.path or "")
        path = _concrete_path(full_path)
        expected = _route_requires_admin(route)
        for method in methods:
            got = _route_requires_admin_for_request(_make_request(app, method, path))
            assert got is expected, (
                f"route mismatch {method} {full_path} (concrete {path}): "
                f"lookup={got}, route metadata={expected}"
            )
            checked += 1
    assert checked > 60, f"expected a broad route sweep, only checked {checked}"
