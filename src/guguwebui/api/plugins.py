"""
插件管理相关的API函数
迁移自 web_server.py 中的 /api/pim/ 端点
"""

import datetime
import logging
import os
import tempfile
import zipfile

from fastapi import Body, Depends, status
from fastapi import Request
from fastapi.responses import JSONResponse

from guguwebui.PIM import create_installer
from guguwebui.structures import PluginInfo, ToggleConfig
from guguwebui.constant import DEFALUT_CONFIG
from guguwebui.utils.file_util import __copyFile
from guguwebui.utils.mc_util import load_plugin_info
from guguwebui.utils.server_util import verify_token


async def package_pim_plugin(server, plugins_dir: str) -> str:
    """
    将 PIM 文件夹打包为独立的 MCDR 插件

    Args:
        server: MCDR 服务器接口
        plugins_dir: MCDR 插件目录路径

    Returns:
        str: 打包后的插件文件路径
    """
    try:
        # 创建临时目录用于打包
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建插件根目录结构
            plugin_root_dir = os.path.join(temp_dir, "pim_helper")  # 插件根目录
            pim_plugin_dir = os.path.join(plugin_root_dir, "pim_helper")  # 插件ID同名文件夹

            # 创建目录结构
            os.makedirs(pim_plugin_dir, exist_ok=True)

            # 从插件包内部提取 PIM 源文件（与前端静态资源导出一致的方式），
            # 但为确保源码完整打包，这里不忽略 .py 文件，仅忽略 __pycache__。

            def copy_folder_from_package(plugin_server, src_folder: str, dst_folder: str) -> bool:
                """
                递归从插件包内复制目录到文件系统，仅忽略 __pycache__。
                与 utils.__copyFolder 类似，但不忽略 .py 与 "utils" 目录。
                """
                try:
                    from pathlib import Path as _Path
                    dst_path = _Path(dst_folder)
                    dst_path.mkdir(parents=True, exist_ok=True)

                    # 列出目录项
                    items = []
                    try:
                        items = plugin_server._PluginServerInterface__plugin.list_directory(src_folder)
                    except Exception:
                        try:
                            from mcdreforged.plugin.type.multi_file_plugin import MultiFilePlugin
                            if isinstance(plugin_server._PluginServerInterface__plugin, MultiFilePlugin):
                                items = plugin_server._PluginServerInterface__plugin.list_directory(src_folder)
                        except Exception:
                            items = []

                    if not items:
                        # 尝试作为单文件复制
                        try:
                            with plugin_server.open_bundled_file(src_folder) as _:
                                # 目标若为目录，补上文件名
                                filename = src_folder.split("/")[-1]
                                target_file = dst_path / filename
                                # 使用已有的文件复制函数
                                __copyFile(plugin_server, src_folder, str(target_file))
                                return True
                        except Exception:
                            return False

                    for name in items:
                        if name == "__pycache__":
                            continue
                        child_src = f"{src_folder}/{name}"
                        child_dst = str(_Path(dst_folder) / name)
                        # 判断文件或目录
                        try:
                            with plugin_server.open_bundled_file(child_src) as _:
                                __copyFile(plugin_server, child_src, child_dst)
                        except Exception:
                            if not copy_folder_from_package(plugin_server, child_src, child_dst):
                                return False

                    return True
                except Exception as _e:
                    try:
                        server.logger.error(f"复制目录失败: {src_folder} -> {dst_folder}, 错误: {_e}")
                    except Exception:
                        pass
                    return False

            # 1) 复制 pim_helper 目录到 pim_plugin_dir
            pim_helper_src = "guguwebui/utils/PIM/pim_helper"
            if not copy_folder_from_package(server, pim_helper_src, pim_plugin_dir):
                server.logger.error(f"无法从插件包内提取目录: {pim_helper_src}")
                raise FileNotFoundError(f"PIM source directory not found inside package: {pim_helper_src}")

            # 2) 复制 mcdreforged.plugin.json 到插件根目录
            meta_src = "guguwebui/utils/PIM/mcdreforged.plugin.json"
            meta_dst = os.path.join(plugin_root_dir, "mcdreforged.plugin.json")
            try:
                __copyFile(server, meta_src, meta_dst)
            except Exception as e:
                server.logger.error(f"无法从插件包内提取元数据文件: {meta_src}, 错误: {e}")
                raise FileNotFoundError(f"Metadata file not found inside package: {meta_src}")

            # 创建 .mcdr 文件（实际上是 zip 文件）
            pim_plugin_path = os.path.join(plugins_dir, "pim_helper.mcdr")

            with zipfile.ZipFile(pim_plugin_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 遍历插件根目录中的所有文件
                for root, dirs, files in os.walk(plugin_root_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # 计算相对路径（相对于插件根目录）
                        relative_path = os.path.relpath(file_path, plugin_root_dir)
                        zipf.write(file_path, relative_path)

            server.logger.info(f"PIM 插件已打包到: {pim_plugin_path}")
            return pim_plugin_path

    except Exception as e:
        server.logger.error(f"打包 PIM 插件时出错: {e}")
        raise


async def install_plugin(
    request: Request,
    plugin_req: dict = Body(...),
    token_valid: bool = Depends(verify_token),
    server=None,
    plugin_installer=None
):
    """
    安装指定的插件

    可接受的参数:
    - plugin_id: 必需，插件ID
    - version: 可选，指定版本号
    - repo_url: 可选，指定仓库URL
    """
    if not token_valid:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "error": "未登录或会话已过期"}
        )

    plugin_id = plugin_req.get("plugin_id")
    version = plugin_req.get("version")
    repo_url = plugin_req.get("repo_url")

    if not plugin_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "缺少插件ID"}
        )

    try:
        # 使用传入的server和plugin_installer参数
        if not server:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"success": False, "error": "服务器接口未提供"}
            )

        # 首先尝试使用已初始化的实例
        installer = plugin_installer
        if not installer:
            # 如果没有预初始化的实例，创建新的安装器实例
            server.logger.info("使用临时创建的安装器实例")
            installer = create_installer(server)

        # 启动异步安装
        task_id = installer.install(plugin_id, version, repo_url)

        # 构建响应消息
        message = f"开始安装插件 {plugin_id}"
        if version:
            message += f" v{version}"
        if repo_url:
            message += f" 从仓库 {repo_url}"

        return JSONResponse(
            content={
                "success": True,
                "task_id": task_id,
                "message": message
            }
        )
    except Exception as e:
        if server:
            server.logger.error(f"安装插件失败: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": f"安装插件失败: {str(e)}"}
        )


