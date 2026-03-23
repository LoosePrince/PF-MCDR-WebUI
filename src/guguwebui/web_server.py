import asyncio
import datetime
import inspect
import json
import logging
import secrets
import uuid
from pathlib import Path
from typing import Any, Optional

import aiohttp
from fastapi import (Body, Depends, FastAPI, Form, HTTPException, Request,
                     status)
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, RedirectResponse)
from mcdreforged.api.event import MCDRPluginEvents
from mcdreforged.api.types import PluginServerInterface
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

import guguwebui.state as gugu_state
from guguwebui.constant import *
from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.panel_merge.proxy import ApiProxyDispatchMiddleware
from guguwebui.panel_merge.routes import router as panel_merge_router
from guguwebui.PIM import initialize_pim
from guguwebui.services.ai_service import AIService
from guguwebui.services.auth_service import AuthService
from guguwebui.services.chat_service import ChatService
from guguwebui.services.config_service import ConfigService
from guguwebui.services.file_service import FileService
from guguwebui.services.pip_service import PipService
from guguwebui.services.plugin_service import PluginService
from guguwebui.services.server_service import ServerService
from guguwebui.state import (RCON_ONLINE_CACHE, PluginApiHandlerParams,
                             bind_plugin_pages_registry_to_server, pip_tasks)
from guguwebui.structures import (BusinessException, ConfigData, DeepseekQuery,
                                  PimInstallRequest, PimUninstallRequest,
                                  PipPackageRequest, PluginInfo, SaveConfig,
                                  SaveContent, ServerControl, ToggleConfig)
from guguwebui.utils.auth_util import migrate_old_config
from guguwebui.utils.log_watcher import LogWatcher
from guguwebui.utils.mc_util import get_plugin_version
from guguwebui.utils.server_util import *

