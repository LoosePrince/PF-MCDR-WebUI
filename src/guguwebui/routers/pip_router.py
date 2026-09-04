from fastapi import APIRouter, Depends, Request

from guguwebui.dependencies.auth import get_current_admin
from guguwebui.services.operation_audit_service import record_operation
from guguwebui.structures import BusinessException, PipTaskCreateRequest
from guguwebui.structures.envelope import ApiSuccessEnvelope, success

router = APIRouter()


@router.get("/pip/packages", response_model=ApiSuccessEnvelope)
async def api_pip_list(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """获取已安装的pip包列表（原 GET /pip/list，已迁移为资源路径 + 统一外壳）"""
    packages = request.app.state.pip_service.list_packages()
    return success({"packages": packages})


@router.post("/pip/tasks", response_model=ApiSuccessEnvelope)
async def api_pip_start_task(
    request: Request,
    body: PipTaskCreateRequest,
    admin: dict = Depends(get_current_admin),
):
    """发起 pip 安装/卸载后台任务（原 POST /pip/install、/pip/uninstall，合并为任务创建）"""
    action = (body.action or "").strip().lower()
    package = (body.package or "").strip()
    if action not in ("install", "uninstall"):
        raise BusinessException(
            f"Unsupported pip action: {body.action}",
            status_code=400,
            code="invalid_action",
        )
    if not package:
        raise BusinessException(
            "Package name is required", status_code=400, code="invalid_package"
        )
    task_id = await request.app.state.pip_service.start_task(action, package)
    record_operation(
        admin,
        operation_type=f"pip.{action}",
        summary=f"发起 pip {action}: {package}",
        detail={"action": action, "package": package, "task_id": task_id},
    )
    return success({"task_id": task_id})


@router.get("/pip/tasks/{task_id}", response_model=ApiSuccessEnvelope)
async def api_pip_task_status(
    request: Request,
    task_id: str,
    _admin: dict = Depends(get_current_admin),
):
    """获取 pip 任务状态（原 GET /pip/task_status?task_id=，已迁移为子资源路径）

    任务体不再把内部 status（success/error）展开覆盖外壳键；
    状态统一为 running|completed|failed，与 PIM 任务结构一致。
    """
    task = request.app.state.pip_service.get_task(task_id)
    if task is None:
        raise BusinessException(
            f"Task not found: {task_id}", status_code=404, code="task_not_found"
        )
    return success({"task_info": task})