async def update_plugin(
    request: Request,
    plugin_req: dict = Body(...),
    token_valid: bool = Depends(verify_token),
    server=None,
    plugin_installer=None
):
    """
    更新指定的插件到指定版本

    可接受的参数:
    - plugin_id: 必需，插件ID
    - version: 可选，指定版本号
    - repo_url: 可选，指定仓库URL
    """
    if not token_valid:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "error": "未登录或会话已过期"}
        )

    plugin_id = plugin_req.get("plugin_id")
    version = plugin_req.get("version")
    repo_url = plugin_req.get("repo_url")

    if not plugin_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "缺少插件ID"}
        )

    try:
        # 使用传入的server和plugin_installer参数
        if not server:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"success": False, "error": "服务器接口未提供"}
            )

        # 首先尝试使用已初始化的实例
        installer = plugin_installer
        if not installer:
            # 如果没有预初始化的实例，创建新的安装器实例
            server.logger.info("使用临时创建的安装器实例")
            installer = create_installer(server)

        # 启动异步安装/更新
        task_id = installer.install(plugin_id, version, repo_url)

        # 构建响应消息
        message = f"开始更新插件 {plugin_id}"
        if version:
            message += f" 到 v{version}"
        else:
            message += " 到最新版本"
        if repo_url:
            message += f" 从仓库 {repo_url}"

        return JSONResponse(
            content={
                "success": True,
                "task_id": task_id,
                "message": message
            }
        )
    except Exception as e:
        if server:
            server.logger.error(f"更新插件失败: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": f"更新插件失败: {str(e)}"}
        )