# 获取插件真实版本号
app = FastAPI(
    title="GUGU WebUI",
    description="MCDR WebUI 管理界面",
    version=get_plugin_version(),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# 导出 get_plugins_info 供 __init__.py 使用
__all__ = [
    "app",
    "init_app",
    "log_watcher",
    "DEFALUT_CONFIG",
    "STATIC_PATH",
    "ThreadedUvicorn",
]

# URL路径处理函数已移至 utils.py

# SPA 入口文件路径
static_index_path = Path(STATIC_PATH) / "static" / "index.html"


def serve_spa_index(request: Request) -> HTMLResponse:
    """返回 SPA 的 index.html 文件，并注入配置"""
    if not static_index_path.exists():
        return HTMLResponse(
            content="<h1>前端文件未找到</h1><p>请确保已构建前端项目（运行 npm run build）</p>",
            status_code=404,
        )
    with open(static_index_path, "r", encoding="utf-8") as f:
        content = f.read()
    root_path = request.scope.get("root_path", "")
    if not root_path.endswith("/"):
        root_path += "/"
    config_script = f'<script>window.__GUGU_CONFIG__ = {json.dumps({"root_path": root_path.rstrip("/")})};</script>'
    overall_css_link = f'<link rel="stylesheet" href="{root_path}custom/overall.css">'
    overall_js_script = f'<script defer src="{root_path}custom/overall.js"></script>'
    content = content.replace(
        "<head>",
        f'<head><base href="{root_path}">{config_script}{overall_css_link}{overall_js_script}',
    )
    return HTMLResponse(content=content)


# 全局LogWatcher实例
log_watcher = LogWatcher()

# ============================================================#
# HTTP client session (for proxy)
@app.on_event("startup")
async def _startup_http_session():
    if not hasattr(app.state, "http_session") or app.state.http_session is None:
        timeout = aiohttp.ClientTimeout(total=30)
        app.state.http_session = aiohttp.ClientSession(timeout=timeout)


@app.on_event("shutdown")
async def _shutdown_http_session():
    session = getattr(app.state, "http_session", None)
    if session is not None:
        try:
            await session.close()
        except Exception:
            pass
        app.state.http_session = None


# Multi-server panel merge logic has been moved to guguwebui.panel_merge.*

# 尝试迁移旧配置
migrate_old_config()


# 初始化函数，在应用程序启动时调用
def init_app(server_instance):
    """初始化应用程序，注册事件监听器"""
    global log_watcher

    # 注入 FastAPI app 到 state，供 PIM installer 等模块调度异步任务
    import guguwebui.state as state_module
    state_module.app = app

    # 存储服务器接口
    app.state.server_interface = server_instance

    # 插件网页注册表挂在 MCDR server 上，避免仅重载 guguwebui 时丢失其它插件的注册
    bind_plugin_pages_registry_to_server(server_instance)

    # 初始化自更新信息
    app.state.self_update_info = {"available": False}

    # 确保user_db包含所有必要的键
    try:
        from guguwebui.constant import DEFALUT_DB, user_db

        # 检查并添加缺失的键
        for key in DEFALUT_DB:
            if key not in user_db:
                user_db[key] = DEFALUT_DB[key]
                server_instance.logger.debug(f"添加缺失的数据库键: {key}")
        user_db.save()
        server_instance.logger.debug("数据库结构已更新")
    except Exception as e:
        server_instance.logger.error(f"更新数据库结构时出错: {e}")

    # 清理现有监听器，避免重复注册
    if log_watcher:
        log_watcher.stop()

    # 初始化LogWatcher实例，将 server_instance 传递给它
    log_watcher = LogWatcher(server_interface=server_instance)

    # 设置日志捕获 - 直接调用此方法确保与MCDR内部日志系统连接
    log_watcher._setup_log_capture()

    # 注册MCDR事件监听器，每种事件只注册一次
    server_instance.register_event_listener(MCDRPluginEvents.GENERAL_INFO, on_mcdr_info)
    server_instance.register_event_listener(
        MCDRPluginEvents.USER_INFO, on_server_output
    )
    # 注册玩家进出事件，刷新RCON在线缓存
    server_instance.register_event_listener(
        MCDRPluginEvents.PLAYER_JOINED, on_player_joined
    )
    server_instance.register_event_listener(
        MCDRPluginEvents.PLAYER_LEFT, on_player_left
    )

    # 初始化服务
    app.state.auth_service = AuthService(server_instance)
    app.state.config_service = ConfigService(server_instance)
    app.state.server_service = ServerService(server_instance, log_watcher)
    app.state.ai_service = AIService(server_instance, app.state.config_service)
    app.state.pip_service = PipService(server_instance)
    app.state.file_service = FileService(server_instance)
    app.state.chat_service = ChatService(server_instance, app.state.config_service)

    # 初始化PIM模块
    try:
        server_instance.logger.debug("正在初始化内置PIM模块...")
        pim_helper, plugin_installer = initialize_pim(server_instance)
        # 将初始化后的PIM实例存储到app.state中，供API调用
        app.state.pim_helper = pim_helper
        app.state.plugin_installer = plugin_installer

        # 初始化插件服务
        app.state.plugin_service = PluginService(
            server_instance, pim_helper, plugin_installer
        )

        # 注入服务依赖
        app.state.auth_service.config_service = app.state.config_service
        app.state.plugin_service.config_service = app.state.config_service
        app.state.server_service.config_service = app.state.config_service

        if pim_helper and plugin_installer:
            server_instance.logger.info("内置PIM模块初始化成功")
        else:
            server_instance.logger.warning(
                "内置PIM模块初始化部分失败，某些功能可能不可用"
            )

        # 在启动时检查插件仓库缓存
        from .utils.file_util import check_repository_cache

        check_repository_cache(server_instance)
    except Exception as e:
        server_instance.logger.error(f"内置PIM模块初始化失败: {e}")

    server_instance.logger.debug("WebUI日志捕获器已初始化，将直接从MCDR捕获日志")


# check_repository_cache 函数已移至 utils.py


# 事件处理函数
def on_player_joined(_server, _player: str, _info=None):
    """处理玩家加入事件"""
    try:
        RCON_ONLINE_CACHE["dirty"] = True
    except Exception:
        pass


def on_player_left(_server, _player: str):
    """处理玩家离开事件"""
    try:
        RCON_ONLINE_CACHE["dirty"] = True
    except Exception:
        pass


def on_server_output(server, info):
    """处理服务器输出事件"""
    global log_watcher
    if log_watcher:
        log_watcher.on_server_output(server, info)


def on_mcdr_info(server, info):
    """处理MCDR信息事件"""
    global log_watcher
    # 增加调试日志
    server.logger.debug(f"收到 MCDR 日志事件: {getattr(info, 'content', '')[:50]}...")
    if log_watcher:
        log_watcher.on_mcdr_info(server, info)
    else:
        server.logger.warning("LogWatcher 尚未初始化，无法记录日志")


# 全局异常处理器
@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.message, "data": exc.data},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # 如果是 401 或 403 且不是 API 请求，重定向到登录
    if exc.status_code in [401, 403] and "/api/" not in request.url.path:
        return RedirectResponse(
            url=get_redirect_url(request, "/login"), status_code=302
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    app.state.server_interface.logger.error(f"全局异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500, content={"status": "error", "message": "服务器内部错误"}
    )


# 语言列表 API：返回 /lang 目录下的 json 文件及其显示名称
@app.get("/api/langs")
def get_languages(request: Request):
    return JSONResponse(
        request.app.state.plugin_service.get_languages(), status_code=200
    )


# ============================================================#
#
# 认证与页面路由


# redirect to log in
@app.get("/", name="root")
def read_root(request: Request):
    return RedirectResponse(url=get_redirect_url(request, "/login"))


# login page - 使用 React SPA
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    auth_service: AuthService = request.app.state.auth_service
    if await auth_service.check_session_valid(request):
        return RedirectResponse(
            url=get_redirect_url(request, "/index"), status_code=status.HTTP_302_FOUND
        )
    return serve_spa_index(request)


# login request
@app.post("/api/login")
async def login(
    request: Request,
    account: str = Form(""),
    password: str = Form(""),
    temp_code: str = Form(""),
    remember: bool = Form(False),
):
    return await request.app.state.auth_service.login(
        request, account, password, temp_code, remember
    )


# logout Endpoints
@app.get("/logout", response_class=RedirectResponse)
async def logout(request: Request):
    """页面级登出"""
    response = RedirectResponse(
        url=get_redirect_url(request, "/login"), status_code=status.HTTP_302_FOUND
    )
    return await request.app.state.auth_service.logout(request, response)


@app.post("/api/logout")
async def api_logout(request: Request):
    """API 形式的登出"""
    return await request.app.state.auth_service.logout(
        request, JSONResponse({"status": "success", "message": "Logged out"})
    )


class SessionTokenSyncMiddleware(BaseHTTPMiddleware):
    """确保 session 与 user_db 中的 token 一致：若 cookie 有 token 但 token 已不在 db（如 db 被清空），则清除 session。"""

    async def dispatch(self, request: Request, call_next):
        token = request.cookies.get("token")
        if token and token not in user_db.get("token", {}):
            request.session.clear()
        return await call_next(request)


app.add_middleware(SessionTokenSyncMiddleware)
app.add_middleware(ApiProxyDispatchMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.include_router(panel_merge_router, prefix="/api")


# ============================================================#
# Pages - 使用 React SPA
@app.get("/index", response_class=HTMLResponse)
async def read_index(request: Request, user: dict = Depends(get_current_user)):
    return serve_spa_index(request)


@app.get("/home", response_class=HTMLResponse)
async def read_home(request: Request, user: dict = Depends(get_current_user)):
    return serve_spa_index(request)


@app.get("/mc", response_class=HTMLResponse)
async def mc(request: Request, admin: dict = Depends(get_current_admin)):
    return serve_spa_index(request)


@app.get("/mcdr", response_class=HTMLResponse)
async def mcdr(request: Request, admin: dict = Depends(get_current_admin)):
    return serve_spa_index(request)


@app.get("/plugins", response_class=HTMLResponse)
async def plugins(request: Request, admin: dict = Depends(get_current_admin)):
    return serve_spa_index(request)


@app.get("/online-plugins", response_class=HTMLResponse)
async def online_plugins(request: Request, admin: dict = Depends(get_current_admin)):
    return serve_spa_index(request)


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, admin: dict = Depends(get_current_admin)):
    return serve_spa_index(request)


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request, user: dict = Depends(get_current_user)):
    return serve_spa_index(request)


