#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebUI 插件网页 + 侧边栏 + 自定义 API 处理器 示例。

依赖：已安装并启用 guguwebui（PF-MCDR-WebUI）。

用法：将本目录复制到 MCDR plugins/ 下，保持
  plugins/webui_plugin_page_example/webui_plugin_page_example.py
  plugins/webui_plugin_page_example/static/demo.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcdreforged.api.types import PluginServerInterface

PLUGIN_ID = "webui_plugin_page_example"
_PLUGIN_DIR = Path(__file__).resolve().parent
_HTML_FILE = _PLUGIN_DIR / "static" / "demo.html"


def _api_handler(url_path: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    WebUI 将请求转发到此：第一参数为子路径，第二参数含 method / query / body。
    可为 async 或 sync（由 WebUI 在线程池中执行 sync）。
    """
    method = params.get("method", "GET")
    query = params.get("query") or {}
    body = params.get("body")

    if url_path == "hello" and method == "GET":
        return {
            "ok": True,
            "message": "hello from webui_plugin_page_example",
            "query": query,
        }

    if url_path == "echo" and method == "POST":
        return {
            "ok": True,
            "echo": body,
        }

    if url_path == "status" and method == "GET":
        return {
            "ok": True,
            "plugin_id": PLUGIN_ID,
            "html_exists": _HTML_FILE.is_file(),
        }

    return {
        "ok": False,
        "error": "no route",
        "url_path": url_path,
        "method": method,
    }


def on_load(server: PluginServerInterface, old) -> None:
    webui = server.get_plugin_instance("guguwebui")
    if not webui or not hasattr(webui, "register_plugin_page"):
        server.logger.warning(
            "[%s] 未找到 guguwebui 或 register_plugin_page，跳过网页注册",
            PLUGIN_ID,
        )
        return

    if not _HTML_FILE.is_file():
        server.logger.error(
            "[%s] 找不到 HTML 文件: %s", PLUGIN_ID, _HTML_FILE
        )
        return

    html_path = str(_HTML_FILE)
    webui.register_plugin_page(
        PLUGIN_ID,
        html_path,
        api_handler=_api_handler,
    )
    server.logger.info(
        "[%s] 已注册插件页与 API 处理器，HTML=%s", PLUGIN_ID, html_path
    )