async def uninstall_plugin(
    request: Request,
    plugin_req: dict = Body(...),
    token_valid: bool = Depends(verify_token),
    server=None,
    plugin_installer=None
):
    """
    卸载指定的插件，支持卸载并删除未加载的插件
    """
    if not token_valid:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "error": "未登录或会话已过期"}
        )

    plugin_id = plugin_req.get("plugin_id")

    if not plugin_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "缺少插件ID"}
        )

    try:
        # 使用传入的server和plugin_installer参数
        if not server:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"success": False, "error": "服务器接口未提供"}
            )

        # 首先尝试使用已初始化的实例
        installer = plugin_installer
        if not installer:
            # 如果没有预初始化的实例，创建新的安装器实例
            server.logger.info("使用临时创建的安装器实例")
            installer = create_installer(server)

        # 启动异步卸载，同时处理已加载和未加载的插件
        task_id = installer.uninstall(plugin_id)

        return JSONResponse(
            content={
                "success": True,
                "task_id": task_id,
                "message": f"开始卸载插件 {plugin_id}"
            }
        )
    except Exception as e:
        if server:
            server.logger.error(f"卸载插件失败: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": f"卸载插件失败: {str(e)}"}
        )


async def task_status(
    request: Request,
    task_id: str = None,
    plugin_id: str = None,
    token_valid: bool = Depends(verify_token),
    server=None,
    plugin_installer=None
):
    """
    获取任务状态

    可以通过任务ID或插件ID获取
    """
    if not token_valid:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "error": "未登录或会话已过期"}
        )

    try:
        # 使用传入的server和plugin_installer参数
        if not server:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"success": False, "error": "服务器接口未提供"}
            )

        # 首先尝试使用已初始化的实例
        installer = plugin_installer
        if not installer:
            # 如果没有预初始化的实例，创建新的安装器实例
            server.logger.info("使用临时创建的安装器实例")
            installer = create_installer(server)

        # 如果指定了任务ID，返回单个任务状态
        if task_id:
            task_status = installer.get_task_status(task_id)
            # 如果找不到任务
            if not task_status:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"success": False, "error": f"找不到任务 {task_id}"}
                )
            return JSONResponse(content={"success": True, "task_info": task_status})

        # 如果指定了插件ID，返回涉及该插件的所有任务
        elif plugin_id:
            all_tasks = installer.get_all_tasks()
            plugin_tasks = {}

            for tid, task in all_tasks.items():
                if task.get('plugin_id') == plugin_id:
                    plugin_tasks[tid] = task

            return JSONResponse(content={"success": True, "tasks": plugin_tasks})

        # 如果两者都未指定，返回所有任务
        else:
            all_tasks = installer.get_all_tasks()
            return JSONResponse(content={"success": True, "tasks": all_tasks})

    except Exception as e:
        if server:
            server.logger.error(f"获取任务状态失败: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": f"获取任务状态失败: {str(e)}"}
        )


