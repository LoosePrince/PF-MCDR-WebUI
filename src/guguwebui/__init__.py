import asyncio
import os
import platform
from typing import Optional

from mcdreforged.api.command import Literal, Text
from mcdreforged.api.event import LiteralEvent
from mcdreforged.api.types import PluginServerInterface

from guguwebui.PIM import PluginInstaller, create_installer
from guguwebui.constant import user_db
from guguwebui.utils.auth_util import change_account_command, create_account_command, get_temp_password_command, \
    verify_chat_code_command
from guguwebui.utils.chat_logger import ChatLogger
from guguwebui.utils.file_util import amount_static_files
from guguwebui.utils.mc_util import get_minecraft_path
from guguwebui.utils.mc_util import get_plugins_info
from guguwebui.utils.server_util import patch_asyncio
from guguwebui.web_server import DEFALUT_CONFIG, STATIC_PATH, ThreadedUvicorn, app, init_app, log_watcher

# 全局变量声明
web_server_interface = None
_mounted_to_fastapi_mcdr = False
chat_logger: Optional[ChatLogger] = None


# ============================================================#


def on_load(server: PluginServerInterface, _old):
    global web_server_interface

    server.logger.info("启动 WebUI 中...")

    # 检测并提示插件运行模式
    try:
        from .utils.mc_util import detect_plugin_format
        plugin_format = detect_plugin_format(server)
        format_map = {
            "mcdr_file": ".mcdr 文件",
            "folder": "文件夹",
            "single_file": "单文件 .py",
            "unknown": "未知"
        }
        format_name = format_map.get(plugin_format, "未知")
        server.logger.info(f"插件运行模式: {format_name}")
    except Exception as e:
        server.logger.debug(f"检测插件运行模式时出错: {e}")

    # 首先检查并安装依赖包
    try:
        from .utils.dependency_checker import check_and_install_dependencies
        check_and_install_dependencies(server)
    except Exception as e:
        server.logger.error(f"依赖检查过程中发生错误: {e}")
        server.logger.warning("将尝试继续启动，但可能会遇到导入错误")

    # 导入必需的模块
    try:
        import uvicorn
        # 导入其他模块 - 明确导入需要的内容
        from fastapi.staticfiles import StaticFiles

        server.logger.info("所有模块导入成功")

    except ImportError as e:
        server.logger.error(f"导入模块时发生错误: {e}")
        server.logger.error("请检查依赖包是否正确安装")
        server.logger.error("建议重新启动MCDR让依赖自动安装生效")
        return
    except Exception as e:
        server.logger.error(f"导入模块时发生未知错误: {e}")
        return

    # 在 Windows 平台应用 asyncio 补丁，防止连接重置错误
    if platform.system() == 'Windows':
        server.logger.debug("正在为 Windows 平台应用 asyncio 补丁...")
        patch_asyncio(server)
        server.logger.debug("asyncio 补丁应用完成")

    plugin_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)

    # 检查是否存在 fastapi_mcdr 插件
    fastapi_mcdr = server.get_plugin_instance('fastapi_mcdr')
    use_fastapi_mcdr = False

    # 检查是否强制独立运行
    force_standalone = plugin_config.get('force_standalone', False)
    if force_standalone:
        server.logger.info("强制独立运行模式已启用，将忽略fastapi_mcdr插件")
        fastapi_mcdr = None  # 强制设为None，模拟插件不存在
        use_fastapi_mcdr = False

    # 无论是否独立运行都检查配置
    try:
        from .utils.config_validator import ConfigValidator
        validator = ConfigValidator(server.logger)
        is_valid, validated_config, has_critical_error = validator.validate_config(plugin_config)

        if has_critical_error:
            # 如果使用 fastapi_mcdr 或强制独立运行，则忽略绑定设置错误
            if fastapi_mcdr is not None or force_standalone:
                if fastapi_mcdr is not None:
                    server.logger.warning("由于使用 fastapi_mcdr 插件，将忽略IP和端口设置")
                else:
                    server.logger.warning("由于强制独立运行模式，将忽略IP和端口设置")
                plugin_config = validated_config
            else:
                # 独立模式下，配置错误则拒绝启动
                server.logger.error("配置验证失败，IP或端口配置错误，拒绝启动Web服务")
                server.logger.error(validator.get_validation_summary())
                server.logger.error("请检查配置文件中的host和port设置，然后重新启动插件")
                server.logger.info("正在卸载插件...")
                try:
                    server.unload_plugin("guguwebui")
                except Exception as e:
                    server.logger.error(f"卸载插件时出错: {e}")
                    raise RuntimeError("配置验证失败，插件无法启动")
                return
        elif not is_valid:
            server.logger.error("配置验证失败，使用默认配置启动")
            server.logger.error(validator.get_validation_summary())
            plugin_config = validated_config
        else:
            server.logger.info("配置验证通过")
            if validator.warnings:
                server.logger.info(validator.get_validation_summary())
            plugin_config = validated_config
    except Exception as e:
        server.logger.error(f"配置验证过程中发生错误: {e}")
        server.logger.warning("将使用原始配置继续启动")

    if fastapi_mcdr is not None and not force_standalone:
        server.logger.info("检测到 fastapi_mcdr 插件，将挂载为子应用")
        use_fastapi_mcdr = True

        # 如果 fastapi_mcdr 已准备好，直接挂载
        if fastapi_mcdr.is_ready():
            mount_to_fastapi_mcdr(server, fastapi_mcdr)
        else:
            # 注册事件监听器，等待 fastapi_mcdr 准备好
            server.register_event_listener(
                fastapi_mcdr.COLLECT_EVENT,
                lambda: mount_to_fastapi_mcdr(server, fastapi_mcdr)
            )
            server.logger.info("fastapi_mcdr 尚未准备好，已注册事件监听器")

        # 注册插件卸载事件监听器
        server.register_event_listener(
            LiteralEvent("mcdreforged.plugin_manager.plugin_unloaded"),
            lambda plugin_id: on_plugin_unloaded(server, plugin_id)
        )
        
        # 注册插件加载事件监听器（用于 GUGUBot）
        server.register_event_listener(
            LiteralEvent("mcdreforged.plugin_manager.plugin_loaded"),
            lambda plugin_id: on_plugin_loaded(server, plugin_id)
        )
    elif force_standalone:
        server.logger.info("强制独立运行模式，已忽略fastapi_mcdr插件")
        # 注册插件加载事件监听器（用于 GUGUBot）
        server.register_event_listener(
            LiteralEvent("mcdreforged.plugin_manager.plugin_loaded"),
            lambda plugin_id: on_plugin_loaded(server, plugin_id)
        )
    else:
        server.logger.info("未检测到 fastapi_mcdr 插件，将使用独立服务器模式")
        # 注册插件加载事件监听器（用于 GUGUBot）
        server.register_event_listener(
            LiteralEvent("mcdreforged.plugin_manager.plugin_loaded"),
            lambda plugin_id: on_plugin_loaded(server, plugin_id)
        )

    host = plugin_config['host']
    port = plugin_config['port']
    register_command(server, host, port)  # register MCDR command

    amount_static_files(server)  # move static resource
    # app.mount("/src", StaticFiles(directory=f"{STATIC_PATH}/src"), name="src")
    # app.mount("/js", StaticFiles(directory=f"{STATIC_PATH}/js"), name="js")
    # app.mount("/css", StaticFiles(directory=f"{STATIC_PATH}/css"), name="css")
    # app.mount("/custom", StaticFiles(directory=f"{STATIC_PATH}/custom"), name="custom")
    # # 多语言静态文件
    # app.mount("/lang", StaticFiles(directory=f"{STATIC_PATH}/lang"), name="lang")
    # 前端构建产物（React SPA）
    app.mount("/static", StaticFiles(directory=f"{STATIC_PATH}/static"), name="static")
    # 映射 /assets/ 到 /static/assets/，以支持 Vite 构建的资源路径
    app.mount("/assets", StaticFiles(directory=f"{STATIC_PATH}/static/assets"), name="assets")

    # 初始化应用程序和日志捕获器
    init_app(server)

    # 启动自更新检查
    start_self_update_checker(server)

    # 初始化聊天消息监听器
    try:
        from .utils.chat_logger import ChatLogger
        from .utils.mc_util import create_chat_logger_status_rtext
        global chat_logger
        chat_logger = ChatLogger()
        status_msg = create_chat_logger_status_rtext('init', True)
        server.logger.info(status_msg)
    except Exception as e:
        server.logger.error(f"聊天消息监听器初始化失败: {e}")
        chat_logger = None

    # 如果使用 fastapi_mcdr，则不需要启动独立服务器
    if not use_fastapi_mcdr:
        # 从配置中读取SSL设置
        ssl_enabled = plugin_config.get('ssl_enabled', False)

        # 基本配置
        config_params = {
            'app': app,
            'host': host,
            'port': port,
            'log_level': "warning"
        }

        # 如果启用了SSL，添加SSL配置
        if ssl_enabled:
            try:
                ssl_keyfile = plugin_config.get('ssl_keyfile', '')
                ssl_certfile = plugin_config.get('ssl_certfile', '')
                ssl_keyfile_password = plugin_config.get('ssl_keyfile_password', '')

                if ssl_keyfile and ssl_certfile:
                    # 检查文件是否存在
                    ssl_files_exist = True
                    error_messages = []

                    if not os.path.exists(ssl_certfile):
                        ssl_files_exist = False
                        error_messages.append(f"SSL证书文件不存在: {ssl_certfile}")
                        server.logger.error(f"SSL证书文件不存在: {ssl_certfile}")

                    if not os.path.exists(ssl_keyfile):
                        ssl_files_exist = False
                        error_messages.append(f"SSL密钥文件不存在: {ssl_keyfile}")
                        server.logger.error(f"SSL密钥文件不存在: {ssl_keyfile}")

                    if ssl_files_exist:
                        # 文件都存在，添加SSL配置
                        try:
                            config_params['ssl_keyfile'] = ssl_keyfile
                            config_params['ssl_certfile'] = ssl_certfile
                            if ssl_keyfile_password:
                                config_params['ssl_keyfile_password'] = ssl_keyfile_password
                            server.logger.info("已启用HTTPS模式")
                        except Exception as e:
                            server.logger.error(f"配置HTTPS时发生错误: {e}")
                            server.logger.warning("由于错误，将回退到HTTP模式")
                            ssl_enabled = False
                    else:
                        # 文件不存在，回退到HTTP
                        server.logger.warning("SSL文件不存在，将回退至HTTP模式")
                        for error in error_messages:
                            server.logger.warning(f"{error}")
                        server.logger.info("请在设置页面检查SSL配置，确保文件路径正确并且文件存在")
                        ssl_enabled = False
                else:
                    server.logger.warning("SSL配置不完整，将使用HTTP模式启动")
                    ssl_enabled = False
            except Exception as e:
                server.logger.error(f"处理SSL配置时发生错误: {e}")
                server.logger.warning("由于错误，将回退到HTTP模式")
                ssl_enabled = False

        # 创建配置对象
        config = uvicorn.Config(**config_params)
        web_server_interface = ThreadedUvicorn(server, config)

        # 显示URL（根据是否启用SSL选择协议；IPv6 地址在 URL 中需加方括号）
        protocol = "https" if ssl_enabled else "http"
        from .utils.server_util import format_host_for_url
        host_display = format_host_for_url(host)
        server.logger.info(f"网页地址: {protocol}://{host_display}:{port}")
        web_server_interface.start()
    else:
        server.logger.info("WebUI 已挂载到 fastapi_mcdr 插件，无需启动独立服务器")
        # 尝试获取 fastapi_mcdr 的端口信息
        try:
            # 使用插件自己的方案读取 fastapi_mcdr 配置
            fastapi_config = server.load_config_simple("fastapi_mcdr_config.json", {"host": "0.0.0.0", "port": 8080},
                                                       echo_in_console=False)
            fastapi_port = fastapi_config.get('port', 8080)
            server.logger.info(f"WebUI 访问地址: http://localhost:{fastapi_port}/guguwebui")
            server.logger.info(f"API 文档地址: http://localhost:{fastapi_port}/guguwebui/docs")
        except Exception as e:
            server.logger.debug(f"无法获取 fastapi_mcdr 配置: {e}")
            server.logger.info("WebUI 已挂载到 fastapi_mcdr 插件，访问地址请查看 fastapi_mcdr 插件配置")

    get_plugins_info(app.state.server_interface)

    # 尝试注册 GUGUBot 系统模块
    register_gugubot_system(server)


