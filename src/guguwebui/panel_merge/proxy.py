from __future__ import annotations

from typing import Any, Dict, List, Tuple

import aiohttp
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.services.config_service import ConfigService


def get_target_server_id(request: Request) -> str:
    # header 优先，其次 query
    sid = (request.headers.get("X-Target-Server") or "").strip()
    if not sid:
        sid = (request.query_params.get("serverId") or "").strip()
    return sid or "local"


def is_proxy_candidate_path(path: str) -> bool:
    # 只代理 /api/*，并排除主服本地必须处理的少量端点
    if not path.startswith("/api/"):
        return False
    # 登录/登出/校验登录：必须由主服本地处理（cookie 建立在主服域）
    if path in [
        "/api/login",
        "/api/logout",
        "/api/checkLogin",
        "/api/servers",
        "/api/panel_merge_config",
    ]:
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


def is_admin_api_path(path: str) -> bool:
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


def _filter_query_items(items: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    # 移除 serverId，避免子服再处理
    return [(k, v) for (k, v) in items if k != "serverId"]


def _filter_outbound_request_headers(request: Request) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for k, v in request.headers.items():
        lk = k.lower()
        if lk in {"host", "content-length", "cookie"}:
            continue
        headers[k] = v
    return headers


def _filter_inbound_response_headers(headers: aiohttp.typedefs.LooseHeaders) -> Dict[str, str]:
    out_headers: Dict[str, str] = {}
    for k, v in dict(headers).items():
        lk = str(k).lower()
        if lk in {"set-cookie", "content-length", "transfer-encoding", "connection"}:
            continue
        out_headers[str(k)] = str(v)
    return out_headers


async def proxy_request_to_slave(request: Request, slave: dict, sub_path: str) -> Response:
    """
    将主服请求代理到子服的 /api/{sub_path}
    - 注入 X-Panel-Token
    - 不透传 Cookie / Set-Cookie
    """
    base_url = str(slave.get("base_url", "")).rstrip("/")
    target_url = f"{base_url}/api/{sub_path.lstrip('/')}"

    query = _filter_query_items(list(request.query_params.multi_items()))
    body = await request.body()

    headers = _filter_outbound_request_headers(request)
    headers["X-Panel-Token"] = str(slave.get("token", "")).strip()
    headers["X-Forwarded-For"] = request.client.host if request.client else ""

    verify_tls = bool(slave.get("verify_tls", True))
    session: aiohttp.ClientSession = request.app.state.http_session
    async with session.request(
        method=request.method,
        url=target_url,
        params=query,
        data=body if body else None,
        headers=headers,
        ssl=verify_tls,
    ) as resp:
        resp_body = await resp.read()
        out_headers = _filter_inbound_response_headers(resp.headers)
        return Response(content=resp_body, status_code=resp.status, headers=out_headers)


class ApiProxyDispatchMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            server_id = get_target_server_id(request)
            if server_id == "local":
                return await call_next(request)

            # 仅主服模式启用代理
            config_service: ConfigService | None = getattr(
                request.app.state, "config_service", None
            )
            if config_service is None:
                return await call_next(request)
            server_config = config_service.get_config()
            if server_config.get("panel_role", "master") != "master":
                return await call_next(request)

            if not is_proxy_candidate_path(request.url.path):
                return await call_next(request)

            # 主服本地先做权限判定（权限在主服判定）
            if is_admin_api_path(request.url.path):
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
            return await proxy_request_to_slave(request, slave, sub_path)
        except HTTPException:
            raise
        except Exception as e:
            request.app.state.server_interface.logger.error(
                f"代理请求失败: {e}", exc_info=True
            )
            return JSONResponse(
                {"status": "error", "message": "Proxy request failed"},
                status_code=502,
            )