async def get_plugin_versions_v2(
    request: Request,
    plugin_id: str,
    repo_url: str = None,
    token_valid: bool = Depends(verify_token),
    server=None,
    plugin_installer=None
):
    """
    获取插件的所有可用版本（新版API）
    """
    if not token_valid:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "error": "未登录或会话已过期"}
        )

    if not plugin_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "缺少插件ID"}
        )

    try:
        # 使用传入的server和plugin_installer参数
        if not server:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"success": False, "error": "服务器接口未提供"}
            )

        # 记录请求日志
        server.logger.debug(f"请求获取插件版本: {plugin_id}, 仓库: {repo_url}")

        # 首先尝试使用已初始化的 PluginInstaller 实例
        installer = plugin_installer
        if installer:
            server.logger.debug(f"使用已初始化的插件安装器获取版本信息")
            versions = installer.get_plugin_versions(plugin_id, repo_url)
        else:
            # 如果没有预初始化的实例，创建临时安装器
            server.logger.info(f"使用临时创建的安装器获取版本信息")
            installer = create_installer(server)
            versions = installer.get_plugin_versions(plugin_id, repo_url)

        # 记录结果
        if versions:
            server.logger.debug(f"成功获取插件 {plugin_id} 的 {len(versions)} 个版本")
        else:
            server.logger.debug(f"获取插件 {plugin_id} 版本列表为空")

        # 返回版本列表
        return JSONResponse(
            content={
                "success": True,
                "versions": versions
            }
        )
    except Exception as e:
        if server:
            server.logger.error(f"获取插件版本失败: {e}")
            import traceback
            server.logger.debug(traceback.format_exc())
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": f"获取插件版本失败: {str(e)}"}
        )