def mount_to_fastapi_mcdr(server: PluginServerInterface, fastapi_mcdr):
    """挂载 WebUI 到 fastapi_mcdr 插件"""
    global _mounted_to_fastapi_mcdr
    try:
        from .web_server import app
        fastapi_mcdr.mount("guguwebui", app)
        _mounted_to_fastapi_mcdr = True
    except Exception as e:
        server.logger.error(f"挂载到 fastapi_mcdr 时发生错误: {e}")
        server.logger.warning("将回退到独立服务器模式")
        # 这里可以添加回退逻辑，但为了简化，我们只记录错误


def on_plugin_unloaded(server: PluginServerInterface, plugin_id: str):
    """处理插件卸载事件"""
    if plugin_id == "fastapi_mcdr":
        # 检查是否强制独立运行
        from guguwebui.constant import DEFALUT_CONFIG
        plugin_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
        force_standalone = plugin_config.get('force_standalone', False)

        if force_standalone:
            server.logger.info("强制独立运行模式，忽略fastapi_mcdr插件卸载事件")
        else:
            server.logger.warning("检测到 fastapi_mcdr 插件被卸载，WebUI 将切换到独立服务器模式")

            # 启动独立服务器模式
            try:
                start_standalone_server(server)
                server.logger.info("已成功切换到独立服务器模式")
            except Exception as e:
                server.logger.error(f"切换到独立服务器模式失败: {e}")


