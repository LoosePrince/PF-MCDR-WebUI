import asyncio
import json
import os
from pathlib import Path

import aiohttp
import anyio
import javaproperties
from mcdreforged.api.rtext import RAction, RColor, RText, RTextBase, RTextList
# MCDR 内部实现，非公开 API，可能随 MCDR 版本变化
from mcdreforged.plugin.type.directory_plugin import DirectoryPlugin
from mcdreforged.plugin.type.multi_file_plugin import MultiFilePlugin
from mcdreforged.plugin.type.packed_plugin import PackedPlugin as ZippedPlugin
from mcdreforged.plugin.type.solo_plugin import SoloPlugin
from mcstatus import JavaServer
from ruamel.yaml import YAML


# --- Synchronous Utility Functions ---

def get_minecraft_path(server_interface=None, path_type="working_directory"):
    """获取Minecraft服务器相关路径 (同步版本)"""
    try:
        working_directory = None
        if server_interface:
            try:
                mcdr_config = server_interface.get_mcdr_config()
                if hasattr(mcdr_config, 'working_directory'):
                    working_directory = mcdr_config.working_directory
            except:
                pass
        if not working_directory:
            mcdr_config_path = "config.yml"
            if not os.path.exists(mcdr_config_path):
                working_directory = "server"
            else:
                yaml = YAML()
                with open(mcdr_config_path, 'r', encoding='utf-8') as f:
                    config = yaml.load(f)
                working_directory = config.get('working_directory', 'server')
        path_map = {
            "working_directory": working_directory,
            "logs": os.path.join(working_directory, "logs"),
            "usercache": os.path.join(working_directory, "usercache.json"),
            "server_jar": working_directory,
            "worlds": os.path.join(working_directory, "worlds"),
            "plugins": os.path.join(working_directory, "plugins"),
            "mods": os.path.join(working_directory, "mods"),
        }
        return path_map.get(path_type, working_directory)
    except Exception:
        return "server"


def get_server_port(server_interface=None) -> int:
    """获取Minecraft服务器端口"""
    try:
        properties_path = Path(get_minecraft_path(server_interface, "working_directory")) / "server.properties"
        if properties_path.exists():
            with open(properties_path, "r", encoding="UTF-8") as f:
                data = javaproperties.load(f)
            return int(data.get("server-port", 25565))
        return 25565
    except Exception:
        return 25565


def get_plugin_version():
    """获取插件的真实版本号"""
    try:
        from mcdreforged.api.types import PluginServerInterface
        metadata = PluginServerInterface.psi().get_self_metadata()
        return metadata.version
    except Exception:
        return "1.0.0"


def find_plugin_config_paths(plugin_id: str) -> list:
    """查找插件的所有配置文件路径"""
    config_dir = Path("./config")
    MCDR_plugin_folder = config_dir / plugin_id
    single_file_path = config_dir / plugin_id
    response = []
    config_suffix = [".json", ".yml", ".yaml"]
    single_file_paths = [single_file_path.with_suffix(suffix) for suffix in config_suffix]

    if MCDR_plugin_folder.exists():
        response += [file for file in MCDR_plugin_folder.rglob("*") if file.suffix.lower() in config_suffix]
    else:
        if config_dir.exists():
            for item in config_dir.iterdir():
                if item.is_dir() and item.name.lower() == plugin_id.lower():
                    response += [file for file in item.rglob("*") if file.suffix.lower() in config_suffix]

    for file_path in single_file_paths:
        if file_path.exists():
            response.append(file_path)
        else:
            parent_dir = file_path.parent
            if parent_dir.exists():
                for item in parent_dir.iterdir():
                    if item.is_file() and item.stem.lower() == plugin_id.lower() and item.suffix.lower() in config_suffix:
                        response.append(item)

    return [str(i) for i in response if not Path(i).stem.lower().endswith("_lang")]


def load_plugin_info(server_interface):
    """加载所有插件的信息"""
    from .file_util import extract_metadata
    loaded_metadata = server_interface.get_all_metadata()
    disabled_plugins = server_interface.get_disabled_plugin_list()
    unloaded_plugins = server_interface.get_unloaded_plugin_list()
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


