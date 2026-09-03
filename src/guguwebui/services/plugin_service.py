import datetime
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from guguwebui.constant import (STATIC_PATH,
                                collect_repository_entries,
                                collect_repository_urls)
from guguwebui.utils.file_util import __copyFile, extract_metadata
from guguwebui.utils.mc_util import get_plugins_info, load_plugin_info
from guguwebui.utils.mcdr_adapter import MCDRAdapter


class PluginService:
    def __init__(
        self, server, pim_helper=None, plugin_installer=None, config_service=None
    ):
        self.server = server
        self.pim_helper = pim_helper
        self.plugin_installer = plugin_installer
        self.config_service = config_service

    async def package_pim_plugin(self, plugins_dir: str) -> str:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                plugin_root_dir = os.path.join(temp_dir, "pim_helper")
                pim_plugin_dir = os.path.join(plugin_root_dir, "pim_helper")
                os.makedirs(pim_plugin_dir, exist_ok=True)

                def copy_folder_from_package(
                    plugin_server, src_folder: str, dst_folder: str
                ) -> bool:
                    try:
                        dst_path = Path(dst_folder)
                        dst_path.mkdir(parents=True, exist_ok=True)
                        items = MCDRAdapter.list_plugin_directory(
                            plugin_server, src_folder
                        )

                        if not items:
                            try:
                                with plugin_server.open_bundled_file(src_folder) as _:
                                    filename = src_folder.split("/")[-1]
                                    target_file = dst_path / filename
                                    __copyFile(
                                        plugin_server, src_folder, str(target_file)
                                    )
                                    return True
                            except Exception:
                                return False

                        for name in items:
                            if name == "__pycache__":
                                continue
                            child_src = f"{src_folder}/{name}"
                            child_dst = str(Path(dst_folder) / name)
                            try:
                                # 直接复制文件；失败再尝试按目录递归，避免双重 open 导致误判
                                __copyFile(plugin_server, child_src, child_dst)
                            except Exception:
                                self.server.logger.debug(
                                    f"按文件复制失败，尝试按目录递归: {child_src} -> {child_dst}"
                                )
                                if not copy_folder_from_package(
                                    plugin_server, child_src, child_dst
                                ):
                                    self.server.logger.error(
                                        f"目录递归复制也失败: {child_src} -> {child_dst}"
                                    )
                                    return False
                        return True
                    except Exception as _e:
                        try:
                            self.server.logger.error(
                                f"复制目录失败: {src_folder} -> {dst_folder}, 错误: {_e}"
                            )
                        except Exception:
                            pass
                        return False

                pim_helper_src = "guguwebui/PIM/pim_helper"
                meta_src = "guguwebui/PIM/mcdreforged.plugin.json"
                meta_dst = os.path.join(plugin_root_dir, "mcdreforged.plugin.json")
                copied = False
                meta_copied = False

                # 优先本地文件系统路径（目录插件/源码模式最稳定）
                pkg_root = Path(__file__).resolve().parents[1]  # .../guguwebui
                local_pim_dir = pkg_root / "PIM" / "pim_helper"
                local_meta = pkg_root / "PIM" / "mcdreforged.plugin.json"
                if local_pim_dir.exists() and local_pim_dir.is_dir():
                    shutil.rmtree(pim_plugin_dir, ignore_errors=True)
                    os.makedirs(pim_plugin_dir, exist_ok=True)
                    shutil.copytree(
                        local_pim_dir,
                        Path(pim_plugin_dir),
                        dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"),
                    )
                    copied = True
                if local_meta.exists() and local_meta.is_file():
                    Path(meta_dst).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(local_meta, meta_dst)
                    meta_copied = True

                # 本地不存在时再回退到包内资源复制（压缩包插件模式兜底）
                if not copied:
                    copied = copy_folder_from_package(self.server, pim_helper_src, pim_plugin_dir)
                if copied and not meta_copied:
                    __copyFile(self.server, meta_src, meta_dst)
                    meta_copied = True

                if not copied:
                    raise FileNotFoundError(
                        f"PIM source directory not found (package or filesystem): {pim_helper_src}"
                    )
                if not meta_copied:
                    raise FileNotFoundError(
                        f"PIM metadata not found (package or filesystem): {meta_src}"
                    )

                pim_plugin_path = os.path.join(plugins_dir, "pim_helper.mcdr")
                with zipfile.ZipFile(
                    pim_plugin_path, "w", zipfile.ZIP_DEFLATED
                ) as zipf:
                    for root, dirs, files in os.walk(plugin_root_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            relative_path = os.path.relpath(file_path, plugin_root_dir)
                            zipf.write(file_path, relative_path)

                self.server.logger.info(f"PIM 插件已打包到: {pim_plugin_path}")
                return pim_plugin_path
        except Exception as e:
            self.server.logger.error(f"打包 PIM 插件时出错: {e}")
            raise

    def get_local_plugins_info(self):
        loaded_metadata, unloaded_metadata, unloaded_plugins, disabled_plugins = (
            load_plugin_info(self.server)
        )
        return loaded_metadata, unloaded_metadata, unloaded_plugins, disabled_plugins

    def get_plugins_list(self):
        """获取插件列表及其元数据（供 API 使用）"""
        return get_plugins_info(self.server)

    async def get_online_plugins(self, repo_url: str = None):
        """获取在线插件列表"""
        # 获取配置中定义的仓库URL（R1：统一复用官方 + PF + 自定义仓库列表）
        config = self.config_service.get_config() if self.config_service else {}
        configured_repos = collect_repository_urls(config)

        try:

            class FakeSource:
                def __init__(self, server):
                    self.server = server

                def reply(self, message):
                    if isinstance(message, str):
                        self.server.logger.debug(f"[仓库API] {message}")

                def get_server(self):
                    return self.server

            source = FakeSource(self.server)

            if repo_url:
                if not self.pim_helper:
                    return []

                meta_registry = self.pim_helper.get_cata_meta(
                    source, ignore_ttl=False, repo_url=repo_url
                )
                if (
                    not meta_registry
                    or not hasattr(meta_registry, "get_plugins")
                    or not meta_registry.get_plugins()
                ):
                    return []

                registry_data = {}
                try:
                    if hasattr(meta_registry, "get_registry_data"):
                        registry_data = meta_registry.get_registry_data()
                except Exception:
                    pass

                # 确保 registry_data 是字典，如果不是，则返回空列表或进行适当处理
                if not isinstance(registry_data, dict):
                    # 如果 registry_data 是列表，可能是旧版格式或特定仓库格式
                    if isinstance(registry_data, list):
                        return registry_data
                    registry_data = {}

                authors_data = {}
                try:
                    if (
                        registry_data
                        and "authors" in registry_data
                        and "authors" in registry_data["authors"]
                    ):
                        authors_data = registry_data["authors"]["authors"]
                except Exception:
                    pass

                plugins_data = []
                for plugin_id, plugin_data in meta_registry.get_plugins().items():
                    try:
                        authors = []
                        if (
                            registry_data
                            and "plugins" in registry_data
                            and plugin_id in registry_data["plugins"]
                        ):
                            plugin_info = registry_data["plugins"][plugin_id].get(
                                "plugin", {}
                            )
                            author_names = plugin_info.get("authors", [])
                            for author_name in author_names:
                                if (
                                    isinstance(author_name, str)
                                    and author_name in authors_data
                                ):
                                    author_info = authors_data.get(author_name, {})
                                    authors.append(
                                        {
                                            "name": author_info.get(
                                                "name", author_name
                                            ),
                                            "link": author_info.get("link", ""),
                                        }
                                    )
                                else:
                                    authors.append({"name": author_name, "link": ""})
                        elif hasattr(plugin_data, "author"):
                            for author_item in plugin_data.author:
                                if isinstance(author_item, str):
                                    if author_item in authors_data:
                                        author_info = authors_data.get(author_item, {})
                                        authors.append(
                                            {
                                                "name": author_info.get(
                                                    "name", author_item
                                                ),
                                                "link": author_info.get("link", ""),
                                            }
                                        )
                                    else:
                                        authors.append(
                                            {"name": author_item, "link": ""}
                                        )
                                elif isinstance(author_item, dict):
                                    authors.append(author_item)

                        latest_release = plugin_data.get_latest_release()
                        labels = []
                        if (
                            registry_data
                            and "plugins" in registry_data
                            and plugin_id in registry_data["plugins"]
                        ):
                            labels = (
                                registry_data["plugins"][plugin_id]
                                .get("plugin", {})
                                .get("labels", [])
                            )

                        license_key = "未知"
                        license_url = ""
                        readme_url = ""
                        if (
                            registry_data
                            and "plugins" in registry_data
                            and plugin_id in registry_data["plugins"]
                        ):
                            repo_info = registry_data["plugins"][plugin_id].get(
                                "repository", {}
                            )
                            if "license" in repo_info and repo_info["license"]:
                                license_info = repo_info["license"]
                                license_key = license_info.get("key", "未知")
                                license_url = license_info.get("url", "")
                            readme_url = repo_info.get("readme_url", "")

                        total_downloads = 0
                        if (
                            registry_data
                            and "plugins" in registry_data
                            and plugin_id in registry_data["plugins"]
                        ):
                            releases = (
                                registry_data["plugins"][plugin_id]
                                .get("release", {})
                                .get("releases", [])
                            )
                            for rel in releases:
                                if "asset" in rel and "download_count" in rel["asset"]:
                                    total_downloads += rel["asset"]["download_count"]

                        if (
                            total_downloads == 0
                            and latest_release
                            and hasattr(latest_release, "download_count")
                        ):
                            total_downloads = latest_release.download_count

                        plugin_entry = {
                            "id": plugin_data.id,
                            "name": plugin_data.name,
                            "version": plugin_data.version,
                            "description": plugin_data.description,
                            "authors": authors,
                            "dependencies": {
                                k: str(v) for k, v in plugin_data.dependencies.items()
                            },
                            "labels": labels,
                            "repository_url": plugin_data.link,
                            "update_time": datetime.datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            "latest_version": plugin_data.latest_version,
                            "license": license_key,
                            "license_url": license_url,
                            "downloads": total_downloads,
                            "readme_url": readme_url,
                        }

                        if latest_release and hasattr(latest_release, "created_at"):
                            try:
                                dt = datetime.datetime.fromisoformat(
                                    latest_release.created_at.replace("Z", "+00:00")
                                )
                                plugin_entry["last_update_time"] = dt.strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                            except Exception:
                                plugin_entry["last_update_time"] = (
                                    latest_release.created_at
                                )

                        plugins_data.append(plugin_entry)
                    except Exception:
                        continue
                return plugins_data
            else:
                all_plugins_data = []
                for url in configured_repos:
                    try:
                        repo_plugins = await self.get_online_plugins(url)
                        all_plugins_data.extend(repo_plugins)
                    except Exception:
                        continue
                return all_plugins_data
        except Exception as e:
            self.server.logger.error(f"获取在线插件列表失败: {e}")
            return []

    async def install_plugin(
        self, plugin_id: str, version: str = None, repo_url: str = None
    ):
        if not self.plugin_installer:
            from guguwebui.PIM import create_installer

            self.plugin_installer = create_installer(self.server)
        return await self.plugin_installer.install(plugin_id, version, repo_url)

    async def uninstall_plugin(self, plugin_id: str):
        if not self.plugin_installer:
            from guguwebui.PIM import create_installer

            self.plugin_installer = create_installer(self.server)
        return await self.plugin_installer.uninstall(plugin_id)

    def toggle_plugin(self, plugin_id: str, status: bool):
        """
        切换插件状态（B1/B2/B8）：直接调用 MCDR API 并返回真实结果。
        - 启用：disabled 插件用 enable_plugin(文件路径)，unloaded 插件用 load_plugin(文件路径)
        - 禁用：disable_plugin(插件id)，持久化（文件改为 .disabled，重启/刷新后不会自动加载）
        """
        server = self.server
        try:
            is_loaded = server.get_plugin_instance(plugin_id) is not None
        except Exception:
            is_loaded = False

        if status:
            # 目标状态：已加载
            if is_loaded:
                return {
                    "status": "success",
                    "message": f"插件 {plugin_id} 已处于加载状态",
                }
            _, unloaded_metadata, _, _ = load_plugin_info(server)
            info = unloaded_metadata.get(plugin_id)
            if not info or not info.get("path"):
                return {
                    "status": "error",
                    "message": f"未找到插件 {plugin_id} 的本地文件，无法启用",
                }
            plugin_path = info["path"]
            try:
                disabled_paths = set(server.get_disabled_plugin_list())
                if plugin_path in disabled_paths:
                    ok = server.enable_plugin(plugin_path)
                    done_text = f"插件 {plugin_id} 已启用（取消禁用）"
                else:
                    ok = server.load_plugin(plugin_path)
                    done_text = f"插件 {plugin_id} 已加载"
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"启用插件 {plugin_id} 失败: {e}",
                }
            if ok:
                return {"status": "success", "message": done_text}
            return {
                "status": "error",
                "message": f"插件 {plugin_id} 启用失败，请查看 MCDR 控制台日志",
            }
        else:
            # 目标状态：禁用（持久化，而非仅从内存卸载）
            if not is_loaded:
                return {
                    "status": "error",
                    "message": f"插件 {plugin_id} 当前未加载，无需禁用",
                }
            try:
                ok = server.disable_plugin(plugin_id)
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"禁用插件 {plugin_id} 失败: {e}",
                }
            if ok:
                return {"status": "success", "message": f"插件 {plugin_id} 已禁用"}
            return {
                "status": "error",
                "message": f"插件 {plugin_id} 禁用失败，请查看 MCDR 控制台日志",
            }

    def reload_plugin(self, plugin_id: str):
        """重载插件（B8：直接调用 MCDR API 并返回真实结果）"""
        try:
            ok = self.server.reload_plugin(plugin_id)
        except Exception as e:
            return {
                "status": "error",
                "message": f"重载插件 {plugin_id} 失败: {e}",
            }
        if ok:
            return {"status": "success", "message": f"插件 {plugin_id} 已重载"}
        return {
            "status": "error",
            "message": f"插件 {plugin_id} 重载失败（插件可能未加载）",
        }

    def get_plugin_repository(self, plugin_id: str):
        """获取插件所属的仓库信息"""
        if not self.pim_helper:
            return {"status": "error", "message": "PIM helper not initialized"}

        try:
            # 模拟命令源
            class FakeSource:
                def __init__(self, server):
                    self.server = server

                def reply(self, msg):
                    pass

                def get_server(self):
                    return self.server

            source = FakeSource(self.server)
            # 获取所有仓库条目 (url, name?)（R1：统一复用官方 + PF + 自定义仓库列表）
            config = self.config_service.get_config() if self.config_service else {}
            for entry in collect_repository_entries(config):
                repo_url = entry["url"]
                meta = self.pim_helper.get_cata_meta(
                    source, ignore_ttl=False, repo_url=repo_url
                )
                if meta and plugin_id in meta.get_plugins():
                    return {
                        "status": "success",
                        "repository": {
                            "url": repo_url,
                            "is_official": entry["is_official"],
                            "name_key": (
                                "official"
                                if entry["is_official"]
                                else ("loose_repo" if entry["is_loose"] else "custom")
                            ),
                            "name": entry["name"],
                        },
                    }

            return {"status": "error", "message": "Plugin not found in any repository"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_plugin_versions(self, plugin_id: str, repo_url: str = None):
        """获取插件版本列表"""
        if not self.plugin_installer:
            from guguwebui.PIM import create_installer

            self.plugin_installer = create_installer(self.server)
        return self.plugin_installer.get_plugin_versions(plugin_id, repo_url)

    def get_task_status(self, task_id: str = None, plugin_id: str = None):
        if not self.plugin_installer:
            return None
        if task_id:
            return self.plugin_installer.get_task_status(task_id)
        elif plugin_id:
            all_tasks = self.plugin_installer.get_all_tasks()
            return {
                tid: t
                for tid, t in all_tasks.items()
                if t.get("plugin_id") == plugin_id
            }
        return self.plugin_installer.get_all_tasks()

    def get_languages(self):
        """获取支持的语言列表"""
        try:
            lang_dir = Path(STATIC_PATH) / "lang"
            if not lang_dir.exists():
                return []

            # 常见语言的默认显示名映射
            default_names = {
                "zh-CN": "中文",
                "zh-TW": "繁體中文",
                "en-US": "English",
                "ja-JP": "日本語",
                "ko-KR": "한국어",
                "ru-RU": "Русский",
                "fr-FR": "Français",
                "de-DE": "Deutsch",
                "es-ES": "Español",
                "pt-BR": "Português (Brasil)",
                "vi-VN": "Tiếng Việt",
                "tr-TR": "Türkçe",
                "ar-SA": "العربية",
                "it-IT": "Italiano",
                "pl-PL": "Polski",
                "uk-UA": "Українська",
                "id-ID": "Bahasa Indonesia",
                "th-TH": "ไทย",
                "hi-IN": "हिन्दी",
            }

            langs = []
            for file in sorted(lang_dir.glob("*.json")):
                code = file.stem
                name = default_names.get(code, code)
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        meta = data.get("meta") or {}
                        if isinstance(meta, dict) and meta.get("name"):
                            name = meta.get("name").strip()
                except Exception:
                    pass
                langs.append({"code": code, "name": name})
            return langs
        except Exception as e:
            self.server.logger.error(f"获取语言列表失败: {e}")
            return []

    def check_pim_status(self):
        """检查 PIM 插件的安装状态"""
        loaded_metadata, unloaded_metadata, _, _ = self.get_local_plugins_info()
        installed = "pim_helper" in loaded_metadata or "pim_helper" in unloaded_metadata
        return {
            "status": "success",
            "pim_status": "installed" if installed else "not_installed",
            "message": "PIM插件已安装" if installed else "PIM插件未安装",
        }

    async def install_pim_plugin_action(self):
        """将PIM作为独立插件安装"""
        loaded_metadata, unloaded_metadata, _, _ = self.get_local_plugins_info()
        if "pim_helper" in loaded_metadata or "pim_helper" in unloaded_metadata:
            return {"status": "success", "message": "PIM插件已安装"}

        data_folder = self.server.get_data_folder()
        mcdr_root = os.path.dirname(os.path.dirname(data_folder))
        plugins_dir = os.path.join(mcdr_root, "plugins")
        os.makedirs(plugins_dir, exist_ok=True)

        pim_plugin_path = await self.package_pim_plugin(plugins_dir)
        self.server.load_plugin(pim_plugin_path)
        return {"status": "success", "message": "PIM插件已成功安装并加载"}

    def self_update(self):
        """执行 WebUI 自身更新"""
        command = "!!MCDR plugin install -U -y guguwebui"
        self.server.logger.info(f"执行自更新命令: {command}")
        self.server.execute_command(command)
        return {
            "success": True,
            "message": "已发送更新指令到 MCDR，插件将自动重启并完成更新",
        }
