import asyncio
import inspect
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile
from starlette.responses import Response

import guguwebui.state as gugu_state
from guguwebui.constant import PLUGIN_API_MAX_UPLOAD_BYTES
from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.services.config_service import ConfigService
from guguwebui.state import PluginApiHandlerParams

router = APIRouter()

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
    {"type": "file", "filename", "content_type", "size", "data": bytes}。
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


@router.api_route(
    "/plugin/{plugin_id}",
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


@router.api_route(
    "/plugin/{plugin_id}/{subpath:path}",
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

