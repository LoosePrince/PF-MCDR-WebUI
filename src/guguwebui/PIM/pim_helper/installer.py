import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import requests

from guguwebui.utils.github_proxy import build_github_fallback_urls

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
        # Cache resolved GitHub release asset URLs to avoid repeated API calls.
        self._github_release_asset_url_cache: Dict[str, str] = {}
        # Cache expanded GitHub releases to provide full version selection UX.
        self._github_repo_releases_cache: Dict[str, List[ReleaseData]] = {}

    def _github_get_with_fallback(
        self,
        url: str,
        headers: Dict[str, str],
        timeout: int,
    ) -> Optional[requests.Response]:
        """GitHub 请求失败时自动回退到 ghfast 代理。"""
        candidate_urls = build_github_fallback_urls(url)
        for index, candidate_url in enumerate(candidate_urls):
            try:
                resp = requests.get(candidate_url, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    return resp
                if index + 1 < len(candidate_urls):
                    self.logger.warning(
                        f"GitHub 请求返回 {resp.status_code}，准备切换备用地址: {candidate_url}"
                    )
            except Exception as e:
                if index + 1 < len(candidate_urls):
                    self.logger.warning(
                        f"GitHub 请求失败，准备切换备用地址: {candidate_url}, error: {e}"
                    )
                else:
                    self.logger.warning(
                        f"GitHub 请求失败: {e}, URL: {candidate_url}"
                    )
        return None

    def _resolve_github_mcdreforged_asset_url(
        self,
        plugin_id: str,
        plugin_data: PluginData,
        target_release: ReleaseData,
        timeout: int = 10,
    ) -> Optional[str]:
        """
        兜底：当简化版 catalogue 缺失 browser_download_url 时，
        根据 repository_url + 版本在 GitHub release 中查找 .mcdr / .pyz 资源下载链接。
        """
        owner = getattr(plugin_data, "repos_owner", "") or ""
        repo = getattr(plugin_data, "repos_name", "") or ""
        if not owner or not repo:
            return None

        repo_key = f"{owner}/{repo}"

        # prefer explicit tag_name if provided
        release_version = target_release.version or ""
        candidates: List[str] = []
        if target_release.tag_name:
            candidates.append(target_release.tag_name)

        if release_version:
            # MCDR plugin catalogue tag rules (see docs)
            candidates.extend(
                [
                    release_version,  # 1.2.3
                    f"v{release_version}",  # v1.2.3
                    f"{plugin_id}-{release_version}",  # plugin_id-1.2.3
                    f"{plugin_id}-v{release_version}",  # plugin_id-v1.2.3
                ]
            )

        # de-dup while preserving order
        seen = set()
        tag_candidates = []
        for t in candidates:
            t = (t or "").strip()
            if not t or t in seen:
                continue
            seen.add(t)
            tag_candidates.append(t)

        if not tag_candidates:
            return None

        cache_prefix = f"github_release_asset_url:{repo_key}:{plugin_id}:{release_version}"

        headers = {
            "User-Agent": "MCDR-PIM-Installer/1.0",
            "Accept": "application/vnd.github+json",
        }

        for tag in tag_candidates:
            cache_key = f"{cache_prefix}:{tag}"
            if cache_key in self._github_release_asset_url_cache:
                cached = self._github_release_asset_url_cache[cache_key]
                return cached or None

            url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
            try:
                resp = self._github_get_with_fallback(url, headers, timeout)
            except Exception as e:
                self.logger.warning(f"GitHub release API request failed: {e}, URL: {url}")
                continue

            if not resp or resp.status_code != 200:
                continue

            try:
                data = resp.json()
            except Exception:
                continue

            assets = data.get("assets") or []
            if not isinstance(assets, list):
                continue

            # Filter by supported packaged file extensions.
            mc_assets = [
                a
                for a in assets
                if isinstance(a, dict)
                and isinstance(a.get("name"), str)
                and str(a["name"]).lower().endswith((".mcdr", ".pyz"))
            ]
            if not mc_assets:
                # fallback: sometimes extensions are missing but URLs still end with the packaged suffix
                mc_assets = [
                    a
                    for a in assets
                    if isinstance(a, dict)
                    and isinstance(a.get("browser_download_url"), str)
                    and str(a["browser_download_url"]).lower().endswith((".mcdr", ".pyz"))
                ]
            if not mc_assets:
                continue

            # Prefer assets that include plugin_id in their filename.
            pid_lower = plugin_id.lower()
            preferred = [
                a for a in mc_assets if pid_lower in str(a.get("name", "")).lower()
            ]
            chosen = preferred[0] if preferred else mc_assets[0]
            download_url = chosen.get("browser_download_url") if isinstance(chosen, dict) else None

            if isinstance(download_url, str) and download_url.strip():
                self._github_release_asset_url_cache[cache_key] = download_url
                return download_url

            # cache negative result for this tag to reduce repeated probing
            self._github_release_asset_url_cache[cache_key] = ""

        return None

    @staticmethod
    def _extract_version_from_tag(tag_name: str) -> str:
        """
        将 GitHub release tag 提取成类似 catalogue 里的版本号。
        支持的常见情况：
        - v1.2.3 -> 1.2.3
        - 1.2.3 -> 1.2.3
        - my_plugin-1.2.3 -> 1.2.3
        - my_plugin-v1.2.3 -> 1.2.3
        """
        t = (tag_name or "").strip()
        if not t:
            return ""
        if t.lower().startswith("v"):
            t = t[1:]
        if "-" in t:
            t = t.split("-")[-1]
            if t.lower().startswith("v"):
                t = t[1:]
        return t

    def _expand_github_releases(
        self,
        plugin_id: str,
        plugin_data: PluginData,
        timeout: int = 10,
        per_page: int = 100,
    ) -> List[ReleaseData]:
        """
        兜底：当简化仓库只提供 latest_version 时，
        从 GitHub releases 拉取更多历史版本，补足版本选择体验。
        """
        owner = getattr(plugin_data, "repos_owner", "") or ""
        repo = getattr(plugin_data, "repos_name", "") or ""
        if not owner or not repo:
            return []

        repo_key = f"{owner}/{repo}"
        if repo_key in self._github_repo_releases_cache:
            return self._github_repo_releases_cache[repo_key]

        headers = {
            "User-Agent": "MCDR-PIM-Installer/1.0",
            "Accept": "application/vnd.github+json",
        }

        # 基于需求的简化：只取前 per_page 个 releases（通常足够）
        url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page={per_page}"
        try:
            resp = self._github_get_with_fallback(url, headers, timeout)
            if not resp or resp.status_code != 200:
                self.logger.warning(f"GitHub releases API request failed, URL: {url}")
                self._github_repo_releases_cache[repo_key] = []
                return []
            data = resp.json()
        except Exception as e:
            self.logger.warning(f"GitHub releases API request failed: {e}, URL: {url}")
            self._github_repo_releases_cache[repo_key] = []
            return []

        if not isinstance(data, list):
            self._github_repo_releases_cache[repo_key] = []
            return []

        pid_lower = plugin_id.lower()
        releases: List[ReleaseData] = []
        for rel in data:
            if not isinstance(rel, dict):
                continue

            # catalogue 约定：不接受预发布版本
            if bool(rel.get("prerelease", False)):
                continue

            tag_name = str(rel.get("tag_name") or "")
            version = self._extract_version_from_tag(tag_name)
            if not version:
                continue

            assets = rel.get("assets") or []
            if not isinstance(assets, list) or not assets:
                continue

            packaged_assets: List[Dict[str, Any]] = [
                a
                for a in assets
                if isinstance(a, dict)
                and isinstance(a.get("name"), str)
                and str(a.get("name", "")).lower().endswith((".mcdr", ".pyz"))
            ]
            if not packaged_assets:
                continue

            preferred = [
                a
                for a in packaged_assets
                if pid_lower in str(a.get("name", "")).lower()
            ]
            chosen = preferred[0] if preferred else packaged_assets[0]

            download_url = chosen.get("browser_download_url", "") or ""
            if not isinstance(download_url, str) or not download_url.strip():
                continue

            created_at = str(rel.get("published_at") or rel.get("created_at") or "")
            file_name = str(chosen.get("name") or f"{plugin_id}.mcdr")

            releases.append(
                ReleaseData(
                    name=f"v{version}",
                    tag_name=f"v{version}",  # 统一为 catalogue 风格，保证 ReleaseData.version 正确
                    created_at=created_at,
                    description=str(rel.get("body") or ""),
                    prerelease=False,
                    url=str(rel.get("html_url") or ""),
                    browser_download_url=download_url,
                    download_count=0,
                    size=int(chosen.get("size") or 0),
                    file_name=file_name,
                )
            )

        # GitHub API 通常按时间倒序返回，无需额外排序；但为稳妥可按 created_at 字符串排序
        releases.sort(key=lambda r: r.created_at or "", reverse=True)
        self._github_repo_releases_cache[repo_key] = releases
        return releases

    @staticmethod
    def _find_release_from_releases(
        releases: List[ReleaseData],
        version: str,
        plugin_id: str,
    ) -> Optional[ReleaseData]:
        if not releases:
            return None
        if not version:
            return releases[0]

        v_clean = str(version).lstrip("v")
        for r in releases:
            if r.version == v_clean or r.tag_name == version:
                return r
        return None

    async def install(self, plugin_id: str, version: str = None, repo_url: str = None) -> str:
        task_id = self.task_manager.create_task('install', plugin_id, version=version, repo_url=repo_url)
        # 使用 anyio.to_thread 在后台线程运行阻塞逻辑
        import anyio
        async def run_install():
            try:
                await anyio.to_thread.run_sync(self._install_logic, task_id, plugin_id, version, repo_url)
                self.task_manager.update_task(task_id, progress=1.0, status='completed', message=f"任务完成")
            except Exception as e:
                self.logger.error(f"安装失败: {e}")
                self.task_manager.update_task(task_id, status='failed', message=f"错误: {str(e)}", end_time=time.time())
        
        from guguwebui.state import app
        if app:
            import asyncio
            asyncio.create_task(run_install())
        else:
            # 回退到线程
            thread = threading.Thread(target=self._install_thread, args=(task_id, plugin_id, version, repo_url),
                                      daemon=True)
            thread.start()
        return task_id

    async def uninstall(self, plugin_id: str) -> str:
        task_id = self.task_manager.create_task('uninstall', plugin_id)
        self.logger.debug(f"创建卸载任务: {task_id} for {plugin_id}")
        
        import anyio
        async def run_uninstall():
            try:
                await anyio.to_thread.run_sync(self._uninstall_logic, task_id, plugin_id)
                self.task_manager.update_task(task_id, progress=1.0, status='completed', message=f"任务完成")
            except Exception as e:
                self.logger.error(f"卸载失败: {e}", exc_info=True)
                self.task_manager.update_task(task_id, status='failed', message=f"卸载失败: {str(e)}", end_time=time.time())

        from guguwebui.state import app
        if app:
            import asyncio
            asyncio.create_task(run_uninstall())
        else:
            # 回退到线程
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

        # 简化版 list catalogue 通常只有 latest_version，缺少历史版本；
        # 这里做兜底：当 releases 不完整时从 GitHub 补全。
        needs_expand = (
            len(plugin_data.releases) <= 1
            or any(not r.browser_download_url for r in plugin_data.releases)
        )
        releases = plugin_data.releases
        if needs_expand and getattr(plugin_data, "repos_owner", None) and getattr(plugin_data, "repos_name", None):
            expanded = self._expand_github_releases(plugin_id, plugin_data)
            if expanded:
                releases = expanded

        versions: List[Dict[str, Any]] = []
        for release in releases:
            versions.append(
                {
                    "version": release.version,
                    "tag_name": release.tag_name,
                    # 前端映射优先使用 date 字段
                    "date": release.created_at,
                    "created_at": release.created_at,
                    "prerelease": release.prerelease,
                    "download_url": release.browser_download_url,
                    "download_count": release.download_count,
                    "size": release.size,
                    "description": release.description,
                }
            )
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
            # 简化版 catalogue 可能只有最新版本，兜底从 GitHub 查找
            expanded = self._expand_github_releases(plugin_id, plugin_data)
            target_release = self._find_release_from_releases(expanded, version or "", plugin_id)
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

        download_url = target_release.browser_download_url
        if not download_url:
            download_url = self._resolve_github_mcdreforged_asset_url(
                plugin_id=plugin_id,
                plugin_data=plugin_data,
                target_release=target_release,
            )
            target_release.browser_download_url = download_url or ""

        if not download_url:
            raise Exception(
                f"{prefix}解析插件下载 URL 失败: {plugin_id}, repo={plugin_data.repos_owner}/{plugin_data.repos_name}, "
                f"version={target_release.version}, tag={target_release.tag_name}"
            )

        self.task_manager.update_task(task_id, message=f"{prefix}正在从 {download_url} 下载...")
        if not self.downloader.download(download_url, target_path):
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