def on_plugin_loaded(server: PluginServerInterface, plugin_id: str):
    """处理插件加载事件"""
    server.logger.info(f"插件加载事件触发: {plugin_id}")
    if plugin_id == "fastapi_mcdr":
        # 检查是否强制独立运行
        from guguwebui.constant import DEFALUT_CONFIG
        plugin_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
        force_standalone = plugin_config.get('force_standalone', False)

        if force_standalone:
            server.logger.info("强制独立运行模式，忽略fastapi_mcdr插件加载事件")
        else:
            server.logger.info("检测到 fastapi_mcdr 插件被重新加载")
            # 不需要主动切换，fastapi_mcdr 准备好时会自动挂载 WebUI
    elif plugin_id == "gugubot":
        # GUGUBot 插件加载时，尝试注册系统模块
        server.logger.info("检测到 GUGUBot 插件加载，尝试注册 WebUI 系统模块")
        register_gugubot_system(server)


def start_standalone_server(server: PluginServerInterface):
    """启动独立服务器模式"""
    try:
        from .web_server import app, init_app, DEFALUT_CONFIG
        from .utils.mc_util import get_plugins_info
        from .utils.server_util import ThreadedUvicorn
        import uvicorn
        import os

        # 重新初始化应用程序
        init_app(server)

        # 加载配置
        plugin_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
        host = plugin_config['host']
        port = plugin_config['port']

        # 从配置中读取SSL设置
        ssl_enabled = plugin_config.get('ssl_enabled', False)

        # 基本配置
        config_params = {
            'app': app,
            'host': host,
            'port': port,
            'log_level': "warning"
        }

        # 如果启用了SSL，添加SSL配置
        if ssl_enabled:
            try:
                ssl_keyfile = plugin_config.get('ssl_keyfile', '')
                ssl_certfile = plugin_config.get('ssl_certfile', '')
                ssl_keyfile_password = plugin_config.get('ssl_keyfile_password', '')

                if ssl_keyfile and ssl_certfile and os.path.exists(ssl_certfile) and os.path.exists(ssl_keyfile):
                    config_params['ssl_keyfile'] = ssl_keyfile
                    config_params['ssl_certfile'] = ssl_certfile
                    if ssl_keyfile_password:
                        config_params['ssl_keyfile_password'] = ssl_keyfile_password
                    server.logger.info("已启用HTTPS模式")
                else:
                    server.logger.warning("SSL文件不存在，将使用HTTP模式")
                    ssl_enabled = False
            except Exception as e:
                server.logger.error(f"处理SSL配置时发生错误: {e}")
                ssl_enabled = False

        # 创建配置对象
        config = uvicorn.Config(**config_params)
        global web_server_interface
        web_server_interface = ThreadedUvicorn(server, config)

        # 显示URL（IPv6 地址在 URL 中需加方括号）
        protocol = "https" if ssl_enabled else "http"
        from .utils.server_util import format_host_for_url
        host_display = format_host_for_url(host)
        server.logger.info(f"独立服务器已启动: {protocol}://{host_display}:{port}")
        web_server_interface.start()

        # 获取插件信息
        get_plugins_info(app.state.server_interface)

    except Exception as e:
        server.logger.error(f"启动独立服务器失败: {e}")
        raise


