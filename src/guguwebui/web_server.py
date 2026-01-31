import datetime
import javaproperties
import secrets
import aiohttp
import asyncio
import requests
import os
import json
import lzma
import time
import io
import importlib
import uuid
import logging
import inspect
import subprocess
import sys
from typing import Dict, List, Any, Optional, Union, Tuple
from packaging.version import parse as parse_version

from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request, status, HTTPException, Body
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    JSONResponse,
    PlainTextResponse,
    FileResponse,
)
from ruamel.yaml.comments import CommentedSeq
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .utils.log_watcher import LogWatcher
from .utils.PIM import PluginInstaller, create_installer, initialize_pim  # 修改导入，添加 initialize_pim

from .utils.constant import *
from .utils.server_util import *
from .utils.table import yaml
from .utils.utils import *

from mcdreforged.api.all import MCDRPluginEvents

# 导入聊天API模块和全局变量
from .api.chat import (
    generate_chat_verification_code, check_chat_verification_status,
    set_chat_user_password, chat_user_login, check_chat_session,
    chat_user_logout, get_chat_messages_handler, get_new_chat_messages_handler,
    clear_chat_messages_handler, send_chat_message_handler,
    WEB_ONLINE_PLAYERS, RCON_ONLINE_CACHE,
    on_player_joined, on_player_left
)

# 导入插件API模块
from .api.plugins import (
    install_plugin, update_plugin, uninstall_plugin,
    task_status, get_plugin_versions_v2, get_plugin_repository,
    check_pim_status, install_pim_plugin, toggle_plugin,
    reload_plugin, get_online_plugins
)

# 导入配置API模块
from .api.config import (
    list_config_files, get_web_config, save_web_config,
    load_config, save_config, setup_rcon_config
)

# 导入服务器API模块
from .api.server import (
    get_server_status, control_server, get_server_logs,
    get_new_logs, get_command_suggestions, send_command, get_rcon_status
)

# 获取插件真实版本号已移至 utils.py

app = FastAPI(
    title="GUGU WebUI",
    description="MCDR WebUI 管理界面",
    version=get_plugin_version(),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# URL路径处理函数已移至 utils.py

# SPA 入口文件路径
static_index_path = Path(STATIC_PATH) / "static" / "index.html"

def serve_spa_index(request: Request) -> FileResponse:
    """返回 SPA 的 index.html 文件，用于客户端路由"""
    if static_index_path.exists():
        return FileResponse(str(static_index_path))
    else:
        # 如果 index.html 不存在，返回简单的错误页面
        return HTMLResponse(
            content="<h1>前端文件未找到</h1><p>请确保已构建前端项目（运行 npm run build）</p>",
            status_code=404
        )

# 全局LogWatcher实例
log_watcher = LogWatcher()

# 用于保存pip任务状态的字典
pip_tasks = {}

# 尝试迁移旧配置
migrate_old_config()


# 事件处理函数已移至 api/chat.py


# 初始化函数，在应用程序启动时调用
def init_app(server_instance):
    """初始化应用程序，注册事件监听器"""
    global log_watcher
    
    # 存储服务器接口
    app.state.server_interface = server_instance
    
    # 确保user_db包含所有必要的键
    try:
        from .utils.constant import user_db, DEFALUT_DB
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
    # 修正：GENERAL_INFO应该映射到on_mcdr_info，处理MCDR和服务器的常规信息
    # USER_INFO应该映射到on_server_output，处理用户输入的命令
    server_instance.register_event_listener(MCDRPluginEvents.GENERAL_INFO, on_mcdr_info)
    server_instance.register_event_listener(MCDRPluginEvents.USER_INFO, on_server_output)
    # 注册玩家进出事件，刷新RCON在线缓存
    server_instance.register_event_listener(MCDRPluginEvents.PLAYER_JOINED, on_player_joined)
    server_instance.register_event_listener(MCDRPluginEvents.PLAYER_LEFT, on_player_left)
    
    # 初始化PIM模块
    try:
        server_instance.logger.debug("正在初始化内置PIM模块...")
        pim_helper, plugin_installer = initialize_pim(server_instance)
        # 将初始化后的PIM实例存储到app.state中，供API调用
        app.state.pim_helper = pim_helper
        app.state.plugin_installer = plugin_installer
        if pim_helper and plugin_installer:
            server_instance.logger.info("内置PIM模块初始化成功")
        else:
            server_instance.logger.warning("内置PIM模块初始化部分失败，某些功能可能不可用")
            
        # 在启动时检查插件仓库缓存
        check_repository_cache(server_instance)
    except Exception as e:
        server_instance.logger.error(f"内置PIM模块初始化失败: {e}")
    
    server_instance.logger.debug("WebUI日志捕获器已初始化，将直接从MCDR捕获日志")

# check_repository_cache 函数已移至 utils.py

# 事件处理函数
def on_server_output(server, info):
    """处理服务器输出事件"""
    global log_watcher
    if log_watcher:
        log_watcher.on_server_output(server, info)

def on_mcdr_info(server, info):
    """处理MCDR信息事件"""
    global log_watcher
    if log_watcher:
        log_watcher.on_mcdr_info(server, info)


# 语言列表 API：返回 /lang 目录下的 json 文件及其显示名称
@app.get("/api/langs")
def get_languages():
    try:
        lang_dir = Path(STATIC_PATH) / "lang"
        if not lang_dir.exists():
            return JSONResponse([], status_code=200)

        # 常见语言的默认显示名映射
        default_names = {
            "zh-CN": "中文",
            "zh-TW": "繁體中文",
            "en-US": "English",
            "ja-JP": "日本語",
            "ko-KR": "한국어",
            "ru-RU": "Русский",
            "fr-FR": "Français",
            "de-DE": "Deutsch",
            "es-ES": "Español",
            "pt-BR": "Português (Brasil)",
            "vi-VN": "Tiếng Việt",
            "tr-TR": "Türkçe",
            "ar-SA": "العربية",
            "it-IT": "Italiano",
            "pl-PL": "Polski",
            "uk-UA": "Українська",
            "id-ID": "Bahasa Indonesia",
            "th-TH": "ไทย",
            "hi-IN": "हिन्दी"
        }

        langs = []
        for file in sorted(lang_dir.glob("*.json")):
            code = file.stem
            name = default_names.get(code, code)
            # 如果文件里包含更友好的显示名，优先使用
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    meta = data.get("meta") or {}
                    if isinstance(meta, dict):
                        display = meta.get("name")
                        if isinstance(display, str) and display.strip():
                            name = display.strip()
            except Exception:
                pass
            langs.append({"code": code, "name": name})
        return JSONResponse(langs, status_code=200)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ============================================================#

# redirect to login
@app.get("/", name="root")
def read_root(request: Request):
    return RedirectResponse(url=get_redirect_url(request, "/login"))


# login page - 使用 React SPA
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # token is valid
    token = request.cookies.get("token")
    server:PluginServerInterface = app.state.server_interface
    server_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)

    disable_other_admin = server_config.get("disable_other_admin", False)
    super_admin_account = server_config.get("super_admin_account")

    def login_admin_check(account, disable_other_admin, super_admin_account):
        if disable_other_admin and account != super_admin_account:
            return False
        return True

    if (
        token
        and user_db["token"].get(token)
        and user_db["token"][token]["expire_time"]
        > str(datetime.datetime.now(datetime.timezone.utc))
        and login_admin_check(user_db["token"][token]["user_name"], disable_other_admin, super_admin_account)
    ):
        request.session["logged_in"] = True
        request.session["token"] = token
        request.session["username"] = user_db["token"][token]["user_name"]
        
        return RedirectResponse(url=get_redirect_url(request, "/index"), status_code=status.HTTP_302_FOUND)

    # no token / expired token - 返回 SPA index.html
    response = serve_spa_index(request)
    if token:
        if token in user_db["token"]:
            del user_db["token"][token]
            user_db.save()
        
        # 删除过期token的cookie，确保在不同模式下都能正确删除
        root_path = request.scope.get("root_path", "")
        if root_path:
            # fastapi_mcdr模式下，删除cookie时需要指定正确的路径
            response.delete_cookie("token", path=root_path)
            # 同时尝试删除根路径的cookie，确保完全清除
            response.delete_cookie("token", path="/")
        else:
            # 独立模式下，删除根路径的cookie
            response.delete_cookie("token", path="/")
    return response