async def get_plugin_repository(
    request: Request,
    plugin_id: str,
    token_valid: bool = Depends(verify_token),
    server=None,
    pim_helper=None
):
    """
    获取插件所属的仓库信息
    """
    if not token_valid:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "error": "未登录或会话已过期"}
        )

    if not plugin_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "缺少插件ID"}
        )

    try:
        # 使用传入的server和pim_helper参数
        if not server:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"success": False, "error": "服务器接口未提供"}
            )

        # 记录请求日志
        server.logger.debug(f"api_get_plugin_repository: Request for plugin_id={plugin_id}")

        # 使用传入的PIM助手
        if not pim_helper:
            server.logger.warning("未找到PIM助手实例，无法获取插件仓库信息")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"success": False, "error": "PIM助手未初始化"}
            )

        # 获取配置中定义的仓库URL
        config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
        server.logger.debug(f"api_get_plugin_repository: Raw config: {config}")

        official_repo_url = config.get("mcdr_plugins_url", "https://api.mcdreforged.com/catalogue/everything_slim.json.xz")
        configured_repos = [official_repo_url]  # 始终包含官方仓库

        # 添加内置的第三方仓库（与前端保持一致）
        loose_repo_url = "https://pfingan-code.github.io/PluginCatalogue/plugins.json"
        configured_repos.append(loose_repo_url)
        server.logger.debug(f"api_get_plugin_repository: Added built-in repository URL: {loose_repo_url}")

        # 添加配置中的其他仓库URL
        if "repositories" in config and isinstance(config["repositories"], list):
            server.logger.debug(f"api_get_plugin_repository: Found repositories in config: {config['repositories']}")
            for repo in config["repositories"]:
                if isinstance(repo, dict) and "url" in repo:
                    # 避免重复添加内置仓库
                    if repo["url"] != loose_repo_url:
                        configured_repos.append(repo["url"])
                        server.logger.debug(f"api_get_plugin_repository: Added repository URL: {repo['url']}")
        else:
            server.logger.debug(f"api_get_plugin_repository: No repositories found in config or not a list")

        server.logger.debug(f"api_get_plugin_repository: Configured repositories: {configured_repos}")

        # 创建一个命令源模拟对象
        class FakeSource:
            def __init__(self, server):
                self.server = server

            def reply(self, message):
                if isinstance(message, str):
                    self.server.logger.debug(f"[仓库查找] {message}")

            def get_server(self):
                return self.server

        source = FakeSource(server)

        # 遍历所有配置的仓库，查找插件
        # 优先检查官方仓库
        official_found = False
        third_party_found = None

        for repo_url in configured_repos:
            server.logger.debug(f"api_get_plugin_repository: Checking repository: {repo_url}")
            try:
                # 获取仓库元数据
                meta_registry = pim_helper.get_cata_meta(source, ignore_ttl=False, repo_url=repo_url)
                if not meta_registry or not hasattr(meta_registry, 'get_plugin_data'):
                    server.logger.debug(f"api_get_plugin_repository: Failed to get meta_registry or get_plugin_data for {repo_url}")
                    continue

                # 查找插件
                plugin_data = meta_registry.get_plugin_data(plugin_id)
                if plugin_data:
                    server.logger.debug(f"api_get_plugin_repository: Plugin {plugin_id} found in {repo_url}")
                    # 找到插件
                    if repo_url == official_repo_url:
                        # 官方仓库中找到，直接返回
                        repo_name = "官方仓库"
                        server.logger.debug(f"在官方仓库中找到插件 {plugin_id}")

                        return JSONResponse(
                            content={
                                "success": True,
                                "repository": {
                                    "name": repo_name,
                                    "url": repo_url,
                                    "is_official": True
                                }
                            }
                        )
                    else:
                        # 第三方仓库中找到，记录但不立即返回
                        if not third_party_found:
                            repo_name = "第三方仓库"

                            # 检查是否是内置仓库
                            if repo_url == loose_repo_url:
                                repo_name = "PF的仓库"
                            else:
                                # 尝试从配置中获取仓库名称
                                if "repositories" in config:
                                    for repo in config["repositories"]:
                                        if isinstance(repo, dict) and repo.get("url") == repo_url:
                                            repo_name = repo.get("name", "第三方仓库")
                                            break

                            third_party_found = {
                                "name": repo_name,
                                "url": repo_url,
                                "is_official": False
                            }
                            server.logger.debug(f"在第三方仓库 {repo_name} 中找到插件 {plugin_id}")
                else:
                    server.logger.debug(f"api_get_plugin_repository: Plugin {plugin_id} NOT found in {repo_url}")
            except Exception as e:
                server.logger.warning(f"检查仓库 {repo_url} 时出错: {e}")
                import traceback
                server.logger.debug(traceback.format_exc())
                continue

        # 如果官方仓库中没有找到，但第三方仓库中有，返回第三方仓库信息
        if third_party_found:
            server.logger.debug(f"插件 {plugin_id} 在第三方仓库中找到: {third_party_found['name']}")
            return JSONResponse(
                content={
                    "success": True,
                    "repository": third_party_found
                }
            )

        # 未找到插件
        server.logger.debug(f"未找到插件 {plugin_id} 所属的仓库")
        return JSONResponse(
            content={
                "success": False,
                "error": "未找到插件所属的仓库"
            }
        )

    except Exception as e:
        if server:
            server.logger.error(f"获取插件仓库信息失败: {e}")
            import traceback
            server.logger.debug(traceback.format_exc())
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": f"获取插件仓库信息失败: {str(e)}"}
        )


async def check_pim_status(
    request: Request,
    token_valid: bool = Depends(verify_token),
    server=None
):
# ... (existing code) ...
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": f"检查PIM状态时出错: {str(e)}"}
        )


async def self_update(
    request: Request,
    token_valid: bool = Depends(verify_token),
    server=None
):
    """执行 WebUI 自身更新"""
    if not token_valid:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "error": "未登录或会话已过期"}
        )

    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    try:
        command = "!!MCDR plugin install -U -y guguwebui"
        server.logger.info(f"执行自更新命令: {command}")
        server.execute_command(command)

        return JSONResponse(
            content={
                "success": True,
                "message": "已发送更新指令到 MCDR，插件将自动重启并完成更新"
            }
        )
    except Exception as e:
        server.logger.error(f"执行自更新失败: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": f"执行自更新失败: {str(e)}"}
        )


async def get_self_update_info(
    request: Request,
    token_valid: bool = Depends(verify_token)
):
    """获取 WebUI 自身更新信息"""

    # 使用 request.app 获取正确的 app 实例
    info = getattr(request.app.state, "self_update_info", {"available": False})
    return JSONResponse(content={"success": True, "info": info})