def get_plugins_info(server_interface):
    """获取插件列表及其元数据"""
    ignore_plugin = ["mcdreforged", "python"]
    loaded_metadata, unloaded_metadata, unloaded_plugins, disabled_plugins = load_plugin_info(server_interface)

    def fetch_plugin_versions():
        try:
            from guguwebui.PIM import PIMHelper
            class DummySource:
                def reply(self, message): pass

                @staticmethod
                def get_server(): return server_interface

            pim_helper = PIMHelper(server_interface)
            dummy_source = DummySource()
            # 仅基于 PIM 默认逻辑（官方仓库）获取版本信息
            cata_meta = pim_helper.get_cata_meta(dummy_source)
            plugins = cata_meta.get_plugins()
            return {plugin_id: plugin_data.latest_version for plugin_id, plugin_data in plugins.items()}
        except Exception:
            return {}

    plugin_versions = fetch_plugin_versions()
    respond = []
    import copy
    # MCDR 内部实现，非公开 API，可能随 MCDR 版本变化
    from mcdreforged.plugin.meta.metadata import Metadata
    merged_metadata = copy.deepcopy(unloaded_metadata)
    merged_metadata.update(loaded_metadata)

    for plugin_name, plugin_metadata in merged_metadata.items():
        if plugin_name in ignore_plugin: continue
        try:
            if not isinstance(plugin_metadata, Metadata):
                plugin_metadata = Metadata(plugin_metadata)
            latest_version = plugin_versions.get(plugin_name, None)
            if latest_version and ("-v" in latest_version or "-" in latest_version):
                version_parts = latest_version.split("-v")
                if len(version_parts) > 1:
                    latest_version = version_parts[1]
                else:
                    version_parts = latest_version.split("-")
                    if len(version_parts) > 1:
                        latest_version = version_parts[-1]
                        if latest_version.startswith("v"): latest_version = latest_version[1:]

            try:
                raw_desc = plugin_metadata.description
                if isinstance(raw_desc, dict):
                    full_desc = {}
                    for k, v in raw_desc.items():
                        if not isinstance(v, str): continue
                        key_norm = str(k).lower().replace('-', '_')
                        full_desc[key_norm] = v
                    description = full_desc
                else:
                    description = str(raw_desc) if raw_desc is not None else ""
            except Exception:
                description = "该插件数据异常"

            try:
                author_info = plugin_metadata.author
                if isinstance(author_info, list):
                    if author_info and isinstance(author_info[0], dict):
                        author = ", ".join(author.get('name', '') for author in author_info)
                    else:
                        author = ", ".join(str(a) for a in author_info)
                else:
                    author = str(author_info)
            except:
                author = "未知"

            respond.append({
                "id": str(plugin_metadata.id),
                "name": str(plugin_metadata.name) if hasattr(plugin_metadata, 'name') else plugin_name,
                "description": description,
                "author": author,
                "github": str(plugin_metadata.link) if hasattr(plugin_metadata, 'link') else "",
                "version": str(plugin_metadata.version) if hasattr(plugin_metadata, 'version') else "未知",
                "version_latest": str(latest_version) if latest_version else str(plugin_metadata.version) if hasattr(
                    plugin_metadata, 'version') else "未知",
                "status": "loaded" if str(plugin_metadata.id) in loaded_metadata else "disabled" if str(
                    plugin_metadata.id) in disabled_plugins else "unloaded",
                "path": plugin_name if plugin_name in unloaded_plugins + disabled_plugins else "",
                "config_file": bool(find_plugin_config_paths(str(plugin_metadata.id))) if hasattr(plugin_metadata,
                                                                                                  'id') else False,
                "repository": None
            })
        except Exception:
            respond.append({
                "id": plugin_name, "name": plugin_name, "description": "该插件数据异常",
                "author": "未知", "github": "", "version": "未知", "version_latest": "未知",
                "status": "loaded" if plugin_name in loaded_metadata else "disabled" if plugin_name in disabled_plugins else "unloaded",
                "path": plugin_name if plugin_name in unloaded_plugins + disabled_plugins else "",
                "config_file": False
            })
    return respond


def format_uuid(uuid_string):
    """格式化UUID"""
    try:
        uuid_clean = uuid_string.replace('-', '')
        if len(uuid_clean) == 32 and all(c in '0123456789abcdefABCDEF' for c in uuid_clean):
            formatted_uuid = f"{uuid_clean[:8]}-{uuid_clean[8:12]}-{uuid_clean[12:16]}-{uuid_clean[16:20]}-{uuid_clean[20:32]}"
            return formatted_uuid.lower()
        if len(uuid_string) == 36 and uuid_string.count('-') == 4:
            return uuid_string.lower()
        return uuid_string
    except Exception:
        return uuid_string