# login request
@app.post("/api/login")
async def login(
    request: Request,
    account: str = Form(""),
    password: str = Form(""),
    temp_code: str = Form(""),
    remember: bool = Form(False),
):
    now = datetime.datetime.now(datetime.timezone.utc)
    server:PluginServerInterface = app.state.server_interface
    server_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)

    # 获取当前应用的根路径，用于处理子应用挂载
    root_path = request.scope.get("root_path", "")
    if root_path:
        # 如果是子应用挂载，需要调整重定向URL和cookie路径
        redirect_url = get_redirect_url(request, "/index")
        cookie_path = root_path
    else:
        # 独立运行模式
        redirect_url = "/index"
        cookie_path = "/"

    # check account & password
    if account and password:
        # 防呆处理：自动去除可能存在的<>字符
        account = account.replace('<', '').replace('>', '')
        password = password.replace('<', '').replace('>', '')
        # check if super admin & only_super_admin
        disable_other_admin = server_config.get("disable_other_admin", False)
        super_admin_account = str(server_config.get("super_admin_account"))
        
        if disable_other_admin and account != super_admin_account:
            return JSONResponse({"status": "error", "message": "只有超级管理才能登录。"}, status_code=403)

        if account in user_db["user"] and verify_password(
            password, user_db["user"][account]
        ):
            # token Generation
            token = secrets.token_hex(16)
            expiry = now + (
                    datetime.timedelta(days=365)
                    if remember
                    else datetime.timedelta(days=1)
                )
            max_age = datetime.timedelta(days=365) if remember else datetime.timedelta(days=1)
            max_age = max_age.total_seconds()

            # 设置session和token
            request.session["logged_in"] = True
            request.session["token"] = token
            request.session["username"] = account

            user_db["token"][token] = {"user_name": account, "expire_time": str(expiry)}
            user_db.save()

            # 创建响应并设置cookie
            response = JSONResponse({"status": "success", "message": "登录成功"})
            response.set_cookie("token", token, expires=expiry, path=cookie_path, httponly=True, max_age=max_age)

            return response

        else:
            return JSONResponse({"status": "error", "message": "账号或密码错误。"}, status_code=401)

    # temp password
    elif temp_code:
        # disallow temp_password check
        allow_temp_password = server_config.get('allow_temp_password', True)
        if not allow_temp_password:
            return JSONResponse({"status": "error", "message": "已禁止临时登录码登录。"}, status_code=403)

        if temp_code in user_db["temp"] and user_db["temp"][temp_code] > str(now):
            # token Generation
            token = secrets.token_hex(16)
            expiry = now + datetime.timedelta(hours=2)  # 临时码有效期为2小时
            max_age = datetime.timedelta(hours=2)
            max_age = max_age.total_seconds()

            # 设置session和token
            request.session["logged_in"] = True
            request.session["token"] = token
            request.session["username"] = "tempuser"

            user_db["token"][token] = {"user_name": "tempuser", "expire_time": str(expiry)}
            user_db.save()

            # 创建响应并设置cookie
            response = JSONResponse({"status": "success", "message": "临时登录成功"})
            response.set_cookie("token", token, expires=expiry, path=cookie_path, httponly=True, max_age=max_age)

            server.logger.info(f"临时用户登录成功")
            return response

        else:
            if temp_code in user_db["temp"]:  # delete expired token
                del user_db["temp"][temp_code]
                user_db.save()
            # Invalid temp password
            return JSONResponse({"status": "error", "message": "临时登录码无效。"}, status_code=401)

    else:
        # 如果未提供完整的登录信息
        return JSONResponse({"status": "error", "message": "请填写完整的登录信息。"}, status_code=400)