async def install_pim_plugin(
    request: Request,
    token_valid: bool = Depends(verify_token),
    server=None
):
    """将PIM作为独立插件安装"""
    if not token_valid:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "error": "未登录或会话已过期"}
        )

    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    try:
        # 获取已加载插件列表
        loaded_plugin_metadata, unloaded_plugin_metadata, loaded_plugin, disabled_plugin = load_plugin_info(server)

        # 检查是否已安装（检查插件ID为pim_helper的插件）
        if 'pim_helper' in loaded_plugin_metadata or 'pim_helper' in unloaded_plugin_metadata:
            return JSONResponse(
                content={
                    "status": "success",
                    "message": "PIM插件已安装"
                }
            )

        # 获取MCDR根目录和plugins目录路径
        # 使用get_data_folder()获取插件数据目录，然后回溯到MCDR根目录
        data_folder = server.get_data_folder()
        mcdr_root = os.path.dirname(os.path.dirname(data_folder))  # 从plugins/guguwebui/config回溯到MCDR根目录
        plugins_dir = os.path.join(mcdr_root, "plugins")

        # 创建plugins目录（如果不存在）
        os.makedirs(plugins_dir, exist_ok=True)

        # 将PIM文件夹打包为独立插件
        pim_plugin_path = await package_pim_plugin(server, plugins_dir)

        # 加载插件
        server.load_plugin(pim_plugin_path)

        return JSONResponse(
            content={
                "status": "success",
                "message": "PIM插件已成功安装并加载"
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": f"安装PIM插件时出错: {str(e)}"}
        )


async def toggle_plugin(
    request: Request,
    request_body: ToggleConfig,
    server=None
):
    """切换插件状态（加载/卸载）"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "服务器接口未提供"}
        )

    plugin_id = request_body.plugin_id
    target_status = request_body.status

    # reload only for guguwebui
    if plugin_id == "guguwebui":
        server.reload_plugin(plugin_id)
    # loading
    elif target_status:
        _, unloaded_plugin_metadata, unloaded_plugin, disabled_plugin = (
            load_plugin_info(server)
        )
        plugin_path = unloaded_plugin_metadata.get(plugin_id, {}).get("path")
        # plugin not found
        if not plugin_path:
            return JSONResponse(
                {"status": "error", "message": "Plugin not found"}, status_code=404
            )
        # enable the plugin before load it
        if plugin_path in disabled_plugin:
            server.enable_plugin(plugin_path)
        server.load_plugin(plugin_path)
    # unload
    elif not target_status:
        server.unload_plugin(plugin_id)
    return JSONResponse({"status": "success"})


async def reload_plugin(
    request: Request,
    plugin_info: PluginInfo,
    server=None
):
    """重载插件"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "服务器接口未提供"}
        )

    plugin_id = plugin_info.plugin_id
    if plugin_id == "guguwebui":
        return JSONResponse({"status": "error", "message": "无法处理自身"})

    server_response = server.reload_plugin(plugin_id)

    if server_response: # success
        return JSONResponse({"status": "success"})

    return JSONResponse({"status": "error", "message": f"Reload {plugin_id} failed"}, status_code=500)


