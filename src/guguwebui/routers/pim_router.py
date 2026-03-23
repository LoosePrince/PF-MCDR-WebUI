from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.structures import PimInstallRequest, PimUninstallRequest

router = APIRouter()


@router.get("/pim/plugin_repository")
async def api_get_plugin_repository(
    request: Request, plugin_id: str, _user: dict = Depends(get_current_user)
):
    """获取插件所属的仓库信息"""
    result = request.app.state.plugin_service.get_plugin_repository(plugin_id)
    return JSONResponse(result)


@router.get("/pim/plugin_versions")
async def api_get_plugin_versions(
    request: Request,
    plugin_id: str,
    repo_url: str | None = None,
    _user: dict = Depends(get_current_user),
):
    """获取插件版本列表"""
    versions = request.app.state.plugin_service.get_plugin_versions(plugin_id, repo_url)
    return JSONResponse({"success": True, "versions": versions or []})


@router.post("/pim/install_plugin")
async def api_pim_install_plugin(
    request: Request,
    body: PimInstallRequest,
    _admin: dict = Depends(get_current_admin),
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


@router.post("/pim/uninstall_plugin")
async def api_pim_uninstall_plugin(
    request: Request,
    body: PimUninstallRequest,
    _admin: dict = Depends(get_current_admin),
):
    """卸载插件（PIM）"""
    if body.plugin_id == "guguwebui":
        return JSONResponse(
            {"success": False, "error": "不允许卸载 WebUI 自身"}, status_code=400
        )

    try:
        task_id = await request.app.state.plugin_service.uninstall_plugin(body.plugin_id)
        return JSONResponse({"success": True, "task_id": task_id})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/pim/update_plugin")
async def api_pim_update_plugin(
    request: Request,
    body: PimInstallRequest,
    _admin: dict = Depends(get_current_admin),
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


@router.get("/pim/task_status")
async def api_pim_task_status(
    request: Request,
    task_id: str | None = None,
    plugin_id: str | None = None,
    _user: dict = Depends(get_current_user),
):
    """获取 PIM 任务状态"""
    info = request.app.state.plugin_service.get_task_status(
        task_id=task_id, plugin_id=plugin_id
    )
    if task_id and info is None:
        return JSONResponse({"success": False, "task_info": None})
    return JSONResponse({"success": True, "task_info": info})


@router.get("/check_pim_status")
async def api_check_pim_status(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """检查PIM插件的安装状态"""
    return JSONResponse(
        {"status": "success", **request.app.state.plugin_service.check_pim_status()}
    )


@router.get("/install_pim_plugin")
async def api_install_pim_plugin(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """将PIM作为独立插件安装"""
    return JSONResponse(
        {
            "status": "success",
            **await request.app.state.plugin_service.install_pim_plugin_action(),
        }
    )

