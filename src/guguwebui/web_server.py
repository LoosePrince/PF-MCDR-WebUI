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
from guguwebui.routers.audit_router import router as audit_router
from guguwebui.routers.chat_router import router as chat_router
from guguwebui.routers.config_router import router as config_router
from guguwebui.routers.pim_router import router as pim_router
from guguwebui.routers.pip_router import router as pip_router
from guguwebui.routers.plugin_management_router import \
    router as plugin_management_router
from guguwebui.routers.plugin_proxy_router import router as plugin_proxy_router
from guguwebui.routers.server_router import router as server_router
from guguwebui.services.ai_service import AIService
from guguwebui.services.auth_service import AuthService
from guguwebui.services.chat_service import ChatService
from guguwebui.services.config_service import ConfigService
from guguwebui.services.file_service import FileService
from guguwebui.services.pip_service import PipService
from guguwebui.services.plugin_service import PluginService
from guguwebui.services.qq_qr_login_service import QQQRCodeLoginService
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


# 全局 LogWatcher 实例
log_watcher = None

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

    server_config = server_instance.load_config_simple(
        "config.json", DEFALUT_CONFIG, echo_in_console=False
    )
    log_capture_compat_mode = server_config.get("log_capture_compat_mode", False)

    # 初始化 LogWatcher，根据配置选择捕获模式
    log_watcher = LogWatcher(
        server_interface=server_instance,
        compat_mode=log_capture_compat_mode,
    )

    if not log_capture_compat_mode:
        # 标准模式：连接 MCDR 内部日志系统
        log_watcher._setup_log_capture()

    # 仅标准模式注册事件监听，兼容模式通过读文件获取日志
    # 双事件统一交给 on_server_output，由 LogWatcher 做去重与内容兜底提取：
    # - GENERAL_INFO 覆盖面更广（含服务端输出）
    # - USER_INFO 在部分环境下可补充用户来源信息
    if not log_capture_compat_mode:
        server_instance.register_event_listener(
            MCDRPluginEvents.GENERAL_INFO, on_server_output
        )
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

    if log_capture_compat_mode:
        server_instance.logger.info("WebUI 日志捕获兼容模式已启用，将通过读取日志文件获取日志")
    else:
        server_instance.logger.debug("WebUI 日志捕获器已初始化，将直接从 MCDR 捕获日志")


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


@app.post("/api/login/qq_qr/start")
async def qq_qr_login_start(request: Request):
    """
    启动 QQ 扫码登录。
    返回：
      - code：轮询用的 code
      - qrImageUrl：二维码图片地址
    """
    qr = await asyncio.to_thread(QQQRCodeLoginService.request_login_code)
    return JSONResponse(
        {
            "status": "success",
            "code": qr.get("code", ""),
            "qrImageUrl": qr.get("qrImageUrl", ""),
        }
    )


@app.get("/api/login/qq_qr/status")
async def qq_qr_login_status(request: Request, code: str = ""):
    """
    轮询 QQ 扫码登录状态；成功后会直接在本次响应中写入 token cookie。
    """
    if not code:
        return JSONResponse(
            {"status": "error", "message": "Missing qq login code。"},
            status_code=400,
        )

    result = await asyncio.to_thread(QQQRCodeLoginService.query_status, code)
    state = str(result.get("state", "error"))

    if state == "wait":
        return JSONResponse(
            {
                "status": "success",
                "state": "wait",
                "message": "正在等待扫码登录...",
                "ret": "66",
            }
        )

    if state == "used":
        return JSONResponse(
            {
                "status": "success",
                "state": "used",
                "message": "二维码已过期，请重新开始扫码登录。",
                "ret": "65",
            }
        )

    if state == "ok":
        uin = str(result.get("uin", "") or "")
        if not uin:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "扫码成功，但未获取到 QQ uin。",
                },
                status_code=500,
            )
        return await request.app.state.auth_service.login_with_account(
            request=request,
            account=uin,
            remember=False,
            state="ok",
        )

    return JSONResponse(
        {
            "status": "success",
            "state": "error",
            "message": f"扫码状态查询失败：{result.get('msg', '')}",
        },
        status_code=200,
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
app.include_router(panel_merge_router, prefix="/api") # 合并面板
app.include_router(plugin_management_router, prefix="/api") # 插件管理
app.include_router(config_router, prefix="/api") # 配置
app.include_router(server_router, prefix="/api") # 服务器
app.include_router(plugin_proxy_router, prefix="/api") # 插件代理
app.include_router(pim_router, prefix="/api") # PIM
app.include_router(pip_router, prefix="/api") # PIP
app.include_router(chat_router, prefix="/api") # 聊天
app.include_router(audit_router, prefix="/api") # 操作审计


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

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    server_service: ServerService = request.app.state.server_service
    if not server_service.is_public_chat_enabled():
        return serve_spa_index(request)  # 返回 SPA，由前端处理 404
    return serve_spa_index(request)

@app.get("/player-chat", response_class=HTMLResponse)
async def player_chat_page(request: Request):
    server_service: ServerService = request.app.state.server_service
    if not server_service.is_public_chat_enabled():
        return serve_spa_index(request)  # 返回 SPA，由前端处理 404
    return serve_spa_index(request)


@app.get("/terminal", response_class=HTMLResponse)
async def terminal_page(request: Request, admin: dict = Depends(get_current_admin)):
    """提供终端日志页面 - 使用 React SPA"""
    return serve_spa_index(request)

@app.get("/operation-logs", response_class=HTMLResponse)
async def operation_logs_page(request: Request, admin: dict = Depends(get_current_admin)):
    """操作记录（只读）"""
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


def _is_admin_user(request: Request, user: dict) -> bool:
    """与 get_current_admin 一致，不抛异常。"""
    if user.get("auth_via") == "panel_token":
        return True
    config_service = request.app.state.config_service
    server_config = config_service.get_config()
    super_admin_account = str(server_config.get("super_admin_account"))
    disable_other_admin = server_config.get("disable_other_admin", False)
    username = user.get("username")
    if disable_other_admin and str(username) != super_admin_account:
        return False
    return True


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
        "nickname": nickname,
        "is_admin": _is_admin_user(request, user),
    })

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


# ============================================================#
# 聊天页相关API端点
# ============================================================#


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

