from fastapi import APIRouter, Depends, Request

from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.services.operation_audit_service import record_operation
from guguwebui.structures import BusinessException
from guguwebui.structures.envelope import ApiSuccessEnvelope, success

router = APIRouter()


@router.get("/pim/tasks/{task_id}", response_model=ApiSuccessEnvelope)
async def api_pim_task_status(
    request: Request,
    task_id: str,
    _user: dict = Depends(get_current_user),
):
    """获取 PIM 任务状态（原 GET /pim/task_status?task_id=）"""
    info = request.app.state.plugin_service.get_task_status(task_id=task_id)
    if info is None:
        raise BusinessException(
            f"Task not found: {task_id}", status_code=404, code="task_not_found"
        )
    return success({"task_info": info})


@router.get("/pim/status", response_model=ApiSuccessEnvelope)
async def api_check_pim_status(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """检查PIM插件的安装状态（原 /check_pim_status）"""
    result = request.app.state.plugin_service.check_pim_status()
    return success(
        {
            "pim_status": result.get("pim_status", "not_installed"),
            "message": result.get("message", ""),
        }
    )


@router.post("/pim/bootstrap", response_model=ApiSuccessEnvelope)
async def api_install_pim_plugin(
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """将PIM作为独立插件安装（原 GET /install_pim_plugin，改为 POST 副作用语义）"""
    result = await request.app.state.plugin_service.install_pim_plugin_action()
    if isinstance(result, dict) and result.get("status") == "success":
        record_operation(
            admin,
            operation_type="pim.install_pim_bootstrap",
            summary="安装/启用内置 PIM 模块",
            detail={k: v for k, v in result.items() if k in ("message", "task_id")},
        )
        return success(
            message=result.get("message") or "PIM插件已成功安装并加载",
            data={"task_id": result.get("task_id")} if result.get("task_id") else None,
        )
    raise BusinessException(
        (result.get("message") if isinstance(result, dict) else None)
        or "PIM 插件安装失败",
        status_code=500,
        code="pim_bootstrap_failed",
    )
