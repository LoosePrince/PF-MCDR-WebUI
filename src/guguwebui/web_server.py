import asyncio
import datetime
import json
import logging
import secrets
import uuid
from pathlib import Path
from typing import Optional

import aiohttp
from fastapi import Body, Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from mcdreforged.api.event import MCDRPluginEvents
from mcdreforged.api.types import PluginServerInterface
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from guguwebui.constant import *
from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.PIM import initialize_pim
from guguwebui.services.ai_service import AIService
from guguwebui.services.auth_service import AuthService
from guguwebui.services.chat_service import ChatService
from guguwebui.services.config_service import ConfigService
from guguwebui.services.file_service import FileService
from guguwebui.services.pip_service import PipService
from guguwebui.services.plugin_service import PluginService
from guguwebui.services.server_service import ServerService
from guguwebui.state import RCON_ONLINE_CACHE, REGISTERED_PLUGIN_PAGES, pip_tasks
from guguwebui.structures import (
    BusinessException,
    ConfigData,
    DeepseekQuery,
    PimInstallRequest,
    PimUninstallRequest,
    PipPackageRequest,
    PluginInfo,
    SaveConfig,
    SaveContent,
    ServerControl,
    ToggleConfig,
)
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
    content = content.replace(
        "<head>", f'<head><base href="{root_path}">{config_script}'
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


def _get_target_server_id(request: Request) -> str:
    # header 优先，其次 query
    sid = (request.headers.get("X-Target-Server") or "").strip()
    if not sid:
        sid = (request.query_params.get("serverId") or "").strip()
    return sid or "local"


def _is_proxy_candidate_path(path: str) -> bool:
    # 只代理 /api/*，并排除主服本地必须处理的少量端点
    if not path.startswith("/api/"):
        return False
    # 登录/登出/校验登录：必须由主服本地处理（cookie 建立在主服域）
    if path in ["/api/login", "/api/logout", "/api/checkLogin", "/api/servers", "/api/panel_merge_config"]:
        return False
    # OpenAPI 文档与语言列表也保持主服本地（避免跨服混淆）
    if path in ["/api/langs"]:
        return False
    # 在线插件列表等大数据：永远走本地，避免无意义传输
    if path in ["/api/online-plugins"]:
        return False
    # 配对连接：永远走本地（避免跨服代理导致握手混乱）
    if path.startswith("/api/pairing/"):
        return False
    return True


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _get_pairing_state(app_: FastAPI) -> dict:
    state = getattr(app_.state, "pairing_state", None)
    if state is None:
        state = {
            "enabled_until": None,  # datetime
            "pending": {},  # request_id -> {ip,name,created_at}
            "results": {},  # request_id -> {status, token?}
            "connects": {},  # connect_id -> {base_url, request_id, slave_name, created_at}
        }
        app_.state.pairing_state = state
    return state


def _is_admin_api_path(path: str) -> bool:
    # 近似映射：需要管理员权限的接口集合（与路由 Depends(get_current_admin) 对齐）
    admin_exact = {
        "/api/toggle_plugin",
        "/api/reload_plugin",
        "/api/save_config",
        "/api/setup_rcon",
        "/api/save_file",
        "/api/save_config_file",
        "/api/control_server",
        "/api/send_command",
        "/api/self_update",
        "/api/pip/list",
        "/api/pip/install",
        "/api/pip/uninstall",
        "/api/pip/task_status",
        "/api/pim/install_plugin",
        "/api/pim/uninstall_plugin",
        "/api/pim/update_plugin",
        "/api/chat/clear_messages",
        "/api/install_pim_plugin",
        "/api/check_pim_status",
        "/api/deepseek",
        "/api/online-plugins",
    }
    if path in admin_exact:
        return True
    # /api/pim/* 基本都是管理员
    if path.startswith("/api/pim/"):
        return True
    # 兜底：pip 相关均视为管理员
    if path.startswith("/api/pip/"):
        return True
    return False


async def _proxy_request_to_slave(request: Request, slave: dict, sub_path: str) -> Response:
    """
    将主服请求代理到子服的 /api/{sub_path}
    - 注入 X-Panel-Token
    - 不透传 Cookie / Set-Cookie
    """
    base_url = str(slave.get("base_url", "")).rstrip("/")
    target_url = f"{base_url}/api/{sub_path.lstrip('/')}"

    # query：移除 serverId，避免子服再处理
    query = list(request.query_params.multi_items())
    query = [(k, v) for (k, v) in query if k != "serverId"]

    body = await request.body()

    headers = {}
    for k, v in request.headers.items():
        lk = k.lower()
        if lk in {"host", "content-length", "cookie"}:
            continue
        headers[k] = v

    headers["X-Panel-Token"] = str(slave.get("token", "")).strip()
    headers["X-Forwarded-For"] = request.client.host if request.client else ""

    verify_tls = bool(slave.get("verify_tls", True))
    session: aiohttp.ClientSession = app.state.http_session
    async with session.request(
        method=request.method,
        url=target_url,
        params=query,
        data=body if body else None,
        headers=headers,
        ssl=verify_tls,
    ) as resp:
        resp_body = await resp.read()
        # 过滤 set-cookie，避免子服 cookie 覆盖主服
        out_headers = {}
        for k, v in resp.headers.items():
            lk = k.lower()
            if lk in {"set-cookie", "content-length", "transfer-encoding", "connection"}:
                continue
            out_headers[k] = v
        return Response(content=resp_body, status_code=resp.status, headers=out_headers)


class ApiProxyDispatchMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            server_id = _get_target_server_id(request)
            if server_id == "local":
                return await call_next(request)

            # 仅主服模式启用代理
            config_service: ConfigService = getattr(request.app.state, "config_service", None)
            if config_service is None:
                return await call_next(request)
            server_config = config_service.get_config()
            if server_config.get("panel_role", "master") != "master":
                return await call_next(request)

            if not _is_proxy_candidate_path(request.url.path):
                return await call_next(request)

            # 主服本地先做权限判定（你的设想：权限在主服判定）
            if _is_admin_api_path(request.url.path):
                current_user = await get_current_user(request)
                await get_current_admin(request, current_user=current_user)
            else:
                await get_current_user(request)

            # 查找子服
            slaves = server_config.get("panel_slaves") or []
            slave = None
            for s in slaves:
                if not isinstance(s, dict):
                    continue
                if not s.get("enabled", True):
                    continue
                if str(s.get("id", "")).strip() == server_id:
                    slave = s
                    break
            if slave is None:
                return JSONResponse(
                    {"status": "error", "message": f"Unknown serverId: {server_id}"},
                    status_code=400,
                )

            sub_path = request.url.path[len("/api/") :]
            return await _proxy_request_to_slave(request, slave, sub_path)
        except HTTPException:
            raise
        except Exception as e:
            request.app.state.server_interface.logger.error(f"代理请求失败: {e}", exc_info=True)
            return JSONResponse(
                {"status": "error", "message": "Proxy request failed"},
                status_code=502,
            )


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


@app.get("/api/panel_merge_config")
async def api_get_panel_merge_config(
    request: Request, user: dict = Depends(get_current_user)
):
    """获取多服面板合并配置（仅本地，不参与代理）。"""
    cfg = request.app.state.config_service.get_config()
    return JSONResponse(
        {
            "status": "success",
            "panel_role": cfg.get("panel_role", "master"),
            "panel_slaves": cfg.get("panel_slaves", []) or [],
            "panel_master": cfg.get(
                "panel_master", {"allowed_tokens": [], "allowed_master_ips": []}
            )
            or {"allowed_tokens": [], "allowed_master_ips": []},
        }
    )


@app.post("/api/panel_merge_config")
async def api_save_panel_merge_config(
    request: Request, admin: dict = Depends(get_current_admin)
):
    """保存多服面板合并配置（仅本地，不参与代理）。"""
    body = await request.json()
    config_service: ConfigService = request.app.state.config_service
    web_config = config_service.get_config()

    panel_role = body.get("panel_role")
    if panel_role is not None:
        web_config["panel_role"] = panel_role
    panel_slaves = body.get("panel_slaves")
    if panel_slaves is not None:
        web_config["panel_slaves"] = panel_slaves if isinstance(panel_slaves, list) else []
    panel_master = body.get("panel_master")
    if panel_master is not None:
        web_config["panel_master"] = (
            panel_master
            if isinstance(panel_master, dict)
            else {"allowed_tokens": [], "allowed_master_ips": []}
        )

    try:
        config_dir = request.app.state.server_interface.get_data_folder()
        Path(config_dir).mkdir(parents=True, exist_ok=True)
        config_path = Path(config_dir) / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(web_config, f, ensure_ascii=False, indent=4)
        return JSONResponse(
            {
                "status": "success",
                "message": "多服配置已保存",
                "data": {
                    "panel_role": web_config.get("panel_role", "master"),
                    "panel_slaves": web_config.get("panel_slaves", []) or [],
                    "panel_master": web_config.get("panel_master", {}) or {},
                },
            }
        )
    except Exception as e:
        logger = getattr(
            request.app.state.server_interface, "logger", logging.getLogger(__name__)
        )
        logger.error(f"保存多服配置文件时出错: {e}", exc_info=True)
        return JSONResponse(
            {"status": "error", "message": f"保存多服配置失败: {str(e)}"}, status_code=500
        )


# ============================================================#
# 配对连接（快捷模式）
# ============================================================#


@app.post("/api/pairing/enable")
async def api_pairing_enable(request: Request, admin: dict = Depends(get_current_admin)):
    """子服：开始接受连接（5分钟）；收到第一个连接请求后自动关闭。"""
    cfg = request.app.state.config_service.get_config()
    if cfg.get("panel_role", "master") != "slave":
        return JSONResponse(
            {"status": "error", "message": "仅子服模式可开启接受连接"},
            status_code=400,
        )
    st = _get_pairing_state(request.app)
    expires_at = _now_utc() + datetime.timedelta(minutes=5)
    st["enabled_until"] = expires_at
    return JSONResponse(
        {"status": "success", "expires_at": expires_at.isoformat()},
        status_code=200,
    )


@app.post("/api/pairing/disable")
async def api_pairing_disable(request: Request, admin: dict = Depends(get_current_admin)):
    """子服：停止接受连接。"""
    cfg = request.app.state.config_service.get_config()
    if cfg.get("panel_role", "master") != "slave":
        return JSONResponse(
            {"status": "error", "message": "仅子服模式可停止接受连接"},
            status_code=400,
        )
    st = _get_pairing_state(request.app)
    st["enabled_until"] = None
    return JSONResponse({"status": "success"})


@app.post("/api/pairing/request")
async def api_pairing_request(request: Request):
    """主服 -> 子服：发起连接请求（无需登录，但仅在子服开启接受连接窗口时有效）。"""
    cfg = request.app.state.config_service.get_config()
    if cfg.get("panel_role", "master") != "slave":
        return JSONResponse(
            {"status": "error", "message": "仅子服模式可接受连接请求"},
            status_code=400,
        )
    st = _get_pairing_state(request.app)
    enabled_until = st.get("enabled_until")
    if not enabled_until or _now_utc() > enabled_until:
        st["enabled_until"] = None
        return JSONResponse(
            {"status": "error", "message": "当前未开启接受连接或已超时"},
            status_code=403,
        )

    data = {}
    try:
        data = await request.json()
    except Exception:
        data = {}
    master_name = str(data.get("master_name", "")).strip()
    slave_name = str(data.get("slave_name", "")).strip()
    request_id = uuid.uuid4().hex
    ip = request.client.host if request.client else ""
    st["pending"][request_id] = {
        "request_id": request_id,
        "ip": ip,
        "master_name": master_name,
        "slave_name": slave_name,
        "created_at": _now_utc().isoformat(),
    }
    st["results"][request_id] = {"status": "pending"}
    # 收到第一个请求后关闭
    st["enabled_until"] = None
    return JSONResponse({"status": "pending", "request_id": request_id})


@app.get("/api/pairing/pending")
async def api_pairing_pending(request: Request, admin: dict = Depends(get_current_admin)):
    """子服：获取待确认的连接请求列表。"""
    st = _get_pairing_state(request.app)
    pending = list(st.get("pending", {}).values())
    return JSONResponse({"status": "success", "pending": pending})


@app.post("/api/pairing/deny")
async def api_pairing_deny(request: Request, admin: dict = Depends(get_current_admin)):
    """子服：拒绝连接请求。"""
    body = await request.json()
    request_id = str(body.get("request_id", "")).strip()
    st = _get_pairing_state(request.app)
    st.get("pending", {}).pop(request_id, None)
    st["results"][request_id] = {"status": "denied"}
    return JSONResponse({"status": "success"})


@app.post("/api/pairing/accept")
async def api_pairing_accept(request: Request, admin: dict = Depends(get_current_admin)):
    """子服：接受连接请求，生成 token，保存到 panel_master.allowed_tokens。"""
    cfg = request.app.state.config_service.get_config()
    if cfg.get("panel_role", "master") != "slave":
        return JSONResponse(
            {"status": "error", "message": "仅子服模式可接受连接"},
            status_code=400,
        )
    body = await request.json()
    request_id = str(body.get("request_id", "")).strip()
    st = _get_pairing_state(request.app)
    pending = st.get("pending", {}).get(request_id)
    if not pending:
        return JSONResponse(
            {"status": "error", "message": "连接请求不存在或已处理"},
            status_code=404,
        )

    token = secrets.token_hex(16)
    panel_master = cfg.get("panel_master") or {"allowed_tokens": [], "allowed_master_ips": []}
    allowed = panel_master.get("allowed_tokens") or []
    allowed.append(
        {
            "token": token,
            "enabled": True,
            "name": pending.get("master_name") or "master",
            "created_at": _now_utc().isoformat(),
        }
    )
    panel_master["allowed_tokens"] = allowed
    cfg["panel_master"] = panel_master

    # 写入配置文件（与 panel_merge_config 一致的落盘路径）
    try:
        config_dir = request.app.state.server_interface.get_data_folder()
        Path(config_dir).mkdir(parents=True, exist_ok=True)
        config_path = Path(config_dir) / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger = getattr(
            request.app.state.server_interface, "logger", logging.getLogger(__name__)
        )
        logger.error(f"保存子服配对配置失败: {e}", exc_info=True)
        return JSONResponse(
            {"status": "error", "message": "保存配置失败"}, status_code=500
        )

    st.get("pending", {}).pop(request_id, None)
    st["results"][request_id] = {"status": "accepted", "token": token}
    return JSONResponse({"status": "success", "request_id": request_id})


@app.get("/api/pairing/status")
async def api_pairing_status(request: Request, request_id: str):
    """主服/外部：查询连接请求状态。accepted 时返回 token。"""
    st = _get_pairing_state(request.app)
    res = st.get("results", {}).get(request_id)
    if not res:
        return JSONResponse({"status": "unknown"}, status_code=404)
    return JSONResponse(res)


@app.post("/api/pairing/connect_request")
async def api_pairing_connect_request(
    request: Request, admin: dict = Depends(get_current_admin)
):
    """主服：向子服发起连接请求（服务端到服务端，避免浏览器跨域）。"""
    cfg = request.app.state.config_service.get_config()
    if cfg.get("panel_role", "master") != "master":
        return JSONResponse(
            {"status": "error", "message": "仅主服模式可发起连接"},
            status_code=400,
        )
    body = await request.json()
    slave_name = str(body.get("slave_name", "")).strip()
    base_url = str(body.get("base_url", "")).strip().rstrip("/")
    master_name = str(body.get("master_name", "master")).strip()
    if not slave_name or not base_url:
        return JSONResponse(
            {"status": "error", "message": "slave_name/base_url 不能为空"},
            status_code=400,
        )

    connect_id = uuid.uuid4().hex
    session: aiohttp.ClientSession = request.app.state.http_session
    try:
        async with session.post(
            f"{base_url}/api/pairing/request",
            json={"master_name": master_name, "slave_name": slave_name},
        ) as resp:
            data = await resp.json()
            if resp.status != 200 or data.get("status") != "pending":
                return JSONResponse(
                    {"status": "error", "message": data.get("message", "连接请求失败")},
                    status_code=502,
                )
            request_id = data.get("request_id")
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"连接请求失败: {str(e)}"},
            status_code=502,
        )

    st = _get_pairing_state(request.app)
    st["connects"][connect_id] = {
        "connect_id": connect_id,
        "request_id": request_id,
        "base_url": base_url,
        "slave_name": slave_name,
        "created_at": _now_utc().isoformat(),
    }
    return JSONResponse(
        {"status": "pending", "connect_id": connect_id, "request_id": request_id}
    )


