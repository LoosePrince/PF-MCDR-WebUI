"""
全局状态管理模块
统一维护跨模块的全局变量，减少循环引用
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, TypedDict


@dataclass
class PluginPageEntry:
    """插件在 WebUI 中注册的页面与可选 API 处理器。"""

    html_path: str
    api_handler: Optional[Callable[..., Any]] = None
    upload_max_bytes: Optional[int] = None


class PluginApiHandlerParams(TypedDict):
    """传入插件 api_handler 的第二参数结构（与文档一致）。"""

    method: str
    query: dict[str, str | list[str]]
    body: Any | None  # multipart 文件字段见 WebApi「插件后端 API 代理」

# FastAPI 应用实例，由 web_server.init_app 注入，供 PIM 等模块调度异步任务
app: Optional[Any] = None

# Web在线玩家心跳（基于 /api/chat/get_new_messages 请求），值为最近心跳Unix秒
WEB_ONLINE_PLAYERS: Dict[str, int] = {}

# RCON 在线玩家缓存，降低查询频率
RCON_ONLINE_CACHE: Dict[str, Any] = {
    "names": set(),
    "ts": 0,  # 上次刷新时间（秒）
    "dirty": False  # 标记需要刷新
}

# 用于保存pip任务状态的字典
pip_tasks: Dict[str, Any] = {}

# 已注册的插件网页 (插件ID -> 页面路径与可选 API 处理器)
# 注意：实际数据在 init_app 时绑定到 PluginServerInterface 上，见 bind_plugin_pages_registry_to_server
REGISTERED_PLUGIN_PAGES: Dict[str, PluginPageEntry] = {}

# 挂在 MCDR server 上的属性名；跨 guguwebui 插件重载保留同一张表
PLUGIN_PAGES_SERVER_ATTR = "_guguwebui_registered_plugin_pages"


def bind_plugin_pages_registry_to_server(server: Any) -> None:
    """
    将 REGISTERED_PLUGIN_PAGES 与 MCDR 进程中的 PluginServerInterface 实例绑定。

    guguwebui 插件重载会重新执行本模块，REGISTERED_PLUGIN_PAGES 名字会指向新 dict；
    但 server 对象为同一实例，其上保存的 dict 仍保留其它插件已注册的条目与 api_handler 引用。
    """
    global REGISTERED_PLUGIN_PAGES

    prev = getattr(server, PLUGIN_PAGES_SERVER_ATTR, None)
    if isinstance(prev, dict):
        REGISTERED_PLUGIN_PAGES = prev
        return
    setattr(server, PLUGIN_PAGES_SERVER_ATTR, REGISTERED_PLUGIN_PAGES)