# 全局变量，用于管理检查线程
_checker_thread = None
_checker_running = False


def start_plugin_status_checker(server: PluginServerInterface):
    """启动定期检查插件状态的任务"""
    global _checker_thread, _checker_running
    import threading
    import time

    # 如果已经有检查线程在运行，先停止它
    if _checker_thread is not None and _checker_thread.is_alive():
        _checker_running = False
        _checker_thread.join(timeout=1)
        server.logger.debug("已停止之前的检查线程")

    _checker_running = True

    def check_plugin_status():
        """定期检查 fastapi_mcdr 插件状态"""
        while _checker_running:
            try:
                time.sleep(5)  # 每5秒检查一次

                # 检查 fastapi_mcdr 插件是否还存在
                fastapi_mcdr = server.get_plugin_instance('fastapi_mcdr')
                if fastapi_mcdr is None:
                    # 检查是否强制独立运行
                    from guguwebui.constant import DEFALUT_CONFIG
                    plugin_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
                    force_standalone = plugin_config.get('force_standalone', False)

                    if force_standalone:
                        server.logger.debug("强制独立运行模式，忽略fastapi_mcdr插件状态变化")
                    else:
                        server.logger.warning("定期检查发现 fastapi_mcdr 插件已卸载，切换到独立服务器模式")
                        try:
                            start_standalone_server(server)
                            server.logger.info("已成功切换到独立服务器模式")
                            break  # 退出检查循环
                        except Exception as e:
                            server.logger.error(f"切换到独立服务器模式失败: {e}")
                            break

            except Exception as e:
                server.logger.debug(f"插件状态检查时出错: {e}")
                break

    # 启动检查线程
    _checker_thread = threading.Thread(target=check_plugin_status, daemon=True)
    _checker_thread.start()
    server.logger.info("已启动插件状态定期检查任务")


