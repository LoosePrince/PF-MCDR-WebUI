"""
全局状态管理模块
统一维护跨模块的全局变量，减少循环引用
"""

from typing import Any, Dict

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

# 已注册的插件网页列表 (插件ID: HTML文件相对于插件config目录的路径)
REGISTERED_PLUGIN_PAGES: Dict[str, str] = {}