# logout Endpoint
@app.get("/logout", response_class=RedirectResponse)
def logout(request: Request):
    request.session["logged_in"] = False
    request.session.clear()  # clear session data
    
    # 获取当前应用的根路径，用于处理子应用挂载
    root_path = request.scope.get("root_path", "")
    if root_path:
        # 如果是子应用挂载，需要调整重定向URL和cookie路径
        redirect_url = get_redirect_url(request, "/login")
        cookie_path = root_path
    else:
        # 独立运行模式
        redirect_url = "/login"
        cookie_path = "/"
    
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    
    # 删除token cookie，确保在不同模式下都能正确删除
    if root_path:
        # fastapi_mcdr模式下，删除cookie时需要指定正确的路径
        response.delete_cookie("token", path=cookie_path)
        # 同时尝试删除根路径的cookie，确保完全清除
        response.delete_cookie("token", path="/")
    else:
        # 独立模式下，删除根路径的cookie
        response.delete_cookie("token", path=cookie_path)
    
    return response


class SessionTokenSyncMiddleware(BaseHTTPMiddleware):
    """确保 session 与 user_db 中的 token 一致：若 cookie 有 token 但 token 已不在 db（如 db 被清空），则清除 session。"""

    async def dispatch(self, request: Request, call_next):
        token = request.cookies.get("token")
        if token and token not in user_db.get("token", {}):
            request.session.clear()
        return await call_next(request)


app.add_middleware(SessionTokenSyncMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
# ============================================================#
# Pages - 使用 React SPA
@app.get("/index", response_class=HTMLResponse)
async def read_index(request: Request, token_valid: bool = Depends(verify_token)):
    if not request.session.get("logged_in"):
        return RedirectResponse(url=get_redirect_url(request, "/login"))
    return serve_spa_index(request)


@app.get("/home", response_class=HTMLResponse)
async def read_home(request: Request, token_valid: bool = Depends(verify_token)):
    if not request.session.get("logged_in"):
        return RedirectResponse(url=get_redirect_url(request, "/login"))
    return serve_spa_index(request)


@app.get("/mc", response_class=HTMLResponse)
async def mc(request: Request, token_valid: bool = Depends(verify_token)):
    if not request.session.get("logged_in"):
        return RedirectResponse(url=get_redirect_url(request, "/login"))
    return serve_spa_index(request)


@app.get("/mcdr", response_class=HTMLResponse)
async def mcdr(request: Request, token_valid: bool = Depends(verify_token)):
    if not request.session.get("logged_in"):
        return RedirectResponse(url=get_redirect_url(request, "/login"))
    return serve_spa_index(request)


@app.get("/plugins", response_class=HTMLResponse)
async def plugins(request: Request, token_valid: bool = Depends(verify_token)):
    if not request.session.get("logged_in"):
        return RedirectResponse(url=get_redirect_url(request, "/login"))
    return serve_spa_index(request)


@app.get("/online-plugins", response_class=HTMLResponse)
async def online_plugins(request: Request, token_valid: bool = Depends(verify_token)):
    if not request.session.get("logged_in"):
        return RedirectResponse(url=get_redirect_url(request, "/login"))
    return serve_spa_index(request)


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, token_valid: bool = Depends(verify_token)):
    if not request.session.get("logged_in"):
        return RedirectResponse(url=get_redirect_url(request, "/login"))
    return serve_spa_index(request)


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request, token_valid: bool = Depends(verify_token)):
    if not request.session.get("logged_in"):
        return RedirectResponse(url=get_redirect_url(request, "/login"))
    return serve_spa_index(request)

# 公开聊天页 - 使用 React SPA
@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    try:
        # 检查是否启用公开聊天页
        server:PluginServerInterface = app.state.server_interface
        server_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
        
        if not server_config.get("public_chat_enabled", False):
            return serve_spa_index(request)  # 返回 SPA，由前端处理 404
        
        return serve_spa_index(request)
    except Exception as e:
        server:PluginServerInterface = app.state.server_interface
        if server:
            server.logger.error(f"聊天页加载失败: {e}")
        return serve_spa_index(request)