# 公开聊天页 - 使用 React SPA
@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    server_service: ServerService = request.app.state.server_service
    if not server_service.is_public_chat_enabled():
        return serve_spa_index(request)  # 返回 SPA，由前端处理 404
    return serve_spa_index(request)


# 玩家聊天页 - 独立页面，使用 React SPA
@app.get("/player-chat", response_class=HTMLResponse)
async def player_chat_page(request: Request):
    server_service: ServerService = request.app.state.server_service
    if not server_service.is_public_chat_enabled():
        return serve_spa_index(request)  # 返回 SPA，由前端处理 404
    return serve_spa_index(request)


# 404 page - 返回 SPA index.html，由前端处理 404
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"status": "error", "message": "API endpoint not found"}, status_code=404
        )
    if request.url.path.startswith("/static/"):
        return JSONResponse(
            {"status": "error", "message": "Static file not found"}, status_code=404
        )
    return serve_spa_index(request)


@app.exception_handler(ConnectionResetError)
async def connection_reset_handler(request: Request, exc: ConnectionResetError):
    # 在日志中记录错误，但向客户端返回友好消息
    app.state.server_interface.logger.warning(f"连接重置错误: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "连接被重置，请刷新页面重试"},
    )


@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    """处理业务异常"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.message, "data": exc.data},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = f"未处理的异常: {str(exc)}"
    logger = getattr(app.state.server_interface, "logger", logging.getLogger(__name__))
    logger.error(error_msg, exc_info=True)
    return JSONResponse(
        status_code=500, content={"status": "error", "message": "服务器内部错误"}
    )


# ============================================================#


@app.get("/api/checkLogin")
async def check_login_status(request: Request, user: dict = Depends(get_current_user)):
    username = user.get("username")
    nickname = None
    
    # 从 qq_nicknames 中获取昵称
    if username:
        try:
            from guguwebui.constant import user_db
            nickname = user_db.get("qq_nicknames", {}).get(str(username))
        except Exception:
            pass
    
    return JSONResponse({
        "status": "success",
        "username": username,
        "nickname": nickname
    })


# Return plugins' metadata
@app.get("/api/plugins")
async def get_plugins(
    request: Request, plugin_id: str = None, user: dict = Depends(get_current_user)
):
    plugins = request.app.state.plugin_service.get_plugins_list()
    if plugin_id:
        plugins = [p for p in plugins if p.get("id") == plugin_id]
    return JSONResponse(content={"status": "success", "plugins": plugins})


# 从 everything_slim.json 获取在线插件列表
@app.get("/api/online-plugins")
async def api_get_online_plugins(
    request: Request, repo_url: str = None, admin: dict = Depends(get_current_admin)
):
    """获取在线插件列表"""
    plugins_list = await request.app.state.plugin_service.get_online_plugins(repo_url)
    return JSONResponse(plugins_list)


# Loading/Unloading pluging
@app.post("/api/toggle_plugin")
async def api_toggle_plugin(
    request: Request,
    request_body: ToggleConfig,
    admin: dict = Depends(get_current_admin),
):
    """切换插件状态（加载/卸载）"""
    return JSONResponse(
        request.app.state.plugin_service.toggle_plugin(
            request_body.plugin_id, request_body.status
        )
    )


# Reload Plugin
@app.post("/api/reload_plugin")
async def api_reload_plugin(
    request: Request, plugin_info: PluginInfo, admin: dict = Depends(get_current_admin)
):
    """重载插件"""
    return JSONResponse(
        request.app.state.plugin_service.reload_plugin(plugin_info.plugin_id)
    )


@app.get("/api/list_config_files")
async def api_list_config_files(
    request: Request, plugin_id: str, user: dict = Depends(get_current_user)
):
    """列出插件的配置文件"""
    files_list = request.app.state.config_service.list_config_files(plugin_id)
    return JSONResponse({"status": "success", "files": files_list})


@app.get("/api/config/icp-records")
async def api_get_icp_records(request: Request):
    """获取ICP备案信息"""
    state = request.app.state
    return JSONResponse(state.file_service.get_icp_records(state.config_service))


@app.get("/api/get_web_config")
async def api_get_web_config(request: Request, user: dict = Depends(get_current_user)):
    """获取Web配置"""
    return JSONResponse(await request.app.state.config_service.get_web_config())


@app.post("/api/save_web_config")
async def api_save_web_config(
    request: Request, config: SaveConfig, admin: dict = Depends(get_current_admin)
):
    """保存Web配置"""
    return JSONResponse(request.app.state.config_service.save_web_config(config))


@app.get("/api/load_config")
async def api_load_config(
    request: Request,
    path: str,
    translation: bool = False,
    type: str = "auto",
    user: dict = Depends(get_current_user),
):
    """加载配置文件"""
    return JSONResponse(
        request.app.state.config_service.load_config(path, translation, type)
    )


@app.post("/api/save_config")
async def api_save_config(
    request: Request, config_data: ConfigData, admin: dict = Depends(get_current_admin)
):
    """保存配置文件"""
    config_service: ConfigService = request.app.state.config_service
    return JSONResponse(
        config_service.save_config(config_data.file_path, config_data.config_data)
    )


@app.post("/api/setup_rcon")
async def api_setup_rcon(request: Request, admin: dict = Depends(get_current_admin)):
    """一键启用RCON配置"""
    return JSONResponse(request.app.state.config_service.setup_rcon())


# load overall.js / overall.css
@app.get("/api/load_file")
async def load_file(
    request: Request, file: str, user: dict = Depends(get_current_user)
):
    return PlainTextResponse(request.app.state.file_service.load_custom_file(file))


# save overall.js / overall.css
@app.post("/api/save_file")
async def save_file(
    request: Request, data: SaveContent, admin: dict = Depends(get_current_admin)
):
    file_service: FileService = request.app.state.file_service
    return JSONResponse(file_service.save_custom_file(data.action, data.content))


# load config file
@app.get("/api/load_config_file")
async def load_config_file(
    request: Request, path: str, user: dict = Depends(get_current_user)
):
    config_service: ConfigService = request.app.state.config_service
    return PlainTextResponse(config_service.load_config_file_raw(path))


# save config file
@app.post("/api/save_config_file")
async def save_config_file(
    request: Request, data: SaveContent, admin: dict = Depends(get_current_admin)
):
    config_service: ConfigService = request.app.state.config_service
    return JSONResponse(config_service.save_config_file_raw(data.action, data.content))


# read MC server status
@app.get("/api/get_server_status")
async def api_get_server_status(
    request: Request, user: dict = Depends(get_current_user)
):
    """获取服务器状态"""
    return JSONResponse(
        {
            "status": "success",
            **await request.app.state.server_service.get_server_status(),
        }
    )


# 控制Minecraft服务器
@app.post("/api/control_server")
async def api_control_server(
    request: Request,
    control_info: ServerControl,
    admin: dict = Depends(get_current_admin),
):
    """控制Minecraft服务器"""
    server_service: ServerService = request.app.state.server_service
    result = server_service.control_server(control_info.action)
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)


@app.get("/api/server_logs")
async def api_get_server_logs(
    request: Request,
    start_line: int = 0,
    max_lines: int = 100,
    user: dict = Depends(get_current_user),
):
    """获取服务器日志"""
    return JSONResponse(
        {"status": "success", **request.app.state.server_service.get_logs(max_lines)}
    )


# 获取新增日志（基于计数器）
@app.get("/api/new_logs")
async def api_get_new_logs(
    request: Request,
    last_counter: int = 0,
    max_lines: int = 100,
    user: dict = Depends(get_current_user),
):
    """获取新增日志"""
    return JSONResponse(
        {
            "status": "success",
            **request.app.state.server_service.get_new_logs(last_counter, max_lines),
        }
    )


@app.get("/terminal")
async def terminal_page(request: Request, admin: dict = Depends(get_current_admin)):
    """提供终端日志页面 - 使用 React SPA"""
    return serve_spa_index(request)


# 获取命令补全建议
@app.get("/api/command_suggestions")
async def api_get_command_suggestions(
    request: Request, input: str = "", user: dict = Depends(get_current_user)
):
    """获取MCDR命令补全建议"""
    suggestions = await request.app.state.server_service.get_command_suggestions(input)
    return JSONResponse(
        {"status": "success", "suggestions": suggestions, "input": input}
    )


@app.post("/api/send_command")
async def api_send_command(request: Request, admin: dict = Depends(get_current_admin)):
    """发送命令到MCDR终端"""
    data = await request.json()
    server_service: ServerService = request.app.state.server_service
    result = await server_service.send_command(data.get("command", ""))
    status_code = (
        403
        if result.get("message") == "该命令已被禁止执行"
        else (200 if result.get("status") == "success" else 400)
    )
    return JSONResponse(result, status_code=status_code)


@app.get("/api/get_rcon_status")
async def api_get_rcon_status(request: Request, user: dict = Depends(get_current_user)):
    """获取RCON连接状态"""
    return JSONResponse(await request.app.state.server_service.get_rcon_status())


@app.get("/api/plugins/web_pages")
async def get_registered_web_pages(
    request: Request, user: dict = Depends(get_current_user)
):
    """获取所有已注册的插件网页列表"""
    server_interface = getattr(request.app.state, "server_interface", None)

    def _is_plugin_loaded(pid: str) -> bool:
        if server_interface is None:
            return True
        try:
            # 仅当插件当前仍处于“已加载”状态时，才暴露它的侧边栏页与 API
            return server_interface.get_plugin_instance(pid) is not None
        except Exception:
            # 异常不应导致 WebUI 全挂；保守起见仍然返回 True
            return True

    pages = [
        {
            "id": pid,
            "path": entry.html_path,
            "name": getattr(entry, "name", None),
        }
        for pid, entry in gugu_state.REGISTERED_PLUGIN_PAGES.items()
        if _is_plugin_loaded(pid)
    ]
    return JSONResponse({"status": "success", "pages": pages})


_PLUGIN_API_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")


def _query_params_to_dict(request: Request) -> dict[str, str | list[str]]:
    out: dict[str, str | list[str]] = {}
    for key in request.query_params.keys():
        values = request.query_params.getlist(key)
        if len(values) == 1:
            out[key] = values[0]
        else:
            out[key] = values
    return out


async def _parse_plugin_api_body(
    request: Request,
    *,
    upload_max_bytes: int,
) -> tuple[Any, Optional[int]]:
    """
    解析插件 API 请求体。支持 application/json、表单与 multipart 文件字段；其余返回 (None, 415)。
    GET/HEAD 等无体方法返回 (None, None)。

    multipart 中文件字段解析为 dict：
    ``{"type": "file", "filename", "content_type", "size", "data": bytes}``。
    单字段多值为列表；单值仍为标量。
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None, None

    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not content_type:
        return None, None

    if content_type == "application/json":
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return None, 400
        return body, None

    if content_type in (
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    ):
        form = await request.form()
        result: dict[str, Any] = {}
        for key in form.keys():
            raw_list = form.getlist(key)
            parsed: list[Any] = []
            for val in raw_list:
                if isinstance(val, UploadFile):
                    try:
                        data = await val.read()
                    finally:
                        await val.close()
                    if len(data) > upload_max_bytes:
                        return None, 413
                    parsed.append(
                        {
                            "type": "file",
                            "filename": val.filename,
                            "content_type": val.content_type,
                            "size": len(data),
                            "data": data,
                        }
                    )
                else:
                    parsed.append(val if isinstance(val, str) else str(val))
            if len(parsed) == 1:
                result[key] = parsed[0]
            else:
                result[key] = parsed
        return result, None

    return None, 415