def start_self_update_checker(server: PluginServerInterface):
    """启动 WebUI 自身更新检查任务"""
    import threading
    import time
    from .utils.mc_util import check_self_update
    from .web_server import app

    def check_task():
        # 启动后先延迟 10 秒检查一次，确保系统已完全启动
        time.sleep(10)
        while True:
            try:
                result = check_self_update(server)
                if result.get("available"):
                    latest = result.get("latest")
                    server.logger.info(
                        f"§6[WebUI] 发现新版本: §a{latest}§6，请前往 Web 界面或在终端执行 §b!!MCDR plugin install -U -y guguwebui §6进行更新")
                    # 存储到 app.state 供前端查询
                    if hasattr(app, "state"):
                        app.state.self_update_info = result
            except Exception as e:
                server.logger.debug(f"自更新检查任务出错: {e}")

            # 每 12 小时检查一次
            time.sleep(12 * 3600)

    thread = threading.Thread(target=check_task, daemon=True)
    thread.start()
    server.logger.info("已启动 WebUI 自更新检查任务 (每 12 小时)")


def on_unload(server: PluginServerInterface):
    global _mounted_to_fastapi_mcdr
    server.logger.info("正在卸载 WebUI...")
    
    # 卸载 GUGUBot 系统模块
    unregister_gugubot_system(server)

    # 优先从 fastapi_mcdr 取消挂载（不依赖 config / is_ready，仅根据挂载标志）
    if _mounted_to_fastapi_mcdr:
        try:
            fastapi_mcdr = server.get_plugin_instance('fastapi_mcdr')
            if fastapi_mcdr is not None:
                fastapi_mcdr.unmount("guguwebui")
                server.logger.info("已从 fastapi_mcdr 插件卸载 WebUI")
        except Exception as e:
            server.logger.warning(f"从 fastapi_mcdr 卸载时出错: {e}")
        finally:
            _mounted_to_fastapi_mcdr = False

    # 停止插件状态检查线程
    global _checker_running, _checker_thread
    if _checker_running:
        _checker_running = False
        if _checker_thread is not None and _checker_thread.is_alive():
            _checker_thread.join(timeout=1)
            server.logger.debug("已停止插件状态检查线程")

    # 停止日志捕获
    try:
        from .web_server import log_watcher
        if log_watcher:
            log_watcher.stop()
            server.logger.debug("日志捕获器已停止")
    except (ImportError, AttributeError) as e:
        server.logger.debug(f"日志捕获器未初始化或导入失败: {e}")
    except Exception as e:
        server.logger.warning(f"停止日志捕获器时出错: {e}")

    # 停止Web服务器（仅在独立模式下需要）
    try:
        if 'web_server_interface' in globals() and web_server_interface:
            # 如果使用了SSL，添加特殊处理
            try:
                from .web_server import DEFALUT_CONFIG
                plugin_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
                ssl_enabled = plugin_config.get('ssl_enabled', False)

                if ssl_enabled:
                    server.logger.debug("检测到HTTPS模式，使用特殊卸载流程")

                    # 尝试特殊处理HTTPS相关资源
                    try:
                        import gc
                        import ssl

                        # 尝试关闭所有SSL相关对象
                        for obj in gc.get_objects():
                            try:
                                if isinstance(obj, ssl.SSLSocket) and hasattr(obj, 'close'):
                                    obj.close()
                            except Exception:
                                pass

                        server.logger.debug("HTTPS资源清理完成")
                    except Exception as e:
                        server.logger.warning(f"HTTPS资源清理时出错: {e}")
            except Exception as e:
                server.logger.warning(f"检查SSL配置时出错: {e}")

            # 正常停止Web服务器
            web_server_interface.stop()
            server.logger.debug("Web服务器已停止")
    except Exception as e:
        server.logger.warning(f"停止Web服务器时出错: {e}")

    # 清理事件循环和asyncio相关资源
    try:
        # 获取当前事件循环
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                server.logger.debug("关闭asyncio事件循环")
                # 停止所有任务
                try:
                    for task in asyncio.all_tasks(loop):
                        task.cancel()
                except Exception:
                    pass

                # 运行一次loop确保任务被取消
                if not loop.is_closed():
                    loop.run_until_complete(asyncio.sleep(0))

                # 关闭事件循环
                if not loop.is_closed():
                    loop.close()
        except Exception:
            pass
    except Exception as e:
        server.logger.warning(f"清理asyncio资源时出错: {e}")

    # 强制清理环境
    try:
        import gc
        gc.collect()  # 强制垃圾回收
        server.logger.debug("垃圾回收已完成")
    except Exception as e:
        server.logger.warning(f"垃圾回收时出错: {e}")

    server.logger.info("WebUI 已卸载")