# 玩家聊天页 - 独立页面，使用 React SPA
@app.get("/player-chat", response_class=HTMLResponse)
async def player_chat_page(request: Request):
    try:
        # 检查是否启用公开聊天页
        server:PluginServerInterface = app.state.server_interface
        server_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
        
        if not server_config.get("public_chat_enabled", False):
            return serve_spa_index(request)  # 返回 SPA，由前端处理 404
        
        return serve_spa_index(request)
    except Exception as e:
        server:PluginServerInterface = app.state.server_interface
        if server:
            server.logger.error(f"玩家聊天页加载失败: {e}")
        return serve_spa_index(request)

# 404 page - 返回 SPA index.html，由前端处理 404
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    # 如果是 API 请求，返回 JSON 错误
    if request.url.path.startswith("/api/"):
        return JSONResponse({"status": "error", "message": "API endpoint not found"}, status_code=404)
    # 如果是静态资源请求，返回 404（不应该被拦截，但如果被拦截了，也要返回正确的 404）
    if request.url.path.startswith("/static/"):
        return JSONResponse({"status": "error", "message": "Static file not found"}, status_code=404)
    # 否则返回 SPA index.html（用于客户端路由）
    return serve_spa_index(request)

@app.exception_handler(ConnectionResetError)
async def connection_reset_handler(request: Request, exc: ConnectionResetError):
    # 在日志中记录错误，但向客户端返回友好消息
    app.state.server_interface.logger.warning(f"连接重置错误: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "连接被重置，请刷新页面重试"}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # 记录所有未处理的异常
    error_message = f"未处理的异常: {str(exc)}"
    
    # 尝试获取服务器接口记录日志
    try:
        if hasattr(app.state, "server_interface"):
            app.state.server_interface.logger.error(f"{error_message}")
        else:
            print(f"{error_message}")
    except:
        print(f"{error_message}")
    
    # 返回友好的错误消息
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "服务器内部错误，请稍后再试"}
    )

# ============================================================#

@app.get("/api/checkLogin")
async def check_login_status(request: Request):
    # 与 db 保持一致：若 cookie 中有 token 但 token 已不在 user_db（如 db.json 被清空），则视为未登录
    token = request.cookies.get("token")
    if token and token not in user_db.get("token", {}):
        request.session.clear()
        return JSONResponse({"status": "error", "message": "User not logged in"})
    if request.session.get("logged_in"):
        username = request.session.get("username", "tempuser")
        return JSONResponse({"status": "success", "username": username})
    return JSONResponse({"status": "error", "message": "User not logged in"})


# Return plugins' metadata
@app.get("/api/plugins")
async def get_plugins(request: Request, plugin_id: str = None):
    plugins = get_plugins_info(app.state.server_interface)

    # 如果指定了 plugin_id，则只返回对应插件（如果存在）
    if plugin_id:
        plugins = [p for p in plugins if p.get("id") == plugin_id]

    if not request.session.get("logged_in"):
        # 未登录时仅返回 guguwebui 插件信息
        guguwebui_plugin = next((p for p in plugins if p.get("id") == "guguwebui"), None)
        if guguwebui_plugin:
            return JSONResponse(
                content={"plugins": [guguwebui_plugin]}
            )
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )

    return JSONResponse(
        content={"plugins": plugins}
    )

# 从 everything_slim.json 获取在线插件列表，免登录
@app.get("/api/online-plugins")
async def api_get_online_plugins(request: Request, repo_url: str = None):
    """获取在线插件列表（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    pim_helper = getattr(app.state, "pim_helper", None)
    return await get_online_plugins(request, repo_url, server, pim_helper)


# Loading/Unloading pluging
@app.post("/api/toggle_plugin")
async def api_toggle_plugin(request: Request, request_body: toggleconfig):
    """切换插件状态（加载/卸载）（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    return await toggle_plugin(request, request_body, server)


# Reload Plugin
@app.post("/api/reload_plugin")
async def api_reload_plugin(request: Request, plugin_info: plugin_info):
    """重载插件（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    return await reload_plugin(request, plugin_info, server)   

# List all config files for a plugin
@app.get("/api/list_config_files")
async def api_list_config_files(request: Request, plugin_id:str):
    """列出插件的配置文件（函数已迁移至 api/config.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    return await list_config_files(request, plugin_id)


@app.get("/api/config/icp-records")
async def api_get_icp_records(request: Request):
    """获取ICP备案信息"""
    try:
        server = app.state.server_interface
        plugin_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
        icp_records = plugin_config.get('icp_records', [])

        return JSONResponse({
            "status": "success",
            "icp_records": icp_records
        })
    except Exception as e:
        server.logger.error(f"获取ICP备案信息失败: {e}")
        return JSONResponse({
            "status": "error",
            "message": "获取ICP备案信息失败"
        }, status_code=500)


@app.get("/api/get_web_config")
async def api_get_web_config(request: Request):
    """获取Web配置（函数已迁移至 api/config.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    server = app.state.server_interface
    return await get_web_config(request, server)


@app.post("/api/save_web_config")
async def api_save_web_config(request: Request, config: saveconfig):
    """保存Web配置（函数已迁移至 api/config.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    server = app.state.server_interface
    return await save_web_config(request, config, server)


