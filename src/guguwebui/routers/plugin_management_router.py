from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.structures import PluginInfo, ToggleConfig
from guguwebui import state as gugu_state

router = APIRouter()


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
    _admin: dict = Depends(get_current_admin),
):
    """切换插件状态（加载/卸载）"""
    return JSONResponse(
        request.app.state.plugin_service.toggle_plugin(
            request_body.plugin_id, request_body.status
        )
    )


@router.post("/reload_plugin")
async def api_reload_plugin(
    request: Request,
    plugin_info: PluginInfo,
    _admin: dict = Depends(get_current_admin),
):
    """重载插件"""
    return JSONResponse(
        request.app.state.plugin_service.reload_plugin(plugin_info.plugin_id)
    )


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
        }
        for pid, entry in gugu_state.REGISTERED_PLUGIN_PAGES.items()
        if _is_plugin_loaded(pid)
    ]
    return JSONResponse({"status": "success", "pages": pages})