def register_command(server: PluginServerInterface, host: str, port: int):
    from .utils.auth_util import get_temp_password_command, create_account_command, change_account_command, \
        verify_chat_code_command  # 在函数内部导入所有需要的命令函数

    # 注册指令
    server.register_command(
        Literal('!!webui')
        .then(
            Literal('create')
            .requires(lambda src: src.has_permission(3))
            .then(
                Text('account')
                .then(
                    Text('password')
                    .runs(lambda src, ctx: create_account_command(src, ctx, host, port))
                )
            )
        )
        .then(
            Literal('change')
            .requires(lambda src: src.has_permission(3))
            .then(
                Text('account')
                .then(
                    Text('old password')
                    .then(
                        Text('new password')
                        .runs(lambda src, ctx: change_account_command(src, ctx, host, port))
                    )
                )
            )
        )
        .then(
            Literal('temp')
            .requires(lambda src: src.has_permission(3))
            .runs(lambda src, ctx: get_temp_password_command(src, ctx, host, port))
        )
        .then(
            Literal('verify')
            .requires(lambda src: src.has_permission(1))
            .then(
                Text('code')
                .runs(lambda src, ctx: verify_chat_code_command(src, ctx))
            )
        )
    )

    server.register_help_message("!!webui", "GUGUWebUI 相关指令", 3)


def __get_help_message():
    help_message = "!!webui create <account> <password>: 注册 guguwebui 账户\n"
    help_message += "!!webui change <account> <old password> <new password>: 修改 guguwebui 账户密码\n"
    help_message += "!!webui temp: 获取 guguwebui 临时密码\n"
    help_message += "!!webui verify <code>: 验证聊天页验证码\n"
    return help_message