async def _get_plugin_auth_info(
    request: Request,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    """
    Build auth context for plugin api_handler.

    Note: This is intentionally done in the plugin api proxy layer (not FastAPI Depends),
    so third-party plugins can read `params.auth` for authorization decisions.
    """
    username = current_user.get("username")
    auth_via = current_user.get("auth_via") or "cookie"

    # 是否管理员：复用现有 get_current_admin 的策略，但不把 403 直接抛给插件，
    # 而是让插件在 params.auth 里自行决定返回值。
    is_admin = False
    try:
        await get_current_admin(request, current_user=current_user)
        is_admin = True
    except HTTPException as e:
        if e.status_code != 403:
            raise
        is_admin = False

    # 是否超级管理员：基于配置的 super_admin_account 做布尔判断。
    is_super_admin = False
    try:
        config_service: ConfigService = request.app.state.config_service
        cfg = config_service.get_config()
        super_admin_account = str(cfg.get("super_admin_account"))
        is_super_admin = username is not None and str(username) == super_admin_account
    except Exception:
        is_super_admin = False

    return {
        "username": username,
        "auth_via": auth_via,
        "is_admin": is_admin,
        "is_super_admin": is_super_admin,
        "is_panel": auth_via == "panel_token" or username == "__panel__",
    }


async def _dispatch_plugin_api(
    plugin_id: str,
    url_path: str,
    request: Request,
    auth: dict[str, Any],
) -> Response:
    # 防止“旧注册表残留”：即使 dict 里还有条目，也要求插件当前仍已加载
    server_interface = getattr(request.app.state, "server_interface", None)
    if server_interface is not None:
        try:
            if server_interface.get_plugin_instance(plugin_id) is None:
                raise HTTPException(status_code=404, detail="Plugin not loaded")
        except HTTPException:
            raise
        except Exception:
            # 如遇到兼容性问题，避免导致整体不可用；继续走原逻辑
            pass

    entry = gugu_state.REGISTERED_PLUGIN_PAGES.get(plugin_id)
    if entry is None or entry.api_handler is None:
        raise HTTPException(status_code=404, detail="Plugin API handler not registered")

    # 兼容性：旧注册表条目（历史重载产生的 PluginPageEntry 实例）可能缺少 upload_max_bytes 字段。
    # 缺字段时回退到全局默认上限，避免 AttributeError 影响代理请求。
    entry_upload_max_bytes = getattr(entry, "upload_max_bytes", None)
    upload_max_bytes = (
        entry_upload_max_bytes
        if entry_upload_max_bytes is not None
        else PLUGIN_API_MAX_UPLOAD_BYTES
    )
    body, err_status = await _parse_plugin_api_body(
        request,
        upload_max_bytes=upload_max_bytes,
    )
    if err_status is not None:
        if err_status == 415:
            raise HTTPException(
                status_code=415,
                detail="Unsupported Content-Type; use application/json or form",
            )
        if err_status == 413:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {upload_max_bytes} bytes per field)",
            )
        raise HTTPException(status_code=err_status, detail="Invalid JSON body")

    params: PluginApiHandlerParams = {
        "method": request.method,
        "query": _query_params_to_dict(request),
        "body": body,
        "auth": auth,
    }

    handler = entry.api_handler
    try:
        if inspect.iscoroutinefunction(handler):
            result = await handler(url_path, params)
        else:
            result = await asyncio.to_thread(handler, url_path, params)
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Plugin API handler error: %s", plugin_id)
        raise HTTPException(status_code=500, detail=str(e)) from e

    if isinstance(result, Response):
        return result
    return JSONResponse(result)


