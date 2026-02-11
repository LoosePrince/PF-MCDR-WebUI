import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from .downloader import ReleaseDownloader
from .models import PluginData, ReleaseData
from .resolver import PluginDependencyResolver
from .tasks import TaskManager


class PluginInstaller:
    """插件安装器核心逻辑"""
    PENDING_DELETE_FILES = {}  # {plugin_id: [file_paths]}

    def __init__(self, server, pim_helper):
        self.server = server
        self.pim_helper = pim_helper
        self.logger = logging.getLogger('PIM.Installer')
        self.resolver = PluginDependencyResolver(server, pim_helper)
        self.task_manager = TaskManager(server)
        self.downloader = ReleaseDownloader(server, pim_helper)

    def install(self, plugin_id: str, version: str = None, repo_url: str = None) -> str:
        task_id = self.task_manager.create_task('install', plugin_id, version=version, repo_url=repo_url)
        thread = threading.Thread(target=self._install_thread, args=(task_id, plugin_id, version, repo_url),
                                  daemon=True)
        thread.start()
        return task_id

    def uninstall(self, plugin_id: str) -> str:
        task_id = self.task_manager.create_task('uninstall', plugin_id)
        self.logger.debug(f"创建卸载任务: {task_id} for {plugin_id}")
        thread = threading.Thread(target=self._uninstall_thread, args=(task_id, plugin_id), daemon=True)
        thread.start()
        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取单个任务状态"""
        return self.task_manager.get_task(task_id)

    def get_all_tasks(self) -> Dict[str, Any]:
        """获取所有任务状态"""
        return self.task_manager.get_all_tasks()

    def get_plugin_versions(self, plugin_id: str, repo_url: str = None) -> List[Dict[str, Any]]:
        """获取插件版本列表"""
        meta = self.pim_helper.get_cata_meta(None, repo_url=repo_url)
        plugin_data = meta.get_plugin_data(plugin_id)
        if not plugin_data:
            return []

        versions = []
        for release in plugin_data.releases:
            versions.append({
                'version': release.version,
                'tag_name': release.tag_name,
                'created_at': release.created_at,
                'download_url': release.browser_download_url,
                'download_count': release.download_count,
                'size': release.size,
                'description': release.description
            })
        return versions

    def _install_thread(self, task_id: str, plugin_id: str, version: str, repo_url: str):
        try:
            self._install_logic(task_id, plugin_id, version, repo_url)
            self.task_manager.update_task(task_id, progress=1.0, status='completed', message=f"任务完成")
        except Exception as e:
            self.logger.error(f"安装失败: {e}")
            self.task_manager.update_task(task_id, status='failed', message=f"错误: {str(e)}", end_time=time.time())

    def _install_logic(self, task_id: str, plugin_id: str, version: str, repo_url: str, is_dependency: bool = False):
        """核心安装逻辑，支持递归调用"""
        prefix = "[依赖] " if is_dependency else ""
        self.task_manager.update_task(task_id, message=f"{prefix}正在处理插件: {plugin_id}")

        meta = self.pim_helper.get_cata_meta(None, repo_url=repo_url)
        plugin_data = meta.get_plugin_data(plugin_id)

        if not plugin_data:
            raise Exception(f"未找到插件: {plugin_id}")

        # 确定安装版本
        target_release = self._find_release(plugin_data, version)
        if not target_release:
            raise Exception(f"未找到指定版本: {version or 'latest'}")

        self.task_manager.update_task(task_id, message=f"{prefix}确定安装版本: {target_release.version}")

        # 检查已安装版本
        installed_meta = self.server.get_plugin_metadata(plugin_id)

        # 记录受影响的依赖插件，以便后续重新启用
        affected_plugins = []

        if installed_meta:
            current_ver = str(installed_meta.version)
            if current_ver == target_release.version:
                self.task_manager.update_task(task_id, message=f"{prefix}插件 {plugin_id} 已是最新版本 ({current_ver})")
                return
            self.task_manager.update_task(task_id,
                                          message=f"{prefix}检测到旧版本: {current_ver} -> 目标版本: {target_release.version}")

            # 查找依赖于此插件的其他插件
            for pid in self.server.get_plugin_list():
                p_meta = self.server.get_plugin_metadata(pid)
                if p_meta and plugin_id in p_meta.dependencies:
                    affected_plugins.append(pid)

            if affected_plugins:
                self.task_manager.update_task(task_id,
                                              message=f"{prefix}发现受影响的依赖插件: {', '.join(affected_plugins)}，正在停止...")
                for pid in affected_plugins:
                    if self.server.unload_plugin(pid):
                        self.task_manager.update_task(task_id, message=f"{prefix}已停止依赖插件: {pid}")

        # 卸载旧版本
        if installed_meta:
            self.task_manager.update_task(task_id, message=f"{prefix}正在卸载旧版本 {plugin_id}...")
            if self.server.unload_plugin(plugin_id):
                self.task_manager.update_task(task_id, message=f"{prefix}旧版本插件已卸载")
            self.mark_for_deletion(plugin_id)

        # 下载
        plugin_dir = self.pim_helper.get_plugin_dir()
        file_name = target_release.file_name or f"{plugin_id}.mcdr"
        target_path = os.path.join(plugin_dir, file_name)

        self.task_manager.update_task(task_id, message=f"{prefix}正在从 {target_release.browser_download_url} 下载...")
        if not self.downloader.download(target_release.browser_download_url, target_path):
            raise Exception(f"下载插件 {plugin_id} 失败")
        self.task_manager.update_task(task_id, message=f"{prefix}下载完成: {file_name}")

        # 检查依赖
        self.task_manager.update_task(task_id, message=f"{prefix}正在解析 {plugin_id} 的依赖关系...")
        dep_results = self.resolver.resolve(plugin_id, meta, target_path)

        # 处理环境问题
        if dep_results['environment_issues']:
            for issue in dep_results['environment_issues']:
                self.task_manager.update_task(task_id, message=f"⚠ 环境警告: {issue}")

        # 递归安装缺失插件
        missing = dep_results['missing_plugins']
        if missing:
            # 再次过滤，确保不会尝试安装核心环境
            missing = [m for m in missing if m.lower() not in ('mcdreforged', 'python')]
            if missing:
                self.task_manager.update_task(task_id, message=f"{prefix}发现缺失前置插件: {', '.join(missing)}")
                for dep_id in missing:
                    self._install_logic(task_id, dep_id, None, None, is_dependency=True)

        # 更新的插件提示
        outdated = dep_results['outdated_plugins']
        if outdated:
            self.task_manager.update_task(task_id, message=f"{prefix}提示: 以下依赖版本较低，建议更新: {outdated}")

        # 安装 Python 依赖
        self._install_python_requirements(task_id, target_path, prefix)

        # 加载
        self.task_manager.update_task(task_id, message=f"{prefix}正在加载插件文件: {file_name}")
        if self.server.load_plugin(target_path):
            self._cleanup_pending_files(plugin_id)
            self.task_manager.update_task(task_id, message=f"✓ {prefix}插件 {plugin_id} 加载成功")

            # 重新加载受影响的依赖插件
            if affected_plugins:
                self.task_manager.update_task(task_id, message=f"{prefix}正在重新启用受影响的依赖插件...")
                for pid in affected_plugins:
                    # 获取插件路径以重新加载
                    p_meta = self.server.get_plugin_metadata(pid)
                    if p_meta:
                        # 尝试通过 ID 加载，如果失败则尝试通过路径
                        if self.server.load_plugin(pid):
                            self.task_manager.update_task(task_id, message=f"{prefix}已重新启用依赖插件: {pid}")
                        else:
                            self.task_manager.update_task(task_id,
                                                          message=f"⚠ {prefix}未能自动重新启用依赖插件: {pid}，请手动加载")
        else:
            if not is_dependency:
                raise Exception(f"主插件 {plugin_id} 加载失败，请检查控制台日志")
            else:
                self.task_manager.update_task(task_id,
                                              message=f"⚠ {prefix}插件 {plugin_id} 加载失败，可能会影响主插件运行")

    def _install_python_requirements(self, task_id: str, plugin_path: str, prefix: str = ""):
        """安装插件包内的 Python 依赖"""
        if not zipfile.is_zipfile(plugin_path):
            return

        try:
            with zipfile.ZipFile(plugin_path, 'r') as z:
                req_file = next((f for f in z.namelist() if f.endswith('requirements.txt')), None)
                if req_file:
                    self.task_manager.update_task(task_id,
                                                  message=f"{prefix}发现 requirements.txt，准备安装 Python 依赖...")
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='wb', suffix='req.txt', delete=False) as tmp:
                        tmp.write(z.read(req_file))
                        tmp_path = tmp.name

                    try:
                        process = subprocess.run(
                            [sys.executable, "-m", "pip", "install", "-r", tmp_path],
                            capture_output=True, text=True, check=False
                        )
                        if process.returncode == 0:
                            self.task_manager.update_task(task_id, message=f"{prefix}Python 依赖安装成功")
                        else:
                            self.task_manager.update_task(task_id,
                                                          message=f"⚠ {prefix}Python 依赖安装可能存在问题: {process.stderr[:200]}...")
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
        except Exception as e:
            self.task_manager.update_task(task_id, message=f"⚠ {prefix}读取 requirements.txt 失败: {e}")

    def _uninstall_thread(self, task_id: str, plugin_id: str):
        self.logger.debug(f"卸载线程启动: {task_id} for {plugin_id}")
        try:
            self._uninstall_logic(task_id, plugin_id)
            self.task_manager.update_task(task_id, progress=1.0, status='completed', message=f"任务完成")
        except Exception as e:
            self.logger.error(f"卸载失败: {e}", exc_info=True)
            self.task_manager.update_task(task_id, status='failed', message=f"卸载失败: {str(e)}", end_time=time.time())

    def _uninstall_logic(self, task_id: str, plugin_id: str, is_dependency: bool = False):
        """核心卸载逻辑，支持递归卸载依赖于此插件的其他插件"""
        prefix = "[联动卸载] " if is_dependency else ""

        # 1. 查找依赖于此插件的其他插件（联动卸载）
        # 必须在卸载当前插件之前完成，并且要先删除文件，防止 MCDR 自动重载
        all_plugins = self.server.get_plugin_list()
        for pid in all_plugins:
            p_meta = self.server.get_plugin_metadata(pid)
            if p_meta:
                deps = getattr(p_meta, 'dependencies', {})
                is_dep = False
                if isinstance(deps, dict):
                    is_dep = any(str(d).lower() == plugin_id.lower() for d in deps.keys())
                elif isinstance(deps, list):
                    is_dep = any(str(d).lower() == plugin_id.lower() for d in deps)

                if is_dep:
                    self.task_manager.update_task(task_id,
                                                  message=f"{prefix}发现依赖于 {plugin_id} 的插件: {pid}，正在卸载...")
                    # 递归处理依赖插件
                    self._uninstall_logic(task_id, pid, is_dependency=True)

        # 2. 处理当前插件
        self.task_manager.update_task(task_id, message=f"{prefix}正在处理卸载: {plugin_id}")

        # 3. 标记并【立即】清理文件
        # 在调用 unload 之前清理文件，可以防止 MCDR 在 unload 后的自动扫描中重新发现并尝试加载该插件
        self.mark_for_deletion(plugin_id)
        self._cleanup_pending_files(plugin_id)
        self.task_manager.update_task(task_id, message=f"{prefix}已清理本地文件")

        # 4. 尝试从 MCDR 卸载
        if self.server.get_plugin_instance(plugin_id):
            self.server.unload_plugin(plugin_id)
            self.task_manager.update_task(task_id, message=f"✓ {prefix}插件 {plugin_id} 已从内存卸载")

        self.task_manager.update_task(task_id, message=f"✓ {prefix}插件 {plugin_id} 卸载完成")

    @staticmethod
    def _find_release(plugin_data: PluginData, version: str) -> Optional[ReleaseData]:
        if not version:
            return plugin_data.get_latest_release()

        v_clean = version.lstrip('v')
        for r in plugin_data.releases:
            if r.version == v_clean or r.tag_name == version:
                return r
        return None

    def mark_for_deletion(self, plugin_id: str) -> Tuple[bool, List[str]]:
        """标记插件文件待删除"""
        pending = []
        plugin = self.server.get_plugin_instance(plugin_id)
        if plugin:
            path = getattr(plugin, 'file_path', None)
            if path: pending.append(str(path))

        local_plugins = self.pim_helper.get_local_plugins()
        for path in local_plugins.get('unloaded', []):
            if self.pim_helper.detect_unloaded_plugin_id(path) == plugin_id:
                pending.append(path)

        if pending:
            self.PENDING_DELETE_FILES[plugin_id] = list(set(pending))
            return True, pending
        return False, []

    def _cleanup_pending_files(self, plugin_id: str):
        """执行实际的文件删除"""
        if plugin_id in self.PENDING_DELETE_FILES:
            for path in self.PENDING_DELETE_FILES[plugin_id]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        self.force_delete_file(path)
            del self.PENDING_DELETE_FILES[plugin_id]

    @staticmethod
    def force_delete_file(file_path: str) -> bool:
        """强制删除文件 (Windows 特化)"""
        try:
            if os.name == 'nt':
                subprocess.run(['del', '/f', '/q', file_path], shell=True, check=False)
                if not os.path.exists(file_path): return True
                kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel32.MoveFileExW(file_path, None, 0x4)
            else:
                os.remove(file_path)
            return not os.path.exists(file_path)
        except:
            return False