def on_user_info(server: PluginServerInterface, info):
    """监听玩家聊天消息并记录到聊天日志"""
    try:
        # 检查是否有聊天日志记录器
        if 'chat_logger' in globals() and chat_logger is not None:
            # 检查是否是玩家消息（info.is_user 为 True）
            if info.is_user:
                # 获取玩家名称和消息内容
                player_name = info.player
                message_content = info.content

                # 检查玩家名称和消息内容是否有效
                if player_name and message_content and player_name.strip() and message_content.strip():
                    # 记录聊天消息
                    chat_logger.add_message(player_name.strip(), message_content.strip(), server=server)
                    from .utils.mc_util import create_chat_logger_status_rtext
                    status_msg = create_chat_logger_status_rtext('record', True, player_name.strip(),
                                                                 message_content.strip())
                    server.logger.debug(status_msg)
                else:
                    server.logger.debug(f"跳过无效的聊天消息: player={player_name}, content={message_content}")
    except Exception as e:
        server.logger.error(f"记录聊天消息时出错: {e}")


def send_message_to_webui(server_interface, source: str, message, message_type: str = "info",
                          target_players: list = None, metadata: dict = None, is_rtext: bool = False):
    """供其他插件调用的函数，用于发送消息到WebUI并同步到游戏"""
    from .utils.mc_util import send_message_to_webui as _send_message_to_webui
    return _send_message_to_webui(server_interface, source, message, message_type, target_players, metadata, is_rtext)


def register_plugin_page(plugin_id: str, html_path: str):
    """
    供其他插件调用的函数，用于注册其自定义网页

    Args:
        plugin_id: 插件ID
        html_path: 网页 HTML 文件的完整路径或相对于 config 目录的路径
    """
    from guguwebui.constant import REGISTERED_PLUGIN_PAGES
    REGISTERED_PLUGIN_PAGES[plugin_id] = html_path


def register_gugubot_system(server: PluginServerInterface):
    """
    注册 WebUI 系统模块到 GUGUBot
    
    Parameters
    ----------
    server : PluginServerInterface
        MCDR 服务器接口
    """
    try:
        # 检测 GUGUBot 插件是否存在
        gugubot_module = server.get_plugin_instance("gugubot")
        if not gugubot_module:
            return

        # 通过 connector_manager 获取 SystemManager
        connector_manager = getattr(gugubot_module, "connector_manager", None)
        if not connector_manager:
            return
        
        system_manager = getattr(connector_manager, "system_manager", None)
        if not system_manager:
            return

        # 检查系统是否已注册
        systems = getattr(system_manager, "systems", [])
        for system in systems:
            if hasattr(system, "name") and system.name == "webui":
                # 如果已注册但 system_manager 为 None，更新它
                if hasattr(system, "system_manager") and system.system_manager is None:
                    system.system_manager = system_manager
                return

        # 获取 GUGUBot 配置
        gugubot_config = {}
        config_paths = ["GUGUbot/config.json", "GUGUBot/config.json", "gugubot/config.json"]
        
        for config_path in config_paths:
            try:
                gugubot_config = server.load_config_simple(config_path, {}, echo_in_console=False)
                break
            except Exception:
                continue
        
        # 如果无法加载配置，尝试从模块获取
        if not gugubot_config:
            gugubot_config = getattr(gugubot_module, "gugubot_config", None) or getattr(gugubot_module, "config", {})

        # 创建并注册系统模块
        from .integrations.gugubot_system import create_webui_system
        
        webui_system = create_webui_system(server, gugubot_config, system_manager)
        
        # 初始化系统
        if hasattr(webui_system, "initialize"):
            webui_system.initialize()
        
        # 注册到 SystemManager
        if hasattr(system_manager, "systems"):
            system_manager.systems.append(webui_system)
            server.logger.info("WebUI 系统模块已成功注册到 GUGUBot")

    except Exception as e:
        server.logger.debug(f"注册 GUGUBot 系统模块时出错: {e}")


def unregister_gugubot_system(server: PluginServerInterface):
    """
    从 GUGUBot 卸载 WebUI 系统模块
    
    Parameters
    ----------
    server : PluginServerInterface
        MCDR 服务器接口
    """
    try:
        gugubot_module = server.get_plugin_instance("gugubot")
        if not gugubot_module:
            return

        connector_manager = getattr(gugubot_module, "connector_manager", None)
        if not connector_manager:
            return
        
        system_manager = getattr(connector_manager, "system_manager", None)
        if not system_manager:
            return

        # 查找并移除 WebUI 系统
        systems = getattr(system_manager, "systems", [])
        for i, system in enumerate(systems):
            if hasattr(system, "name") and system.name == "webui":
                systems.pop(i)
                server.logger.info("WebUI 系统模块已从 GUGUBot 卸载")
                break

    except Exception:
        pass