@app.api_route(
    "/api/plugin/{plugin_id}",
    methods=list(_PLUGIN_API_METHODS),
)
async def plugin_api_root(
    plugin_id: str,
    request: Request,
    _user: dict = Depends(get_current_user),
):
    """插件 API 代理：子路径为空。"""
    auth_info = await _get_plugin_auth_info(request, _user)
    return await _dispatch_plugin_api(plugin_id, "", request, auth_info)


@app.api_route(
    "/api/plugin/{plugin_id}/{subpath:path}",
    methods=list(_PLUGIN_API_METHODS),
)
async def plugin_api_subpath(
    plugin_id: str,
    subpath: str,
    request: Request,
    _user: dict = Depends(get_current_user),
):
    """插件 API 代理：子路径为 url_path（如 abc 或 foo/bar）。"""
    auth_info = await _get_plugin_auth_info(request, _user)
    return await _dispatch_plugin_api(plugin_id, subpath, request, auth_info)


@app.get("/api/pim/plugin_repository")
async def api_get_plugin_repository(
    request: Request, plugin_id: str, user: dict = Depends(get_current_user)
):
    """获取插件所属的仓库信息"""
    result = request.app.state.plugin_service.get_plugin_repository(plugin_id)
    return JSONResponse(result)


@app.get("/api/pim/plugin_versions")
async def api_get_plugin_versions(
    request: Request,
    plugin_id: str,
    repo_url: str = None,
    user: dict = Depends(get_current_user),
):
    """获取插件版本列表"""
    versions = request.app.state.plugin_service.get_plugin_versions(plugin_id, repo_url)
    return JSONResponse({"success": True, "versions": versions or []})


