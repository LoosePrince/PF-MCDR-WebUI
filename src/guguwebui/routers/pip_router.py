from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin
from guguwebui.structures import PipPackageRequest

router = APIRouter()


@router.get("/pip/list")
async def api_pip_list(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """获取已安装的pip包列表"""
    return JSONResponse(
        {"status": "success", "packages": request.app.state.pip_service.list_packages()}
    )


@router.post("/pip/install")
async def api_pip_install(
    request: Request,
    package_req: PipPackageRequest,
    _admin: dict = Depends(get_current_admin),
):
    """安装pip包"""
    pip_service = request.app.state.pip_service
    return JSONResponse(
        {"status": "success", **pip_service.install_package(package_req.package)}
    )


@router.post("/pip/uninstall")
async def api_pip_uninstall(
    request: Request,
    package_req: PipPackageRequest,
    _admin: dict = Depends(get_current_admin),
):
    """卸载pip包"""
    pip_service = request.app.state.pip_service
    return JSONResponse(
        {"status": "success", **pip_service.uninstall_package(package_req.package)}
    )


@router.get("/pip/task_status")
async def api_pip_task_status(
    request: Request,
    task_id: str,
    _admin: dict = Depends(get_current_admin),
):
    """获取pip任务状态"""
    return JSONResponse(
        {"status": "success", **request.app.state.pip_service.get_task_status(task_id)}
    )