def is_player(name: str, server_interface=None) -> bool:
    """检查是否为真实玩家"""
    try:
        if not server_interface: return True
        plugin_instance = server_interface.get_plugin_instance("player_ip_logger")
        if plugin_instance and hasattr(plugin_instance, 'is_player'):
            return plugin_instance.is_player(name)
        return True
    except Exception:
        return True


def get_bot_list(server_interface=None) -> list:
    """获取假人列表"""
    try:
        if not server_interface: return []
        online_players = set()
        if hasattr(server_interface, "is_rcon_running") and server_interface.is_rcon_running():
            feedback = server_interface.rcon_query("list")
            if isinstance(feedback, str) and ":" in feedback:
                names_part = feedback.split(":", 1)[1].strip()
                if names_part:
                    for name in [n.strip() for n in names_part.split(",") if n.strip()]:
                        online_players.add(name)
        if not online_players: return []
        return [p for p in online_players if not is_player(p, server_interface)]
    except Exception:
        return []


def create_chat_message_rtext(player_id: str, message: str, player_uuid: str = "未知"):
    """创建聊天消息的RText"""
    name_part = RText(player_id, color=RColor.white)
    hover_text = f"玩家: {player_id}\n来源: WebUI\nUUID: {player_uuid}\n点击快速填入 /tell 命令"
    name_part.h(hover_text)
    name_part.c(RAction.suggest_command, f"/tell {player_id} ")
    return RTextList(RText("<", color=RColor.white), name_part, RText("> ", color=RColor.white),
                     RText(message, color=RColor.white))


def create_chat_logger_status_rtext(action: str, success: bool = True, player_name: str = None,
                                    message_content: str = None):
    """创建聊天日志状态的RText"""
    if action == 'init':
        return RText("聊天消息监听器初始化成功" if success else "聊天消息监听器初始化失败",
                     color=RColor.green if success else RColor.red)
    elif action == 'clear':
        return RText("聊天消息已清空" if success else "聊天消息清空失败", color=RColor.green if success else RColor.red)
    elif action == 'record':
        if success and player_name and message_content: return RTextList(RText("记录玩家 ", color=RColor.green),
                                                                         RText(player_name, color=RColor.yellow),
                                                                         RText(" 的聊天消息: ", color=RColor.green),
                                                                         RText(message_content, color=RColor.white))
        return RText("聊天消息记录成功" if success else "聊天消息记录失败",
                     color=RColor.green if success else RColor.red)
    return RText(f"聊天日志操作: {action}", color=RColor.blue)


def create_rtext_from_data(source: str, rtext_data, player_uuid: str = "未知") -> RTextBase:
    """从RText数据创建RText对象"""
    name_part = RText(f"[{source}]", color=RColor.gray)
    hover_text = f"插件: {source}\n来源: 插件\nUUID: {player_uuid}"
    name_part.h(hover_text)

    if isinstance(rtext_data, dict):
        rtext_component = _parse_rtext_component(rtext_data)
        return RTextList(name_part, RText(" "), rtext_component)
    elif isinstance(rtext_data, list):
        components = []
        for item in rtext_data:
            if isinstance(item, dict):
                components.append(_parse_rtext_component(item))
            else:
                components.append(RText(str(item)))
        return RTextList(name_part, RText(" "), *components)
    else:
        return RTextList(name_part, RText(" "), RText(str(rtext_data)))


def _parse_rtext_component(component: dict) -> RTextBase:
    """解析单个RText组件"""
    from mcdreforged.api.rtext import RStyle
    text = component.get('text', '')
    rtext = RText(text)
    if 'color' in component:
        color_name = component['color']
        if hasattr(RColor, color_name):
            rtext = rtext.set_color(getattr(RColor, color_name))
    styles = []
    if component.get('bold'): styles.append(RStyle.bold)
    if component.get('italic'): styles.append(RStyle.italic)
    if component.get('underlined'): styles.append(RStyle.underlined)
    if component.get('strikethrough'): styles.append(RStyle.strikethrough)
    if component.get('obfuscated'): styles.append(RStyle.obfuscated)
    if styles: rtext = rtext.set_styles(styles)
    if 'clickEvent' in component:
        click_event = component['clickEvent']
        action = click_event.get('action')
        value = click_event.get('value')
        if action == 'run_command' and value:
            rtext = rtext.c(RAction.run_command, value)
        elif action == 'suggest_command' and value:
            rtext = rtext.c(RAction.suggest_command, value)
        elif action == 'open_url' and value:
            rtext = rtext.c(RAction.open_url, value)
        elif action == 'copy_to_clipboard' and value:
            rtext = rtext.c(RAction.copy_to_clipboard, value)
    if 'hoverEvent' in component:
        hover_event = component['hoverEvent']
        if hover_event.get('action') == 'show_text' and 'value' in hover_event:
            rtext = rtext.h(hover_event['value'])
    if 'extra' in component and isinstance(component['extra'], list):
        extra_components = []
        for extra in component['extra']:
            if isinstance(extra, dict):
                extra_components.append(_parse_rtext_component(extra))
            else:
                extra_components.append(RText(str(extra)))
        return RTextList(rtext, *extra_components)
    return rtext


