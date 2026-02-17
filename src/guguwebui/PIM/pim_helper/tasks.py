import logging
import threading
import time
from typing import Any, Dict, Optional


class TaskManager:
    """任务管理器"""
    _task_counter = 0
    _all_tasks = {}
    _global_lock = threading.Lock()

    def __init__(self, server):
        self.server = server
        self.logger = logging.getLogger('PIM.Tasks')

    @classmethod
    def create_task(cls, action: str, plugin_id: str, **kwargs) -> str:
        with cls._global_lock:
            cls._task_counter += 1
            task_id = f"{action}_{cls._task_counter}"
            cls._all_tasks[task_id] = {
                'id': task_id,
                'plugin_id': plugin_id,
                'action': action,
                'status': 'running',
                'progress': 0.0,
                'message': f"Initializing {action} for {plugin_id}",
                'start_time': time.time(),
                'end_time': None,
                'access_time': time.time(),
                'all_messages': [],
                'error_messages': [],
                **kwargs
            }
            return task_id

    @classmethod
    def get_task(cls, task_id: str) -> Optional[Dict[str, Any]]:
        with cls._global_lock:
            cls._cleanup_old_tasks()
            task = cls._all_tasks.get(task_id)
            if task:
                task['access_time'] = time.time()
                return task.copy()
            return None

    @classmethod
    def update_task(cls, task_id: str, **kwargs):
        with cls._global_lock:
            if task_id in cls._all_tasks:
                task = cls._all_tasks[task_id]
                task.update(kwargs)

                # 自动处理消息记录
                if 'message' in kwargs:
                    msg = kwargs['message']
                    if msg not in task['all_messages']:
                        task['all_messages'].append(msg)

                    # 自动识别错误消息
                    if any(x in msg.lower() for x in ['error', 'failed', '失败', '错误', '⚠']):
                        if msg not in task['error_messages']:
                            task['error_messages'].append(msg)

    @classmethod
    def _cleanup_old_tasks(cls):
        current = time.time()
        # 清理 30 分钟前完成的任务
        to_remove = [tid for tid, t in cls._all_tasks.items()
                     if t['status'] in ('completed', 'failed') and current - t.get('access_time', 0) > 1800]
        for tid in to_remove:
            del cls._all_tasks[tid]

    @classmethod
    def get_all_tasks(cls) -> Dict[str, Dict[str, Any]]:
        with cls._global_lock:
            cls._cleanup_old_tasks()
            return {tid: t.copy() for tid, t in cls._all_tasks.items()}