@app.post("/api/pim/install_plugin")
async def api_pim_install_plugin(
    request: Request, body: PimInstallRequest, admin: dict = Depends(get_current_admin)
):
    """安装插件（PIM）"""
    if body.plugin_id == "guguwebui":
        return JSONResponse(
            {"success": False, "error": "不允许安装 WebUI 自身"}, status_code=400
        )
    try:
        task_id = await request.app.state.plugin_service.install_plugin(
            body.plugin_id, body.version, body.repo_url
        )
        return JSONResponse({"success": True, "task_id": task_id})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/pim/uninstall_plugin")
async def api_pim_uninstall_plugin(
    request: Request,
    body: PimUninstallRequest,
    admin: dict = Depends(get_current_admin),
):
    """卸载插件（PIM）"""
    if body.plugin_id == "guguwebui":
        return JSONResponse(
            {"success": False, "error": "不允许卸载 WebUI 自身"}, status_code=400
        )
    try:
        task_id = await request.app.state.plugin_service.uninstall_plugin(
            body.plugin_id
        )
        return JSONResponse({"success": True, "task_id": task_id})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/pim/update_plugin")
async def api_pim_update_plugin(
    request: Request, body: PimInstallRequest, admin: dict = Depends(get_current_admin)
):
    """更新插件（PIM），本质为指定版本安装"""
    if body.plugin_id == "guguwebui":
        return JSONResponse(
            {"success": False, "error": "不允许更新 WebUI 自身"}, status_code=400
        )
    try:
        task_id = await request.app.state.plugin_service.install_plugin(
            body.plugin_id, body.version, body.repo_url
        )
        return JSONResponse({"success": True, "task_id": task_id})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/pim/task_status")
