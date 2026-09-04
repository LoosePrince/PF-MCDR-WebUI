import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from guguwebui.state import pip_tasks
from guguwebui.structures import BusinessException

# 任务体结构对齐 PIM TaskManager：
# {id, package, action, status: running|completed|failed, progress, message,
#  start_time, end_time, access_time, all_messages, error_messages}
# 状态不再使用 success/error（与响应外壳键冲突，且前端无法据此终止轮询）。

_TASK_TTL_SECONDS = 30 * 60  # 与 PIM 一致：完成/失败后 30 分钟无访问即回收


def _pip_base_command() -> List[str]:
    """返回可用的 pip 基础命令。

    优先使用当前解释器（`sys.executable -m pip`，跟随本插件所在环境）；
    若解释器文件不存在/不可用（被移动或删除，Windows 下表现为
    FileNotFoundError: [WinError 2]），回退到 PATH 中的 `pip`。
    """
    if sys.executable and os.path.isfile(sys.executable):
        return [sys.executable, "-m", "pip"]
    fallback = shutil.which("pip")
    if fallback:
        return [fallback]
    return [sys.executable, "-m", "pip"]


class PipService:
    def __init__(self, server):
        self.server = server

    # ------------------------------------------------------------------
    # 包列表
    # ------------------------------------------------------------------

    def list_packages(self):
        """获取已安装的 pip 包列表"""
        try:
            # 使用 sys.executable 确保使用当前 Python 环境
            result = subprocess.run(
                [*_pip_base_command(), "list", "--format=json"],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)
        except Exception as e:
            self.server.logger.error(f"获取 pip 列表失败: {e}")
            raise BusinessException(
                f"获取 pip 列表失败: {str(e)}", status_code=500, code="pip_list_failed"
            )

    # ------------------------------------------------------------------
    # 任务管理（统一任务体）
    # ------------------------------------------------------------------

    def _update_task(self, task_id: str, **kwargs):
        task = pip_tasks.get(task_id)
        if not task:
            return
        task.update(kwargs)
        # 自动记录消息历史
        msg = kwargs.get("message")
        if msg and msg not in task.get("all_messages", []):
            task.setdefault("all_messages", []).append(msg)
            lowered = msg.lower()
            if any(x in lowered for x in ("error", "failed", "失败", "错误", "⚠")):
                task.setdefault("error_messages", []).append(msg)

    def create_task(self, action: str, package: str) -> str:
        """创建 pip 安装/卸载任务记录，立即返回 task_id"""
        task_id = str(uuid.uuid4())
        now = time.time()
        pip_tasks[task_id] = {
            "id": task_id,
            "package": package,
            "action": action,
            "status": "running",
            "progress": 0.0,
            "message": f"正在{action} {package}...",
            "start_time": now,
            "end_time": None,
            "access_time": now,
            "all_messages": [f"正在{action} {package}..."],
            "error_messages": [],
        }
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态（带访问时间刷新与过期回收）"""
        self._cleanup_old_tasks()
        task = pip_tasks.get(task_id)
        if task:
            task["access_time"] = time.time()
            return task.copy()
        return None

    def _cleanup_old_tasks(self):
        now = time.time()
        stale = [
            tid
            for tid, t in pip_tasks.items()
            if t.get("status") in ("completed", "failed")
            and now - t.get("access_time", 0) > _TASK_TTL_SECONDS
        ]
        for tid in stale:
            pip_tasks.pop(tid, None)

    # ------------------------------------------------------------------
    # 后台执行
    # ------------------------------------------------------------------

    async def _run_pip_command(self, task_id: str, action: str, package: str):
        """后台运行 pip 命令并把 stdout/stderr 逐行写入任务消息"""
        try:
            cmd = (
                [*_pip_base_command(), action, package, "-y"]
                if action == "uninstall"
                else [*_pip_base_command(), action, package]
            )

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            out_text = stdout.decode(errors="replace").strip()
            err_text = stderr.decode(errors="replace").strip()

            if process.returncode == 0:
                for line in out_text.splitlines():
                    self._update_task(task_id, message=f"{line}")
                self._update_task(
                    task_id,
                    status="completed",
                    progress=1.0,
                    end_time=time.time(),
                    message=f"{package} {action}成功",
                )
            else:
                error_msg = err_text or out_text or f"{action}失败"
                for line in (err_text or out_text).splitlines():
                    self._update_task(task_id, message=f"{line}")
                self._update_task(
                    task_id,
                    status="failed",
                    end_time=time.time(),
                    message=f"{action}失败: {error_msg}",
                )
        except Exception as e:
            self._update_task(
                task_id,
                status="failed",
                end_time=time.time(),
                message=f"执行异常: {str(e)}",
            )

    async def start_task(self, action: str, package: str) -> str:
        """创建任务并调度后台执行（install/uninstall 统一入口）"""
        task_id = self.create_task(action, package)
        asyncio.create_task(self._run_pip_command(task_id, action, package))
        return task_id

    def get_task_status(self, task_id: str):
        """旧接口兼容：找不到抛 404（返回体结构与 get_task 一致）"""
        task = self.get_task(task_id)
        if task is None:
            raise BusinessException("任务不存在", status_code=404, code="task_not_found")
        return task