@app.get("/api/load_config")
async def api_load_config(request: Request, path:str, translation:bool = False, type:str = "auto"):
    """加载配置文件（函数已迁移至 api/config.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    server = app.state.server_interface
    return await load_config(request, path, translation, type, server)


@app.post("/api/save_config")
async def api_save_config(request: Request, config_data: config_data):
    """保存配置文件（函数已迁移至 api/config.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    server = app.state.server_interface
    return await save_config(request, config_data, server)


@app.post("/api/setup_rcon")
async def api_setup_rcon(request: Request):
    """一键启用RCON配置"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    server = app.state.server_interface
    return await setup_rcon_config(request, server)


# load overall.js / overall.css
@app.get("/api/load_file", response_class=PlainTextResponse)
async def load_file(request: Request, file: str):
    if not request.session.get("logged_in"):
        return JSONResponse({"status": "error", "message": "User not logged in"}, status_code=401)
    file_path = CSS_FILE if file == "css" else JS_FILE
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{file} file not found")


# save overall.js / overall.css
@app.post("/api/save_file")
async def save_css(request: Request, data: SaveContent):
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    file_path = CSS_FILE if data.action == "css" else JS_FILE
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(data.content)
    return {"status": "success", "message": f"{data.action} saved successfully"}


# load config file
@app.get("/api/load_config_file", response_class=PlainTextResponse)
async def load_config_file(request: Request, path: str):
    if not request.session.get("logged_in"):
        return JSONResponse({"status": "error", "message": "User not logged in"}, status_code=401)
    try:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{file} file not found")

# save config file
@app.post("/api/save_config_file")
async def save_config_file(request: Request, data: SaveContent):
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    path = data.action
    if path == "config\\guguwebui\\config.json":
        return JSONResponse({"status": "error", "message": "无法在此处修改guguwebui配置文件"})
    with open(path, "w", encoding="utf-8") as file:
        file.write(data.content)
    return {"status": "success", "message": f"{data.action} saved successfully"}

# read MC server status
@app.get("/api/get_server_status")
async def api_get_server_status(request: Request):
    """获取服务器状态（函数已迁移至 api/server.py）"""
    server = app.state.server_interface
    return await get_server_status(request, server)

# 控制Minecraft服务器
@app.post("/api/control_server")
async def api_control_server(request: Request, control_info: server_control):
    """控制Minecraft服务器（函数已迁移至 api/server.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    server = app.state.server_interface
    return await control_server(request, control_info, server)

# 获取服务器日志
@app.get("/api/server_logs")
async def api_get_server_logs(request: Request, start_line: int = 0, max_lines: int = 100):
    """获取服务器日志（函数已迁移至 api/server.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    server = app.state.server_interface
    global log_watcher
    return await get_server_logs(request, start_line, max_lines, server, log_watcher)

# 获取新增日志（基于计数器）
@app.get("/api/new_logs")
async def api_get_new_logs(request: Request, last_counter: int = 0, max_lines: int = 100):
    """获取新增日志（函数已迁移至 api/server.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    server = app.state.server_interface
    global log_watcher
    return await get_new_logs(request, last_counter, max_lines, server, log_watcher)

@app.get("/terminal")
async def terminal_page(request: Request):
    """提供终端日志页面 - 使用 React SPA
    
    Args:
        request: FastAPI请求对象
    
    Returns:
        FileResponse: SPA index.html
    """
    # 检查是否已登录
    username = request.session.get("username")
    if not username:
        return RedirectResponse(url="login?redirect=/terminal")
    
    return serve_spa_index(request)

# 获取命令补全建议
@app.get("/api/command_suggestions")
async def api_get_command_suggestions(request: Request, input: str = ""):
    """获取MCDR命令补全建议（函数已迁移至 api/server.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse({"status": "error", "message": "User not logged in"}, status_code=401)
    server = app.state.server_interface
    return await get_command_suggestions(request, input, server)

@app.post("/api/send_command")
async def api_send_command(request: Request):
    """发送命令到MCDR终端（函数已迁移至 api/server.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    server = app.state.server_interface
    return await send_command(request, server)

# 获取RCON状态
@app.get("/api/get_rcon_status")
async def api_get_rcon_status(request: Request):
    """获取RCON连接状态（函数已迁移至 api/server.py）"""
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "User not logged in"}, status_code=401
        )
    server = app.state.server_interface
    return await get_rcon_status(request, server)

@app.get("/api/plugins/web_pages")
async def get_registered_web_pages(request: Request):
    """获取所有已注册的插件网页列表"""
    if not request.session.get("logged_in"):
        return JSONResponse({"status": "error", "message": "User not logged in"}, status_code=401)
    
    pages = []
    for plugin_id, config_path in REGISTERED_PLUGIN_PAGES.items():
        pages.append({
            "id": plugin_id,
            "path": config_path
        })
    return JSONResponse({"pages": pages})