async def api_pim_task_status(
    request: Request,
    task_id: str = None,
    plugin_id: str = None,
    user: dict = Depends(get_current_user),
):
    """获取 PIM 任务状态"""
    info = request.app.state.plugin_service.get_task_status(
        task_id=task_id, plugin_id=plugin_id
    )
    if task_id and info is None:
        return JSONResponse({"success": False, "task_info": None})
    return JSONResponse({"success": True, "task_info": info})


@app.post("/api/deepseek")
async def query_deepseek(
    request: Request,
    query_data: DeepseekQuery,
    admin: dict = Depends(get_current_admin),
):
    """向AI API发送问题并获取回答"""
    ai_service: AIService = request.app.state.ai_service
    result = await ai_service.query(
        query_data.query,
        query_data.model,
        query_data.api_key,
        query_data.api_url,
        query_data.system_prompt,
    )
    return JSONResponse({"status": "success", **result})


@app.get("/api/pip/list")
async def api_pip_list(request: Request, admin: dict = Depends(get_current_admin)):
    """获取已安装的pip包列表"""
    return JSONResponse(
        {"status": "success", "packages": request.app.state.pip_service.list_packages()}
    )


@app.post("/api/pip/install")
async def api_pip_install(
    request: Request,
    package_req: PipPackageRequest,
    admin: dict = Depends(get_current_admin),
):
    """安装pip包"""
    pip_service: PipService = request.app.state.pip_service
    return JSONResponse(
        {"status": "success", **pip_service.install_package(package_req.package)}
    )


@app.post("/api/pip/uninstall")
async def api_pip_uninstall(
    request: Request,
    package_req: PipPackageRequest,
    admin: dict = Depends(get_current_admin),
):
    """卸载pip包"""
    pip_service: PipService = request.app.state.pip_service
    return JSONResponse(
        {"status": "success", **pip_service.uninstall_package(package_req.package)}
    )


@app.get("/api/pip/task_status")
async def api_pip_task_status(
    request: Request, task_id: str, admin: dict = Depends(get_current_admin)
):
    """获取pip任务状态"""
    return JSONResponse(
        {"status": "success", **request.app.state.pip_service.get_task_status(task_id)}
    )


# ============================================================#
# 聊天页相关API端点
# ============================================================#


@app.post("/api/chat/generate_code")
async def chat_generate_code(request: Request):
    """生成聊天页验证码"""
    code, expire_minutes = request.app.state.chat_service.generate_verification_code()
    return JSONResponse(
        {"status": "success", "code": code, "expire_minutes": expire_minutes}
    )