async def get_online_plugins(
    request: Request,
    repo_url: str = None,
    server=None,
    pim_helper=None
):
    """获取在线插件列表"""
    # 如果没有服务器接口，无法处理请求
    if not server:
        return []

    # 如果没有PIM助手，无法处理请求
    if not pim_helper:
        server.logger.warning("未找到PIM助手实例，无法获取插件信息")
        return []

    # 获取配置中定义的仓库URL
    config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
    official_repo_url = config.get("mcdr_plugins_url", "https://api.mcdreforged.com/catalogue/everything_slim.json.xz")
    configured_repos = [official_repo_url]  # 始终包含官方仓库

    # 添加配置中的其他仓库URL
    if "repositories" in config and isinstance(config["repositories"], list):
        for repo in config["repositories"]:
            if isinstance(repo, dict) and "url" in repo:
                configured_repos.append(repo["url"])

    try:
        # 创建一个命令源模拟对象，用于PIM助手的API调用
        class FakeSource:
            def __init__(self, server):
                self.server = server

            def reply(self, message):
                if isinstance(message, str):
                    self.server.logger.debug(f"[仓库API] {message}")

            def get_server(self):
                return self.server

        source = FakeSource(server)

        # 如果指定了特定仓库URL，则只获取该仓库的数据
        if repo_url:
            # 检查是否是配置中的仓库，否则视为不受信任的源
            is_configured_repo = repo_url in configured_repos

            # 使用PIM获取元数据，使用ignore_ttl=False以利用PIM的下载失败缓存逻辑
            meta_registry = pim_helper.get_cata_meta(source, ignore_ttl=False, repo_url=repo_url)

            # 如果没有获取到有效的仓库数据，直接返回空列表
            if not meta_registry or not hasattr(meta_registry, 'get_plugins') or not meta_registry.get_plugins():
                server.logger.warning(f"未获取到有效的仓库数据: {repo_url}")
                return []

            # 获取原始仓库数据
            registry_data = {}
            try:
                # 尝试获取原始仓库数据
                if hasattr(meta_registry, 'get_registry_data'):
                    registry_data = meta_registry.get_registry_data()
            except Exception as e:
                server.logger.warning(f"获取原始仓库数据失败: {e}")

            # 检查数据类型 - 处理简化格式(list类型)和标准格式(dict类型)
            if isinstance(registry_data, list):
                # 简化格式 - 直接返回原始数据
                server.logger.debug(f"检测到简化格式仓库数据，直接处理: {repo_url}")
                return registry_data

            # 提取作者信息
            authors_data = {}
            try:
                if registry_data and 'authors' in registry_data and 'authors' in registry_data['authors']:
                    authors_data = registry_data['authors']['authors']
            except Exception as e:
                server.logger.warning(f"提取作者信息失败: {e}")

            # 转换为列表格式返回
            plugins_data = []
            for plugin_id, plugin_data in meta_registry.get_plugins().items():
                try:
                    # 处理作者信息为期望的格式
                    authors = []
                    # 从plugin部分获取作者信息，而不是meta部分
                    if registry_data and 'plugins' in registry_data and plugin_id in registry_data['plugins']:
                        plugin_info = registry_data['plugins'][plugin_id].get('plugin', {})
                        author_names = plugin_info.get('authors', [])

                        for author_name in author_names:
                            if isinstance(author_name, str) and author_name in authors_data:
                                # 从原始数据中获取作者详细信息
                                author_info = authors_data.get(author_name, {})
                                authors.append({
                                    'name': author_info.get('name', author_name),
                                    'link': author_info.get('link', '')
                                })
                            else:
                                # 直接使用作者名称
                                authors.append({
                                    'name': author_name,
                                    'link': ''
                                })
                    # 如果plugin部分没有作者信息，则尝试从plugin_data.author获取
                    elif hasattr(plugin_data, 'author'):
                        for author_item in plugin_data.author:
                            if isinstance(author_item, str):
                                # 原始格式：作者名称是字符串
                                if author_item in authors_data:
                                    # 从原始数据中获取作者详细信息
                                    author_info = authors_data.get(author_item, {})
                                    authors.append({
                                        'name': author_info.get('name', author_item),
                                        'link': author_info.get('link', '')
                                    })
                                else:
                                    # 直接使用作者名称
                                    authors.append({
                                        'name': author_item,
                                        'link': ''
                                    })
                            elif isinstance(author_item, dict):
                                # 简化格式：作者信息已经是字典
                                authors.append(author_item)

                    # 获取最新版本信息
                    latest_release = plugin_data.get_latest_release()

                    # 处理标签信息 (labels)
                    labels = []

                    # 从原始数据中获取plugin信息
                    plugin_info = {}
                    if registry_data and 'plugins' in registry_data and plugin_id in registry_data['plugins']:
                        plugin_info = registry_data['plugins'][plugin_id].get('plugin', {})
                        if 'labels' in plugin_info:
                            labels = plugin_info.get('labels', [])

                    # 处理License信息
                    license_key = "未知"
                    license_url = ""

                    # 从原始数据中获取repository信息
                    repo_info = {}
                    if registry_data and 'plugins' in registry_data and plugin_id in registry_data['plugins']:
                        repo_info = registry_data['plugins'][plugin_id].get('repository', {})
                        if 'license' in repo_info and repo_info['license']:
                            license_info = repo_info['license']
                            license_key = license_info.get('key', '未知')
                            license_url = license_info.get('url', '')

                    # 处理Readme URL
                    readme_url = ""
                    if 'readme_url' in repo_info:
                        readme_url = repo_info.get('readme_url', '')

                    # 计算所有版本的下载总数
                    total_downloads = 0
                    if registry_data and 'plugins' in registry_data and plugin_id in registry_data['plugins']:
                        release_info = registry_data['plugins'][plugin_id].get('release', {})
                        releases = release_info.get('releases', [])
                        for rel in releases:
                            if 'asset' in rel and 'download_count' in rel['asset']:
                                total_downloads += rel['asset']['download_count']

                    # 如果没有找到任何下载数据，但最新版本有下载数，则使用它
                    if total_downloads == 0 and latest_release and hasattr(latest_release, 'download_count'):
                        total_downloads = latest_release.download_count

                    # 创建插件条目
                    plugin_entry = {
                        "id": plugin_data.id,
                        "name": plugin_data.name,
                        "version": plugin_data.version,
                        "description": plugin_data.description,
                        "authors": authors,
                        "dependencies": {k: str(v) for k, v in plugin_data.dependencies.items()},
                        "labels": labels,
                        "repository_url": plugin_data.link,
                        "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "latest_version": plugin_data.latest_version,
                        "license": license_key,
                        "license_url": license_url,
                        "downloads": total_downloads,
                        "readme_url": readme_url,
                    }

                    # 添加最后更新时间
                    if latest_release and hasattr(latest_release, 'created_at'):
                        try:
                            # 将ISO格式时间转换为更友好的格式
                            dt = datetime.datetime.fromisoformat(latest_release.created_at.replace('Z', '+00:00'))
                            plugin_entry["last_update_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except Exception as time_error:
                            server.logger.error(f"处理插件 {plugin_id} 的时间信息时出错: {time_error}")
                            plugin_entry["last_update_time"] = latest_release.created_at if hasattr(latest_release, 'created_at') else ''

                    plugins_data.append(plugin_entry)
                except Exception as plugin_error:
                    server.logger.error(f"处理插件 {plugin_id} 时出错: {plugin_error}")
                    # 继续处理下一个插件

            return plugins_data

        # 如果没有指定特定仓库，则获取所有配置仓库的数据
        else:
            all_plugins_data = []
            for repo_url in configured_repos:
                try:
                    # 为每个仓库递归调用自己
                    repo_plugins = await get_online_plugins(request, repo_url, server, pim_helper)
                    all_plugins_data.extend(repo_plugins)
                except Exception as repo_error:
                    server.logger.error(f"获取仓库 {repo_url} 数据时出错: {repo_error}")
                    # 继续处理下一个仓库

            return all_plugins_data

    except Exception as e:
        # 下载或解析出错，记录详细错误信息
        import traceback
        error_msg = f"获取在线插件列表失败: {str(e)}\n{traceback.format_exc()}"
        if server:
            server.logger.error(error_msg)
        else:
            logging.getLogger(__name__).error(error_msg)
        return []
