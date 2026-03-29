from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin
from guguwebui.services.operation_audit_service import record_operation
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
    admin: dict = Depends(get_current_admin),
):
    """安装pip包"""
    pip_service = request.app.state.pip_service
    body = {"status": "success", **pip_service.install_package(package_req.package)}
    if body.get("status") == "success":
        record_operation(
            admin,
            operation_type="pip.install",
            summary=f"发起 pip 安装: {package_req.package}",
            detail={"package": package_req.package, "task_id": body.get("task_id")},
        )
    return JSONResponse(body)


@router.post("/pip/uninstall")
async def api_pip_uninstall(
    request: Request,
    package_req: PipPackageRequest,
    admin: dict = Depends(get_current_admin),
):
    """卸载pip包"""
    pip_service = request.app.state.pip_service
    body = {"status": "success", **pip_service.uninstall_package(package_req.package)}
    if body.get("status") == "success":
        record_operation(
            admin,
            operation_type="pip.uninstall",
            summary=f"发起 pip 卸载: {package_req.package}",
            detail={"package": package_req.package, "task_id": body.get("task_id")},
        )
    return JSONResponse(body)


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

