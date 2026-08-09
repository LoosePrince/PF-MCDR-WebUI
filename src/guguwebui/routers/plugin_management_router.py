import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.services.operation_audit_service import record_operation
from guguwebui.structures import PluginInfo, ToggleConfig
from guguwebui import state as gugu_state

router = APIRouter()


def _resolve_plugin_icon_path(entry: object) -> tuple[Path, str] | None:
    """Resolve an image icon without allowing access outside the plugin page directory."""
    icon = getattr(entry, "icon", None)
    html_path = getattr(entry, "html_path", None)
    if not isinstance(icon, str) or not icon.strip() or not isinstance(html_path, str):
        return None

    relative_icon_path = Path(icon)
    if relative_icon_path.is_absolute():
        return None

    page_directory = Path(html_path).resolve().parent
    icon_path = (page_directory / relative_icon_path).resolve()
    try:
        icon_path.relative_to(page_directory)
    except ValueError:
        return None

    media_type, _ = mimetypes.guess_type(icon_path.name)
    if not icon_path.is_file() or not media_type or not media_type.startswith("image/"):
        return None
    return icon_path, media_type


@router.get("/langs")
def get_languages(request: Request):
    """返回 /lang 目录下的 json 文件及其显示名称"""
    return JSONResponse(request.app.state.plugin_service.get_languages(), status_code=200)


@router.get("/plugins")
async def get_plugins(
    request: Request,
    plugin_id: str | None = None,
    _user: dict = Depends(get_current_user),
):
    """Return plugins' metadata"""
    plugins = request.app.state.plugin_service.get_plugins_list()
    if plugin_id:
        plugins = [p for p in plugins if p.get("id") == plugin_id]
    return JSONResponse(content={"status": "success", "plugins": plugins})


@router.get("/online-plugins")
async def api_get_online_plugins(
    request: Request,
    repo_url: str | None = None,
    _admin: dict = Depends(get_current_admin),
):
    """获取在线插件列表"""
    plugins_list = await request.app.state.plugin_service.get_online_plugins(repo_url)
    return JSONResponse(plugins_list)


@router.post("/toggle_plugin")
async def api_toggle_plugin(
    request: Request,
    request_body: ToggleConfig,
    admin: dict = Depends(get_current_admin),
):
    """切换插件状态（加载/卸载）"""
    result = request.app.state.plugin_service.toggle_plugin(
        request_body.plugin_id, request_body.status
    )
    if isinstance(result, dict) and result.get("status") == "success":
        verb = "启用" if request_body.status else "禁用"
        record_operation(
            admin,
            operation_type="plugin.toggle",
            summary=f"{verb}插件: {request_body.plugin_id}",
            detail={"plugin_id": request_body.plugin_id, "load": request_body.status},
        )
    return JSONResponse(result)


@router.post("/reload_plugin")
async def api_reload_plugin(
    request: Request,
    plugin_info: PluginInfo,
    admin: dict = Depends(get_current_admin),
):
    """重载插件"""
    result = request.app.state.plugin_service.reload_plugin(plugin_info.plugin_id)
    if isinstance(result, dict) and result.get("status") == "success":
        record_operation(
            admin,
            operation_type="plugin.reload",
            summary=f"重载插件: {plugin_info.plugin_id}",
            detail={"plugin_id": plugin_info.plugin_id},
        )
    return JSONResponse(result)


@router.get("/list_config_files")
async def api_list_config_files(
    request: Request,
    plugin_id: str,
    _user: dict = Depends(get_current_user),
):
    """列出插件的配置文件"""
    files_list = request.app.state.config_service.list_config_files(plugin_id)
    return JSONResponse({"status": "success", "files": files_list})


@router.get("/plugins/web_pages")
async def get_registered_web_pages(
    request: Request,
    _user: dict = Depends(get_current_user),
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
            "icon": getattr(entry, "icon", None),
        }
        for pid, entry in gugu_state.REGISTERED_PLUGIN_PAGES.items()
        if _is_plugin_loaded(pid)
    ]
    return JSONResponse({"status": "success", "pages": pages})


@router.get("/plugins/web_pages/{plugin_id}/icon")
async def get_registered_web_page_icon(
    request: Request,
    plugin_id: str,
    _user: dict = Depends(get_current_user),
):
    """Return a registered plugin page's relative image icon."""
    entry = gugu_state.REGISTERED_PLUGIN_PAGES.get(plugin_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Plugin page not found")

    server_interface = getattr(request.app.state, "server_interface", None)
    if server_interface is not None:
        try:
            if server_interface.get_plugin_instance(plugin_id) is None:
                raise HTTPException(status_code=404, detail="Plugin page not found")
        except HTTPException:
            raise
        except Exception:
            pass

    resolved_icon = _resolve_plugin_icon_path(entry)
    if resolved_icon is None:
        raise HTTPException(status_code=404, detail="Plugin icon not found")
    icon_path, media_type = resolved_icon
    return FileResponse(icon_path, media_type=media_type)