def send_message_to_webui(server_interface, source: str, message, message_type: str = "info",
                          target_players: list = None, metadata: dict = None, is_rtext: bool = False):
    """供其他插件调用的函数，用于发送消息到WebUI并同步到游戏"""
    try:
        from mcdreforged.api.event import LiteralEvent
        import datetime
        import time
        import json

        processed_message = message
        rtext_data = None

        if is_rtext:
            if hasattr(message, 'to_json_object'):
                rtext_data = message.to_json_object()
                processed_message = str(message)
            elif isinstance(message, (dict, list)):
                rtext_data = message
                processed_message = json.dumps(message, ensure_ascii=False)
            elif isinstance(message, str):
                try:
                    rtext_data = json.loads(message)
                    processed_message = message
                except json.JSONDecodeError:
                    rtext_data = None
                    processed_message = message

        player_uuid = f"plugin_{source}"

        if is_rtext and rtext_data:
            if hasattr(message, 'to_json_object'):
                rtext_message = message
            else:
                rtext_message = create_rtext_from_data(source, rtext_data, player_uuid)
        else:
            rtext_message = create_chat_message_rtext(source, processed_message, player_uuid)

        try:
            event_data = (
                source, source, player_uuid, processed_message, f"plugin_{source}",
                int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            )
            server_interface.dispatch_event(LiteralEvent("webui.chat_message_sent"), event_data)
        except Exception as e:
            server_interface.logger.error(f"分发WebUI聊天消息事件失败: {e}")

        server_interface.broadcast(rtext_message)

        try:
            from .chat_logger import ChatLogger
            chat_logger = ChatLogger()
            final_rtext_data = rtext_data if rtext_data else (
                rtext_message.to_json_object() if hasattr(rtext_message, 'to_json_object') else None)
            chat_logger.add_message(source, processed_message, rtext_data=final_rtext_data, message_type=2,
                                    server=server_interface)
        except Exception as e:
            server_interface.logger.warning(f"记录聊天消息失败: {e}")

        return True
    except Exception as e:
        if server_interface:
            server_interface.logger.error(f"发送WebUI消息失败: {e}")
        return False


# --- Asynchronous Utility Functions ---

async def get_minecraft_path_async(server_interface=None, path_type="working_directory"):
    """异步获取Minecraft服务器相关路径"""
    try:
        working_directory = None
        if server_interface:
            try:
                mcdr_config = server_interface.get_mcdr_config()
                if hasattr(mcdr_config, 'working_directory'):
                    working_directory = mcdr_config.working_directory
            except:
                pass

        if not working_directory:
            mcdr_config_path = Path("config.yml")
            if not await anyio.Path(mcdr_config_path).exists():
                working_directory = "server"
            else:
                yaml = YAML()
                async with await anyio.open_file(mcdr_config_path, mode='r', encoding='utf-8') as f:
                    content = await f.read()
                    config = yaml.load(content)
                working_directory = config.get('working_directory', 'server')

        path_map = {
            "working_directory": working_directory,
            "logs": os.path.join(working_directory, "logs"),
            "usercache": os.path.join(working_directory, "usercache.json"),
            "server_jar": working_directory,
            "worlds": os.path.join(working_directory, "worlds"),
            "plugins": os.path.join(working_directory, "plugins"),
            "mods": os.path.join(working_directory, "mods"),
        }
        return path_map.get(path_type, working_directory)
    except Exception:
        return "server"


