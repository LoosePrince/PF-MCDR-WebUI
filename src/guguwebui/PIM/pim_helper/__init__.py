import logging
import os
import threading
import time
from typing import Any, Dict, Optional

from mcdreforged.api.command import Literal, Text
from mcdreforged.api.types import PluginServerInterface

from guguwebui.constant import MCDR_OFFICIAL_CATALOGUE_URL

from .installer import PluginInstaller
from .models import PluginData, PluginRequirement, ReleaseData
from .registry import EmptyMetaRegistry, MetaRegistry, PluginCatalogueAccess, RegistryManager
from .tasks import TaskManager

# 全局实例，供独立插件模式使用
_helper_instance: Optional['PIMHelper'] = None


class PIMHelper:
    """PIM 助手 - 模块协调者"""

    def __init__(self, server: PluginServerInterface):
        self.server = server
        self.logger = logging.getLogger('PIM.Helper')

        # 初始化子模块
        cache_dir = self.get_temp_dir()
        self.registry_manager = RegistryManager(server, cache_dir)
        self.installer = PluginInstaller(server, self)

        self.logger.debug("PIM助手初始化完成")

    def get_temp_dir(self) -> str:
        """获取缓存目录 (config/guguwebui/cache)"""
        return os.path.join(self.server.get_data_folder(), "cache")

    def get_plugin_dir(self) -> str:
        """获取插件安装目录"""
        mcdr_config = self.server.get_mcdr_config()
        plugin_dirs = mcdr_config.get('plugin_directories', [])
        if plugin_dirs:
            return plugin_dirs[0]
        return os.path.join(os.getcwd(), 'plugins')

    def get_cata_meta(self, source=None, ignore_ttl: bool = False, repo_url: str = None) -> MetaRegistry:
        """获取元数据"""
        if source:
            source.reply("正在获取插件目录元数据...")

        url = repo_url if repo_url else MCDR_OFFICIAL_CATALOGUE_URL

        return self.registry_manager.get_meta(url, ignore_ttl)

    def list_plugins(self, source, keyword: Optional[str] = None) -> int:
        """列出插件"""
        meta = self.get_cata_meta()
        from .registry import PluginCatalogueAccess
        # 包装 source 为 replier 兼容接口
        class Replier:
            def __init__(self, s): self.s = s

            def reply(self, t): self.s.reply(t)

        return PluginCatalogueAccess.list_plugin(meta, Replier(source), keyword)

    def get_local_plugins(self) -> Dict[str, Any]:
        """获取本地插件状态"""
        result = {'loaded': {}, 'unloaded': [], 'disabled': []}

        # 已加载
        for pid in self.server.get_plugin_list():
            instance = self.server.get_plugin_instance(pid)
            if instance:
                path = getattr(instance, 'file_path', None)
                if path: result['loaded'][pid] = str(path)

        # 扫描目录
        plugin_dir = self.get_plugin_dir()
        if os.path.isdir(plugin_dir):
            for file_name in os.listdir(plugin_dir):
                if file_name.endswith(('.mcdr', '.py')):
                    path = os.path.join(plugin_dir, file_name)
                    if path not in result['loaded'].values():
                        result['unloaded'].append(path)

        return result

    @staticmethod
    def detect_unloaded_plugin_id(plugin_path: str) -> Optional[str]:
        """检测未加载插件的 ID"""
        # 保持原有逻辑，此处简化演示，实际应迁移原 PIM.py 中的实现
        try:
            import zipfile
            import json
            if plugin_path.endswith('.py'):
                return os.path.basename(plugin_path)[:-3]
            if zipfile.is_zipfile(plugin_path):
                with zipfile.ZipFile(plugin_path, 'r') as z:
                    meta_file = next(
                        (f for f in z.namelist() if f.endswith(('mcdr_plugin.json', 'mcdreforged.plugin.json'))), None)
                    if meta_file:
                        meta = json.loads(z.read(meta_file).decode('utf-8'))
                        return meta.get('id')
        except:
            pass
        return None

    # 代理 Installer 的方法
    def install(self, plugin_id: str, version: str = None, repo_url: str = None) -> str:
        return self.installer.install(plugin_id, version, repo_url)

    def uninstall(self, plugin_id: str) -> str:
        return self.installer.uninstall(plugin_id)

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.installer.task_manager.get_task(task_id)

    def get_all_tasks(self) -> Dict[str, Any]:
        return self.installer.task_manager.get_all_tasks()


# --- MCDR 插件入口点 (支持独立运行) ---

def on_load(server: PluginServerInterface, _old):
    global _helper_instance
    _helper_instance = PIMHelper(server)
    register_commands(server)
    server.logger.info("PIM Helper 独立插件模式已就绪")


def register_commands(server: PluginServerInterface):
    """注册 !!pim 指令树"""

    def get_helper():
        return _helper_instance

    def list_plugins(src, ctx):
        keyword = ctx.get('keyword')
        get_helper().list_plugins(src, keyword)

    def install_plugin(src, ctx):
        plugin_id = ctx['plugin_id']
        version = ctx.get('version')
        task_id = get_helper().install(plugin_id, version)
        src.reply(f"已启动安装任务: {task_id} (插件: {plugin_id})")
        # 启动一个简易的监控线程，将进度反馈给指令源
        _start_task_monitor(src, task_id)

    def uninstall_plugin(src, ctx):
        plugin_id = ctx['plugin_id']
        task_id = get_helper().uninstall(plugin_id)
        src.reply(f"已启动卸载任务: {task_id} (插件: {plugin_id})")
        _start_task_monitor(src, task_id)

    def _start_task_monitor(src, task_id):
        def monitor():
            last_msg_idx = 0
            while True:
                task = get_helper().get_task_status(task_id)
                if not task: break

                msgs = task.get('all_messages', [])
                if len(msgs) > last_msg_idx:
                    for i in range(last_msg_idx, len(msgs)):
                        src.reply(f"[{task_id}] {msgs[i]}")
                    last_msg_idx = len(msgs)

                if task['status'] in ('completed', 'failed'):
                    break
                time.sleep(0.5)

        threading.Thread(target=monitor, daemon=True).start()

    # 注册指令树
    server.register_command(
        Literal('!!pim')
        .requires(lambda src: src.has_permission(4))
        .then(
            Literal('list')
            .runs(list_plugins)
            .then(Text('keyword').runs(list_plugins))
        )
        .then(
            Literal('install')
            .then(
                Text('plugin_id')
                .runs(install_plugin)
                .then(Text('version').runs(install_plugin))
            )
        )
        .then(
            Literal('uninstall')
            .then(Text('plugin_id').runs(uninstall_plugin))
        )
        .then(
            Literal('update')
            .then(Text('plugin_id').runs(install_plugin))
        )
    )

    server.register_help_message('!!pim', 'PIM 插件管理工具')