@app.post("/api/chat/check_verification")
async def chat_check_verification(request: Request):
    """检查验证码验证状态"""
    data = await request.json()
    chat_service: ChatService = request.app.state.chat_service
    result = chat_service.check_verification_status(data.get("code", ""))
    return JSONResponse(
        result, status_code=(200 if result.get("status") != "error" else 400)
    )


@app.post("/api/chat/set_password")
async def chat_set_password(request: Request):
    """设置聊天页用户密码"""
    data = await request.json()
    chat_service: ChatService = request.app.state.chat_service
    result = await chat_service.set_user_password(
        data.get("code", ""), data.get("password", "")
    )
    return JSONResponse(
        result, status_code=(200 if result.get("status") != "error" else 400)
    )


@app.post("/api/chat/login")
async def chat_login(request: Request):
    """聊天页用户登录"""
    data, client_ip = await request.json(), (
        request.client.host if request.client else "unknown"
    )
    chat_service: ChatService = request.app.state.chat_service
    result = await chat_service.login(
        data.get("player_id", ""), data.get("password", ""), client_ip
    )
    status_code = 400 if result.get("status") == "error" else 200
    if status_code == 400 and "IP已达上限" in result.get("message", ""):
        status_code = 429
    return JSONResponse(result, status_code=status_code)


@app.post("/api/chat/check_session")
async def chat_check_session(request: Request):
    """检查聊天页会话状态"""
    data = await request.json()
    chat_service: ChatService = request.app.state.chat_service
    result = await chat_service.check_session(data.get("session_id", ""))
    return JSONResponse(
        result, status_code=(200 if result.get("status") != "error" else 400)
    )


@app.post("/api/chat/logout")
async def chat_logout(request: Request):
    """聊天页用户退出登录"""
    data = await request.json()
    chat_service: ChatService = request.app.state.chat_service
    result = chat_service.logout(data.get("session_id", ""))
    return JSONResponse(
        result, status_code=(200 if result.get("status") != "error" else 400)
    )


@app.post("/api/chat/get_messages")
async def get_chat_messages(request: Request):
    """获取聊天消息"""
    data, chat_service = await request.json(), request.app.state.chat_service
    result = await chat_service.get_messages(
        limit=data.get("limit", 50),
        offset=data.get("offset", 0),
        after_id=data.get("after_id"),
        before_id=data.get("before_id"),
    )
    return JSONResponse({"status": "success", **result})


@app.post("/api/chat/get_new_messages")
async def get_new_chat_messages(request: Request):
    """获取新消息（基于最后消息ID）"""
    data, chat_service = await request.json(), request.app.state.chat_service
    result = await chat_service.get_new_messages(
        after_id=data.get("after_id", 0), player_id_heartbeat=data.get("player_id")
    )
    return JSONResponse({"status": "success", **result})


@app.post("/api/chat/clear_messages")
async def chat_clear_messages(
    request: Request, admin: dict = Depends(get_current_admin)
):
    """清空聊天消息"""
    return JSONResponse(
        {"status": "success", **request.app.state.chat_service.clear_messages()}
    )


@app.get("/api/check_pim_status")
async def api_check_pim_status(
    request: Request, admin: dict = Depends(get_current_admin)
):
    """检查PIM插件的安装状态"""
    return JSONResponse(
        {"status": "success", **request.app.state.plugin_service.check_pim_status()}
    )


@app.get("/api/install_pim_plugin")
async def api_install_pim_plugin(
    request: Request, admin: dict = Depends(get_current_admin)
):
    """将PIM作为独立插件安装"""
    return JSONResponse(
        {
            "status": "success",
            **await request.app.state.plugin_service.install_pim_plugin_action(),
        }
    )


@app.post("/api/self_update")
async def api_self_update(request: Request, admin: dict = Depends(get_current_admin)):
    """执行 WebUI 自身更新"""
    return JSONResponse(
        {"status": "success", **request.app.state.plugin_service.self_update()}
    )


@app.get("/api/self_update_info")
async def api_get_self_update_info(
    request: Request, admin: dict = Depends(get_current_admin)
):
    """获取 WebUI 自身更新信息"""
    return JSONResponse(
        content={
            "success": True,
            "info": getattr(
                request.app.state, "self_update_info", {"available": False}
            ),
        }
    )


@app.post("/api/chat/send_message")
async def send_chat_message(request: Request, user: dict = Depends(get_current_user)):
    """发送聊天消息到游戏"""
    data = await request.json()
    player_id = data.get("player_id", "")
    chat_service: ChatService = request.app.state.chat_service
    result = await chat_service.send_message(
        data.get("message", "").strip(),
        player_id,
        data.get("session_id", ""),
        (user and user.get("username") == player_id),
    )
    return JSONResponse(
        result, status_code=chat_service.get_status_code_for_result(result)
    )