async def get_player_uuid(player_name, server_interface=None, use_api=True):
    """异步获取玩家UUID"""
    try:
        try:
            usercache_path = Path(await get_minecraft_path_async(server_interface, "usercache"))
            if await anyio.Path(usercache_path).exists():
                async with await anyio.open_file(usercache_path, mode='r', encoding='utf-8') as f:
                    usercache_data = json.loads(await f.read())
                for entry in usercache_data:
                    if entry.get('name') == player_name:
                        uuid = entry.get('uuid')
                        if uuid: return format_uuid(uuid)
        except Exception as e:
            if server_interface: server_interface.logger.debug(f"从usercache.json获取UUID失败: {e}")

        if use_api:
            try:
                api_url = f"https://api.mojang.com/users/profiles/minecraft/{player_name}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            uuid = data.get('id')
                            if uuid: return format_uuid(uuid)
            except Exception as e:
                if server_interface: server_interface.logger.debug(f"Mojang API查询失败: {e}")
        return None
    except Exception as e:
        if server_interface: server_interface.logger.error(f"获取玩家UUID时发生错误: {e}")
        return None


async def get_player_info(player_name, server_interface=None, include_uuid=True):
    """异步获取玩家信息"""
    try:
        player_info = {'name': player_name, 'online': False, 'last_seen': None}
        if include_uuid:
            player_info['uuid'] = await get_player_uuid(player_name, server_interface)
        if server_interface:
            try:
                player = server_interface.get_player_info(player_name)
                if player: player_info['online'] = True
            except:
                pass
        try:
            usercache_path = Path(await get_minecraft_path_async(server_interface, "usercache"))
            if await anyio.Path(usercache_path).exists():
                async with await anyio.open_file(usercache_path, mode='r', encoding='utf-8') as f:
                    usercache_data = json.loads(await f.read())
                for entry in usercache_data:
                    if entry.get('name') == player_name:
                        player_info['last_seen'] = entry.get('expiresOn')
                        break
        except:
            pass
        return player_info
    except Exception as e:
        return {'name': player_name, 'error': str(e)}


async def get_java_server_info(server_port):
    """异步获取Java服务器信息"""
    try:
        loop = asyncio.get_event_loop()
        server = await loop.run_in_executor(None, JavaServer.lookup, f"127.0.0.1:{server_port}")
        status = await loop.run_in_executor(None, server.status)
        if status:
            return {
                "server_version": status.version.name,
                "server_player_count": status.players.online,
                "server_maxinum_player_count": status.players.max
            }
        return {}
    except Exception:
        return {}


# --- MCDR Adapter and Plugin Format ---

from .mcdr_adapter import MCDRAdapter


def detect_plugin_format(server) -> str:
    """检测插件运行格式"""
    try:
        plugin = MCDRAdapter.get_plugin_object(server)
        if not plugin: return "unknown"
        if isinstance(plugin, SoloPlugin): return "single_file"
        if isinstance(plugin, MultiFilePlugin):
            if isinstance(plugin, ZippedPlugin): return "mcdr_file"
            if isinstance(plugin, DirectoryPlugin): return "folder"
        plugin_path = getattr(plugin, 'file_path', None)
        if plugin_path:
            if os.path.isdir(plugin_path): return "folder"
            if plugin_path.endswith(('.mcdr', '.pyz')): return "mcdr_file"
            if plugin_path.endswith('.py'): return "single_file"
        return "unknown"
    except Exception:
        return "unknown"


def check_self_update(server):
    """检查 WebUI 插件自身是否有更新"""
    try:
        from guguwebui.PIM import PIMHelper
        from packaging.version import parse as parse_version
        try:
            plugins = get_plugins_info(server)
            current_version = None
            for p in plugins:
                if p.get("id") == "guguwebui":
                    current_version = str(p.get("version") or "1.0.0")
                    break
            if not current_version:
                current_version = get_plugin_version()
        except Exception:
            current_version = get_plugin_version()

        class DummySource:
            def reply(self, message): pass

            def get_server(self): return server

        pim_helper = PIMHelper(server)
        source = DummySource()

        # 仅基于 PIM 默认逻辑（官方仓库）检查“最新版本”
        meta = pim_helper.get_cata_meta(source)
        plugin_data = meta.get_plugin_data("guguwebui")

        if plugin_data:
            latest_version = plugin_data.latest_version
            if parse_version(latest_version) > parse_version(current_version):
                return {
                    "available": True,
                    "current": current_version,
                    "latest": latest_version
                }

        return {"available": False, "current": current_version}
    except Exception as e:
        server.logger.debug(f"检查自更新时出错: {e}")
        return {"available": False, "error": str(e)}