@app.get("/api/pairing/connect_status")
async def api_pairing_connect_status(
    request: Request, connect_id: str, admin: dict = Depends(get_current_admin)
):
    """主服：轮询子服状态；accepted 后自动保存子服配置（含 token）。"""
    st = _get_pairing_state(request.app)
    rec = st.get("connects", {}).get(connect_id)
    if not rec:
        return JSONResponse(
            {"status": "error", "message": "connect_id 不存在"}, status_code=404
        )
    base_url = rec["base_url"]
    request_id = rec["request_id"]
    session: aiohttp.ClientSession = request.app.state.http_session
    try:
        async with session.get(
            f"{base_url}/api/pairing/status", params={"request_id": request_id}
        ) as resp:
            data = await resp.json()
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"查询子服状态失败: {str(e)}"},
            status_code=502,
        )

    if data.get("status") == "pending":
        return JSONResponse({"status": "pending"})
    if data.get("status") == "denied":
        st.get("connects", {}).pop(connect_id, None)
        return JSONResponse({"status": "denied"})
    if data.get("status") != "accepted":
        return JSONResponse({"status": "error", "message": "状态异常"}, status_code=502)

    token = str(data.get("token", "")).strip()
    if not token:
        return JSONResponse(
            {"status": "error", "message": "子服未返回 token"}, status_code=502
        )

    # 自动保存到 panel_slaves
    cfg = request.app.state.config_service.get_config()
    slaves = cfg.get("panel_slaves") or []
    if not isinstance(slaves, list):
        slaves = []

    # 生成 id：基于名称，保证唯一
    base_id = "".join([c.lower() if c.isalnum() else "_" for c in rec["slave_name"]]).strip("_") or "slave"
    existing_ids = {str(s.get("id")) for s in slaves if isinstance(s, dict)}
    sid = base_id
    i = 1
    while sid in existing_ids:
        i += 1
        sid = f"{base_id}_{i}"

    slaves.append(
        {
            "id": sid,
            "name": rec["slave_name"],
            "base_url": base_url,
            "token": token,
            "enabled": True,
            "verify_tls": True,
        }
    )
    cfg["panel_slaves"] = slaves

    try:
        config_dir = request.app.state.server_interface.get_data_folder()
        Path(config_dir).mkdir(parents=True, exist_ok=True)
        config_path = Path(config_dir) / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"保存主服配置失败: {str(e)}"},
            status_code=500,
        )

    st.get("connects", {}).pop(connect_id, None)
    return JSONResponse(
        {
            "status": "accepted",
            "server": {"id": sid, "name": rec["slave_name"], "base_url": base_url},
        }
    )


@app.get("/api/servers")
async def api_list_servers(request: Request, user: dict = Depends(get_current_user)):
    """获取可用的服务器列表（主服 + 子服）"""
    config_service: ConfigService = request.app.state.config_service
    cfg = config_service.get_config()
    servers = [{"id": "local", "name": "local", "enabled": True, "isLocal": True}]
    for s in (cfg.get("panel_slaves") or []):
        if not isinstance(s, dict):
            continue
        servers.append(
            {
                "id": str(s.get("id", "")).strip(),
                "name": s.get("name") or s.get("id") or "",
                "enabled": bool(s.get("enabled", True)),
                "isLocal": False,
            }
        )
    # 过滤空 id
    servers = [x for x in servers if x.get("id")]
    return JSONResponse({"status": "success", "servers": servers})


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
    pages = [{"id": pid, "path": path} for pid, path in REGISTERED_PLUGIN_PAGES.items()]
    return JSONResponse({"status": "success", "pages": pages})


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
