import asyncio
import subprocess
import sys
import uuid
from typing import Dict

from guguwebui.state import pip_tasks
from guguwebui.structures import BusinessException


class PipService:
    def __init__(self, server):
        self.server = server

    def list_packages(self):
        """获取已安装的 pip 包列表"""
        try:
            # 使用 sys.executable 确保使用当前 Python 环境
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)
        except Exception as e:
            self.server.logger.error(f"获取 pip 列表失败: {e}")
            raise BusinessException(f"获取 pip 列表失败: {str(e)}")

    async def _run_pip_command(self, action: str, package: str, task_id: str):
        """后台运行 pip 命令"""
        pip_tasks[task_id] = {
            "status": "running",
            "message": f"正在{action} {package}...",
        }

        try:
            cmd = (
                [sys.executable, "-m", "pip", action, package, "-y"]
                if action == "uninstall"
                else [sys.executable, "-m", "pip", action, package]
            )

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                pip_tasks[task_id] = {
                    "status": "success",
                    "message": f"{package} {action}成功",
                }
            else:
                error_msg = stderr.decode().strip() or stdout.decode().strip()
                pip_tasks[task_id] = {
                    "status": "error",
                    "message": f"{action}失败: {error_msg}",
                }

        except Exception as e:
            pip_tasks[task_id] = {"status": "error", "message": f"执行异常: {str(e)}"}

    def install_package(self, package: str):
        """异步安装 pip 包"""
        task_id = str(uuid.uuid4())
        asyncio.create_task(self._run_pip_command("install", package, task_id))
        return {"status": "success", "task_id": task_id}

    def uninstall_package(self, package: str):
        """异步卸载 pip 包"""
        task_id = str(uuid.uuid4())
        asyncio.create_task(self._run_pip_command("uninstall", package, task_id))
        return {"status": "success", "task_id": task_id}

    def get_task_status(self, task_id: str):
        """获取任务状态"""
        if task_id not in pip_tasks:
            raise BusinessException("任务不存在", status_code=404)
        return pip_tasks[task_id]


import json