@app.post("/api/deepseek")
async def query_deepseek(request: Request, query_data: DeepseekQuery):
    """
    向AI API发送问题并获取回答
    
    Args:
        request: FastAPI请求对象
        query_data: 查询数据，包含问题内容
    
    Returns:
        JSONResponse: AI回答内容
    """
    # 检查是否已登录
    if not request.session.get("logged_in"):
        return JSONResponse(
            {"status": "error", "message": "用户未登录"}, status_code=401
        )
    
    try:
        # 加载配置
        server = app.state.server_interface
        config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
        
        # 获取API密钥 - 优先使用请求中提供的临时api_key参数(用于验证)
        api_key = getattr(query_data, "api_key", None) or config.get("ai_api_key", "")
        if not api_key:
            return JSONResponse(
                {"status": "error", "message": "未配置AI API密钥"}, 
                status_code=400
            )
        
        # 获取模型配置
        model = query_data.model or config.get("ai_model", "deepseek-chat")
        
        # 获取API URL
        api_url = query_data.api_url or config.get("ai_api_url", "https://api.deepseek.com/chat/completions")
        
        # 检查查询内容
        query = query_data.query.strip()
        if not query:
            return JSONResponse(
                {"status": "error", "message": "查询内容不能为空"}, 
                status_code=400
            )
        
        # 准备API请求
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # 构建消息
        messages = []
        
        # 添加系统指令（如果有）
        if query_data.system_prompt:
            messages.append({
                "role": "system",
                "content": query_data.system_prompt
            })
        
        # 添加用户问题
        messages.append({
            "role": "user",
            "content": query
        })
        
        # 准备请求数据
        json_data = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4000
        }
        
        # 发送请求到AI API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                headers=headers,
                json=json_data
            ) as response:
                # 解析响应（有些服务可能返回字符串或非标准结构）
                try:
                    result = await response.json(content_type=None)
                except Exception:
                    # 回退到纯文本
                    text_body = await response.text()
                    result = {"raw": text_body}
                
                # 统一判断类型，避免对 str / list 调用 .get
                is_dict = isinstance(result, dict)
                
                if response.status != 200:
                    if is_dict:
                        error_msg = (
                            result.get("error", {}).get("message")
                            or result.get("message")
                            or str(result)
                        )
                    else:
                        error_msg = str(result)
                    return JSONResponse(
                        {"status": "error", "message": f"API错误: {error_msg}"},
                        status_code=response.status
                    )
                
                # 从响应中提取AI回答
                answer = ""
                if is_dict:
                    choices = result.get("choices")
                    if isinstance(choices, list) and choices:
                        first_choice = choices[0] or {}
                        if isinstance(first_choice, dict):
                            msg_obj = first_choice.get("message") or {}
                            if isinstance(msg_obj, dict):
                                answer = msg_obj.get("content", "") or ""
                    # 如果上述解析不到内容，兜底使用整个 result 的字符串
                    if not answer:
                        answer = str(result)
                else:
                    # 如果直接返回的是字符串 / 其他类型
                    answer = str(result)
                
                return JSONResponse({
                    "status": "success",
                    "answer": answer,
                    "model": model
                })
                
    except Exception as e:
        server = app.state.server_interface
        server.logger.error(f"AI API请求失败: {str(e)}")
        return JSONResponse(
            {"status": "error", "message": f"请求失败: {str(e)}"}, 
            status_code=500
        )

# PIM插件安装和任务模型
class PluginInstallRequest:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id

class TaskStatusRequest:
    def __init__(self, task_id: str):
        self.task_id = task_id
        
# ============================================================#
# PIM API 接口
@app.post("/api/pim/install_plugin")
async def api_install_plugin(
    request: Request, 
    plugin_req: dict = Body(...),
    token_valid: bool = Depends(verify_token)
):
    """安装指定的插件（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    plugin_installer = getattr(app.state, "plugin_installer", None)
    return await install_plugin(request, plugin_req, token_valid, server, plugin_installer)

@app.post("/api/pim/update_plugin")
async def api_update_plugin(
    request: Request, 
    plugin_req: dict = Body(...),
    token_valid: bool = Depends(verify_token)
):
    """更新指定的插件（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    plugin_installer = getattr(app.state, "plugin_installer", None)
    return await update_plugin(request, plugin_req, token_valid, server, plugin_installer)

@app.post("/api/pim/uninstall_plugin")
async def api_uninstall_plugin(
    request: Request, 
    plugin_req: dict = Body(...),
    token_valid: bool = Depends(verify_token)
):
    """卸载指定的插件（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    plugin_installer = getattr(app.state, "plugin_installer", None)
    return await uninstall_plugin(request, plugin_req, token_valid, server, plugin_installer)

@app.get("/api/pim/task_status")
async def api_task_status(
    request: Request, 
    task_id: str = None,
    plugin_id: str = None,
    token_valid: bool = Depends(verify_token)
):
    """获取任务状态（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    plugin_installer = getattr(app.state, "plugin_installer", None)
    return await task_status(request, task_id, plugin_id, token_valid, server, plugin_installer)

@app.get("/api/check_pim_status")
async def api_check_pim_status(request: Request, token_valid: bool = Depends(verify_token)):
    """检查PIM插件的安装状态（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    return await check_pim_status(request, token_valid, server)

@app.get("/api/install_pim_plugin")
async def api_install_pim_plugin(request: Request, token_valid: bool = Depends(verify_token)):
    """将PIM作为独立插件安装（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    return await install_pim_plugin(request, token_valid, server)

