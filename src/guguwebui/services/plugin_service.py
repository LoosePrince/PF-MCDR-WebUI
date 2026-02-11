import os
import tempfile
import zipfile
from pathlib import Path

from guguwebui.utils.file_util import extract_metadata
from guguwebui.utils.mcdr_adapter import MCDRAdapter


class PluginService:
    def __init__(self, server, pim_helper=None, plugin_installer=None):
        self.server = server
        self.pim_helper = pim_helper
        self.plugin_installer = plugin_installer

    async def package_pim_plugin(self, plugins_dir: str) -> str:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                plugin_root_dir = os.path.join(temp_dir, "pim_helper")
                pim_plugin_dir = os.path.join(plugin_root_dir, "pim_helper")
                os.makedirs(pim_plugin_dir, exist_ok=True)

                def copy_folder_from_package(plugin_server, src_folder: str, dst_folder: str) -> bool:
                    try:
                        dst_path = Path(dst_folder)
                        dst_path.mkdir(parents=True, exist_ok=True)
                        items = MCDRAdapter.list_plugin_directory(plugin_server, src_folder)

                        if not items:
                            try:
                                with plugin_server.open_bundled_file(src_folder) as _:
                                    filename = src_folder.split("/")[-1]
                                    target_file = dst_path / filename
                                    __copyFile(plugin_server, src_folder, str(target_file))
                                    return True
                            except Exception:
                                return False

                        for name in items:
                            if name == "__pycache__": continue
                            child_src = f"{src_folder}/{name}"
                            child_dst = str(Path(dst_folder) / name)
                            try:
                                with plugin_server.open_bundled_file(child_src) as _:
                                    __copyFile(plugin_server, child_src, child_dst)
                            except Exception:
                                if not copy_folder_from_package(plugin_server, child_src, child_dst): return False
                        return True
                    except Exception as _e:
                        try:
                            self.server.logger.error(f"复制目录失败: {src_folder} -> {dst_folder}, 错误: {_e}")
                        except Exception:
                            pass
                        return False

                pim_helper_src = "guguwebui/utils/PIM/pim_helper"
                if not copy_folder_from_package(self.server, pim_helper_src, pim_plugin_dir):
                    raise FileNotFoundError(f"PIM source directory not found inside package: {pim_helper_src}")

                meta_src = "guguwebui/utils/PIM/mcdreforged.plugin.json"
                meta_dst = os.path.join(plugin_root_dir, "mcdreforged.plugin.json")
                __copyFile(self.server, meta_src, meta_dst)

                pim_plugin_path = os.path.join(plugins_dir, "pim_helper.mcdr")
                with zipfile.ZipFile(pim_plugin_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
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
        loaded_metadata = self.server.get_all_metadata()
        disabled_plugins = self.server.get_disabled_plugin_list()
        unloaded_plugins = self.server.get_unloaded_plugin_list()

        unloaded_metadata = {}
        for plugin_path in disabled_plugins + unloaded_plugins:
            if not (plugin_path.endswith('.py') or plugin_path.endswith('.mcdr')): continue
            metadata = extract_metadata(plugin_path)
            if not metadata: continue
            if metadata['id'] in unloaded_metadata and metadata['version'] <= unloaded_metadata[metadata["id"]][
                'version']: continue
            metadata['path'] = plugin_path
            unloaded_metadata[metadata["id"]] = metadata

        return loaded_metadata, unloaded_metadata, unloaded_plugins, disabled_plugins