# 添加新的API端点，使用PluginInstaller获取插件版本
@app.get("/api/pim/plugin_versions_v2")
async def api_get_plugin_versions_v2(
    request: Request, 
    plugin_id: str,
    repo_url: str = None,
    token_valid: bool = Depends(verify_token)
):
    """获取插件的所有可用版本（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    plugin_installer = getattr(app.state, "plugin_installer", None)
    return await get_plugin_versions_v2(request, plugin_id, repo_url, token_valid, server, plugin_installer)

# 添加新的API端点，用于获取插件所属的仓库信息
@app.get("/api/pim/plugin_repository")
async def api_get_plugin_repository(
    request: Request, 
    plugin_id: str,
    token_valid: bool = Depends(verify_token)
):
    """获取插件所属的仓库信息（函数已迁移至 api/plugins.py）"""
    server = app.state.server_interface
    pim_helper = getattr(app.state, "pim_helper", None)
    return await get_plugin_repository(request, plugin_id, token_valid, server, pim_helper)

# Pip包管理相关模型
class PipPackageRequest(BaseModel):
    package: str

# Pip 包管理函数已移至 utils.py

@app.get("/api/pip/list")
async def api_pip_list(request: Request, token_valid: bool = Depends(verify_token)):
    """获取已安装的pip包列表"""
    if not token_valid:
        return {"status": "error", "message": "未授权访问"}
    
    return get_installed_pip_packages()

@app.post("/api/pip/install")
async def api_pip_install(
    request: Request, 
    package_req: PipPackageRequest,
    token_valid: bool = Depends(verify_token)
):
    """安装pip包"""
    if not token_valid:
        return {"status": "error", "message": "未授权访问"}
    
    package = package_req.package.strip()
    if not package:
        return {"status": "error", "message": "包名不能为空"}
    
    # 创建任务ID并启动异步任务
    task_id = str(uuid.uuid4())
    asyncio.create_task(pip_task(task_id, "install", package))
    
    return {"status": "success", "task_id": task_id, "message": f"开始安装 {package}"}

@app.post("/api/pip/uninstall")
async def api_pip_uninstall(
    request: Request, 
    package_req: PipPackageRequest,
    token_valid: bool = Depends(verify_token)
):
    """卸载pip包"""
    if not token_valid:
        return {"status": "error", "message": "未授权访问"}
    
    package = package_req.package.strip()
    if not package:
        return {"status": "error", "message": "包名不能为空"}
    
    # 创建任务ID并启动异步任务
    task_id = str(uuid.uuid4())
    asyncio.create_task(pip_task(task_id, "uninstall", package))
    
    return {"status": "success", "task_id": task_id, "message": f"开始卸载 {package}"}

@app.get("/api/pip/task_status")
async def api_pip_task_status(
    request: Request, 
    task_id: str,
    token_valid: bool = Depends(verify_token)
):
    """获取pip任务状态"""
    if not token_valid:
        return {"status": "error", "message": "未授权访问"}
    
    if not task_id or task_id not in pip_tasks:
        return {"status": "error", "message": "无效的任务ID"}
    
    task_info = pip_tasks[task_id]
    
    return {
        "status": "success",
        "completed": task_info["completed"],
        "success": task_info["success"],
        "output": task_info["output"]
    }

# ============================================================#
# 聊天页相关API端点
# ============================================================#

@app.post("/api/chat/generate_code")
async def chat_generate_code(request: Request):
	"""生成聊天页验证码"""
	try:
		server:PluginServerInterface = app.state.server_interface
		result = generate_chat_verification_code(server)
		if isinstance(result, tuple):
			code, expire_minutes = result
			return JSONResponse({
				"status": "success",
				"code": code,
				"expire_minutes": expire_minutes
			})
		else:
			# 如果返回的是异常信息
			return JSONResponse(result, status_code=403)
	except Exception as e:
		server:PluginServerInterface = app.state.server_interface
		if server:
			server.logger.error(f"生成验证码失败: {e}")
		return JSONResponse({"status": "error", "message": "生成验证码失败"}, status_code=500)

@app.post("/api/chat/check_verification")
async def chat_check_verification(request: Request):
	"""检查验证码验证状态"""
	try:
		data = await request.json()
		code = data.get("code", "")
		result = check_chat_verification_status(code)

		status_code = 400 if result.get("status") == "error" else 200
		return JSONResponse(result, status_code=status_code)

	except Exception as e:
		server:PluginServerInterface = app.state.server_interface
		if server:
			server.logger.error(f"检查验证状态失败: {e}")
		return JSONResponse({"status": "error", "message": "检查验证状态失败"}, status_code=500)

@app.post("/api/chat/set_password")
async def chat_set_password(request: Request):
	"""设置聊天页用户密码"""
	try:
		data = await request.json()
		code = data.get("code", "")
		password = data.get("password", "")
		server:PluginServerInterface = app.state.server_interface
		result = set_chat_user_password(code, password, server)

		status_code = 400 if result.get("status") == "error" else 200
		return JSONResponse(result, status_code=status_code)

	except Exception as e:
		server:PluginServerInterface = app.state.server_interface
		if server:
			server.logger.error(f"设置密码失败: {e}")
		return JSONResponse({"status": "error", "message": "设置密码失败"}, status_code=500)

@app.post("/api/chat/login")
async def chat_login(request: Request):
    """聊天页用户登录"""
    try:
        data = await request.json()
        player_id = data.get("player_id", "")
        password = data.get("password", "")

        # 获取客户端IP
        try:
            client_ip = request.client.host if request and request.client else "unknown"
        except Exception:
            client_ip = "unknown"

        server:PluginServerInterface = app.state.server_interface
        result = chat_user_login(player_id, password, client_ip, server)

        status_code = 400 if result.get("status") == "error" else 200
        if status_code == 400 and "IP已达上限" in result.get("message", ""):
            status_code = 429

        return JSONResponse(result, status_code=status_code)

    except Exception as e:
        server:PluginServerInterface = app.state.server_interface
        if server:
            server.logger.error(f"聊天页登录失败: {e}")
        return JSONResponse({"status": "error", "message": "登录失败"}, status_code=500)

@app.post("/api/chat/check_session")
async def chat_check_session(request: Request):
    """检查聊天页会话状态"""
    try:
        data = await request.json()
        session_id = data.get("session_id", "")
        server: PluginServerInterface = app.state.server_interface
        result = check_chat_session(session_id, server)

        status_code = 400 if result.get("status") == "error" else 200
        return JSONResponse(result, status_code=status_code)

    except Exception as e:
        server:PluginServerInterface = app.state.server_interface
        if server:
            server.logger.error(f"检查会话状态失败: {e}")
        return JSONResponse({"status": "error", "message": "检查会话状态失败"}, status_code=500)

@app.post("/api/chat/logout")
async def chat_logout(request: Request):
    """聊天页用户退出登录"""
    try:
        data = await request.json()
        session_id = data.get("session_id", "")
        server:PluginServerInterface = app.state.server_interface
        result = chat_user_logout(session_id, server)

        status_code = 400 if result.get("status") == "error" else 200
        return JSONResponse(result, status_code=status_code)

    except Exception as e:
        server:PluginServerInterface = app.state.server_interface
        if server:
            server.logger.error(f"聊天页退出登录失败: {e}")
        return JSONResponse({"status": "error", "message": "退出登录失败"}, status_code=500)

@app.post("/api/chat/get_messages")
async def get_chat_messages(request: Request):
    """获取聊天消息"""
    try:
        data = await request.json()
        limit = data.get("limit", 50)
        offset = data.get("offset", 0)
        after_id = data.get("after_id")  # 新增：基于消息ID获取
        before_id = data.get("before_id")  # 新增：获取历史消息

        server:PluginServerInterface = app.state.server_interface
        result = get_chat_messages_handler(limit=limit, offset=offset, after_id=after_id, before_id=before_id, server=server)

        return JSONResponse(result)

    except Exception as e:
        server:PluginServerInterface = app.state.server_interface
        if server:
            server.logger.error(f"获取聊天消息失败: {e}")
        return JSONResponse({
            "status": "error",
            "message": f"获取聊天消息失败: {e}"
        }, status_code=500)

@app.post("/api/chat/get_new_messages")
async def get_new_chat_messages(request: Request):
    """获取新消息（基于最后消息ID）"""
    try:
        data = await request.json()
        after_id = data.get("after_id", 0)
        player_id_heartbeat = data.get("player_id")

        server:PluginServerInterface = app.state.server_interface
        result = get_new_chat_messages_handler(after_id=after_id, player_id_heartbeat=player_id_heartbeat, server=server)

        return JSONResponse(result)

    except Exception as e:
        server:PluginServerInterface = app.state.server_interface
        if server:
            server.logger.error(f"获取新聊天消息失败: {e}")
        return JSONResponse({
            "status": "error",
            "message": f"获取新聊天消息失败: {e}"
        }, status_code=500)

@app.post("/api/chat/clear_messages")
async def chat_clear_messages(request: Request):
    """清空聊天消息"""
    try:
        server:PluginServerInterface = app.state.server_interface
        result = clear_chat_messages_handler(server=server)

        return JSONResponse(result)

    except Exception as e:
        server:PluginServerInterface = app.state.server_interface
        if server:
            server.logger.error(f"清空聊天消息失败: {e}")
        return JSONResponse({"status": "error", "message": "清空聊天消息失败"}, status_code=500)

@app.post("/api/chat/send_message")
async def send_chat_message(request: Request):
    """发送聊天消息到游戏"""
    try:
        data = await request.json()
        message = data.get("message", "").strip()
        player_id = data.get("player_id", "")
        session_id = data.get("session_id", "")

        # 检查是否为WebUI已登录管理员
        is_admin = False
        if request.session.get("logged_in") and request.session.get("username") == player_id:
            is_admin = True

        server:PluginServerInterface = app.state.server_interface
        result = send_chat_message_handler(message=message, player_id=player_id, session_id=session_id, server=server, is_admin=is_admin)

        status_code = 400 if result.get("status") == "error" else 200
        if status_code == 400 and "过于频繁" in result.get("message", ""):
            status_code = 429
        elif status_code == 400 and ("过期" in result.get("message", "") or "不匹配" in result.get("message", "")):
            status_code = 401
        elif status_code == 400 and "未启用" in result.get("message", ""):
            status_code = 403

        return JSONResponse(result, status_code=status_code)

    except Exception as e:
        server:PluginServerInterface = app.state.server_interface
        if server:
            server.logger.error(f"发送聊天消息失败: {e}")
        return JSONResponse({
            "status": "error",
            "message": f"发送消息失败: {e}"
        }, status_code=500)

