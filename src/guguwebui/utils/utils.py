import copy
import importlib
import javaproperties
import json
import os
import string
import zipfile

import datetime
import secrets

import requests
import re
import time
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

from mcdreforged.plugin.meta.metadata import Metadata
from mcdreforged.api.all import RAction, RColor, PluginServerInterface, RText, RTextList, RTextBase
from pathlib import Path
from ruamel.yaml.comments import CommentedSeq
from mcstatus import JavaServer

from .constant import user_db, pwd_context, SERVER_PROPERTIES_PATH

#============================================================#
# verify password
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# hash password
def hash_password(plain_password):
    return pwd_context.hash(plain_password)
# create temp password
def create_temp_password()->str:
    characters = string.ascii_uppercase + string.digits
    temp_password = ''.join(secrets.choice(characters) for _ in range(6))
    user_db['temp'][temp_password] = str(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15))
    user_db.save()
    return temp_password
# create password
def create_user_account(user_name:str, password:str)->bool:
    if user_name not in user_db['user']:
        user_db['user'][user_name] = pwd_context.hash(password)
        user_db.save()
        return True
    return False
# change password
def change_user_account(user_name:str, old_password:str, new_password:str)->bool:
    if user_name in user_db['user'] and verify_password(old_password, user_db['user'][user_name]):
        user_db['user'][user_name] = pwd_context.hash(new_password)
        user_db.save()
        return True
    return False
# MCDR command
def create_account_command(src, ctx, host:str, port:int):
    # 检查是否为玩家发送的命令
    if hasattr(src, 'player') and src.player is not None:
        error_msg = RText("此命令只能在终端中执行！请在MCDR控制台中使用此命令。", color=RColor.red)
        src.reply(error_msg)
        return
    
    account, password = ctx['account'], ctx['password']

    # 防呆处理：自动去除可能存在的<>字符
    account = account.replace('<', '').replace('>', '')
    password = password.replace('<', '').replace('>', '')

    success = create_user_account(account, password)
    if success:
        success_msg = RTextList(
            RText("账户: ", color=RColor.green),
            RText(account, color=RColor.yellow),
            RText(" 创建成功。\n", color=RColor.green),
            RText("guguwebui 地址: ", color=RColor.blue),
            RText(f"http://{host}:{port}", color=RColor.aqua)
        )
        src.reply(success_msg)
    else:
        error_msg = RText("账户已存在！", color=RColor.red)
        src.reply(error_msg)
# MCDR command
def change_account_command(src, ctx, host:str, port:int):
    # 检查是否为玩家发送的命令
    if hasattr(src, 'player') and src.player is not None:
        error_msg = RText("此命令只能在终端中执行！请在MCDR控制台中使用此命令。", color=RColor.red)
        src.reply(error_msg)
        return
    
    account = ctx['account']
    old_password, new_password = ctx['old password'], ctx['new password']

    # 防呆处理：自动去除可能存在的<>字符
    account = account.replace('<', '').replace('>', '')
    old_password = old_password.replace('<', '').replace('>', '')
    new_password = new_password.replace('<', '').replace('>', '')

    success = change_user_account(account, old_password, new_password)
    if success:
        success_msg = RTextList(
            RText("账户: ", color=RColor.green),
            RText(account, color=RColor.yellow),
            RText(" 修改成功。\n", color=RColor.green),
            RText("guguwebui 地址: ", color=RColor.blue),
            RText(f"http://{host}:{port}", color=RColor.aqua)
        )
        src.reply(success_msg)
    else:
        error_msg = RText("用户不存在 或 密码错误！", color=RColor.red)
        src.reply(error_msg)
# MCDR command
def get_temp_password_command(src, ctx, host:str, port:int):
    # 检查是否为玩家发送的命令
    if hasattr(src, 'player') and src.player is not None:
        error_msg = RText("此命令只能在终端中执行！请在MCDR控制台中使用此命令。", color=RColor.red)
        src.reply(error_msg)
        return
    
    temp_password = create_temp_password()
    temp_msg = RTextList(
        RText("临时密码(15分钟后过期): ", color=RColor.yellow),
        RText(temp_password, color=RColor.gold),
        RText("\n", color=RColor.reset),
        RText("guguwebui 地址: ", color=RColor.blue),
        RText(f"http://{host}:{port}", color=RColor.aqua)
    )
    src.reply(temp_msg)

# 清理过期或失效的聊天验证码
def cleanup_chat_verifications():
	try:
		if 'chat_verification' not in user_db:
			return
		now = datetime.datetime.now(datetime.timezone.utc)
		codes_to_delete = []
		for code, rec in list(user_db['chat_verification'].items()):
			try:
				expire_time = datetime.datetime.fromisoformat(rec.get('expire_time', '').replace('Z', '+00:00'))
				# 过期即清理
				if now > expire_time:
					codes_to_delete.append(code)
			except Exception:
				# 解析失败也清理
				codes_to_delete.append(code)
		for code in codes_to_delete:
			try:
				del user_db['chat_verification'][code]
			except Exception:
				pass
		if codes_to_delete:
			user_db.save()
	except Exception:
		pass

# MCDR command for chat verification
def verify_chat_code_command(src, ctx):
	code = ctx['code']
	
	# 检查是否为玩家发送的命令
	if not hasattr(src, 'player') or src.player is None:
		error_msg = RText("此命令只能由玩家在游戏内使用！", color=RColor.red)
		src.reply(error_msg)
		return
	
	player_id = src.player
	
	# 先清理一次过期验证码
	cleanup_chat_verifications()
	
	# 检查验证码是否存在
	if code not in user_db['chat_verification']:
		error_msg = RTextList(
			RText("验证码 ", color=RColor.red),
			RText(code, color=RColor.yellow),
			RText(" 不存在！", color=RColor.red)
		)
		src.reply(error_msg)
		return
	
	verification = user_db['chat_verification'][code]
	
	# 检查是否已过期
	expire_time = datetime.datetime.fromisoformat(verification['expire_time'].replace('Z', '+00:00'))
	if datetime.datetime.now(datetime.timezone.utc) > expire_time:
		del user_db['chat_verification'][code]
		user_db.save()
		error_msg = RTextList(
			RText("验证码 ", color=RColor.red),
			RText(code, color=RColor.yellow),
			RText(" 已过期！", color=RColor.red)
		)
		src.reply(error_msg)
		return
	
	# 检查是否已被使用（已验证）
	if verification.get('used'):
		error_msg = RTextList(
			RText("验证码 ", color=RColor.red),
			RText(code, color=RColor.yellow),
			RText(" 已被使用！", color=RColor.red)
		)
		src.reply(error_msg)
		return
	
	# 检查是否已绑定其他玩家
	if verification['player_id'] is not None and verification['player_id'] != player_id:
		error_msg = RTextList(
			RText("验证码 ", color=RColor.red),
			RText(code, color=RColor.yellow),
			RText(" 已被玩家 ", color=RColor.red),
			RText(verification['player_id'], color=RColor.yellow),
			RText(" 使用！", color=RColor.red)
		)
		src.reply(error_msg)
		return
	
	# 绑定玩家ID到验证码，并立刻使验证码失效（不可再次用于游戏内验证）
	verification['player_id'] = player_id
	verification['used'] = True
	verification['verified_time'] = str(datetime.datetime.now(datetime.timezone.utc))
	user_db.save()
	
	success_msg = RTextList(
		RText("验证码 ", color=RColor.green),
		RText(code, color=RColor.yellow),
		RText(" 验证成功！请在聊天页设置密码完成注册。", color=RColor.green)
	)
	src.reply(success_msg)
#============================================================#
# 创建聊天消息的RText格式
def create_chat_message_rtext(player_id: str, message: str, player_uuid: str = "未知") -> RTextBase:
    """创建用于广播的 RText 聊天消息
    
    Args:
        player_id: 玩家ID
        message: 消息内容
        player_uuid: 玩家UUID
        
    Returns:
        RText 对象，可直接用于 server.broadcast
    """
    name_part = RText(player_id, color=RColor.white)
    hover_text = f"玩家: {player_id}\n来源: WebUI\nUUID: {player_uuid}\n点击快速填入 /tell 命令"
    name_part.h(hover_text)
    name_part.c(RAction.suggest_command, f"/tell {player_id} ")
    return RTextList(
        RText("<", color=RColor.white),
        name_part,
        RText("> ", color=RColor.white),
        RText(message, color=RColor.white)
    )

def create_rtext_from_data(source: str, rtext_data, player_uuid: str = "未知") -> RTextBase:
    """从RText数据创建RText对象
    
    Args:
        source: 消息来源
        rtext_data: RText数据（字典、列表或字符串）
        player_uuid: 玩家UUID
        
    Returns:
        RText 对象，可直接用于 server.broadcast
    """
    from mcdreforged.api.all import RText, RTextList, RColor, RAction
    
    # 创建插件标识部分
    name_part = RText(f"[{source}]", color=RColor.gray)
    hover_text = f"插件: {source}\n来源: 插件\nUUID: {player_uuid}"
    name_part.h(hover_text)
    
    # 解析RText数据
    if isinstance(rtext_data, dict):
        # 单个RText组件
        rtext_component = _parse_rtext_component(rtext_data)
        return RTextList(name_part, RText(" "), rtext_component)
    elif isinstance(rtext_data, list):
        # RText组件列表
        components = []
        for item in rtext_data:
            if isinstance(item, dict):
                components.append(_parse_rtext_component(item))
            else:
                components.append(RText(str(item)))
        return RTextList(name_part, RText(" "), *components)
    else:
        # 普通字符串
        return RTextList(name_part, RText(" "), RText(str(rtext_data)))

def _parse_rtext_component(component: dict) -> RTextBase:
    """解析单个RText组件
    
    Args:
        component: RText组件字典
        
    Returns:
        RText 对象
    """
    from mcdreforged.api.all import RText, RTextList, RColor, RAction, RStyle
    
    # 获取文本内容
    text = component.get('text', '')
    
    # 创建基础RText对象
    rtext = RText(text)
    
    # 设置颜色
    if 'color' in component:
        color_name = component['color']
        if hasattr(RColor, color_name):
            rtext = rtext.set_color(getattr(RColor, color_name))
    
    # 设置样式 - 使用RStyle
    styles = []
    if component.get('bold'):
        styles.append(RStyle.bold)
    if component.get('italic'):
        styles.append(RStyle.italic)
    if component.get('underlined'):
        styles.append(RStyle.underlined)
    if component.get('strikethrough'):
        styles.append(RStyle.strikethrough)
    if component.get('obfuscated'):
        styles.append(RStyle.obfuscated)
    
    if styles:
        rtext = rtext.set_styles(styles)
    
    # 设置点击事件
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
    
    # 设置悬停事件
    if 'hoverEvent' in component:
        hover_event = component['hoverEvent']
        if hover_event.get('action') == 'show_text' and 'value' in hover_event:
            rtext = rtext.h(hover_event['value'])
    
    # 处理子组件
    if 'extra' in component and isinstance(component['extra'], list):
        extra_components = []
        for extra in component['extra']:
            if isinstance(extra, dict):
                extra_components.append(_parse_rtext_component(extra))
            else:
                extra_components.append(RText(str(extra)))
        return RTextList(rtext, *extra_components)
    
    return rtext

def create_chat_status_rtext(status_type: str, message: str) -> RTextBase:
    """创建聊天状态消息的RText格式
    
    Args:
        status_type: 状态类型 ('success', 'info', 'warning', 'error')
        message: 状态消息
        
    Returns:
        RText对象
    """
    color_map = {
        'success': RColor.green,
        'info': RColor.blue, 
        'warning': RColor.yellow,
        'error': RColor.red
    }
    
    color = color_map.get(status_type, RColor.white)
    return RText(message, color=color)

def create_chat_logger_status_rtext(action: str, success: bool = True, player_name: str = None, message_content: str = None) -> RTextBase:
    """创建聊天日志记录器状态消息的RText格式
    
    Args:
        action: 操作类型 ('init', 'clear', 'record')
        success: 是否成功
        player_name: 玩家名称（用于record操作）
        message_content: 消息内容（用于record操作）
        
    Returns:
        RText对象
    """
    if action == 'init':
        if success:
            return RText("聊天消息监听器初始化成功", color=RColor.green)
        else:
            return RText("聊天消息监听器初始化失败", color=RColor.red)
    elif action == 'clear':
        if success:
            return RText("聊天消息已清空", color=RColor.green)
        else:
            return RText("聊天消息清空失败", color=RColor.red)
    elif action == 'record':
        if success and player_name and message_content:
            return RTextList(
                RText("记录玩家 ", color=RColor.green),
                RText(player_name, color=RColor.yellow),
                RText(" 的聊天消息: ", color=RColor.green),
                RText(message_content, color=RColor.white)
            )
        elif success:
            return RText("聊天消息记录成功", color=RColor.green)
        else:
            return RText("聊天消息记录失败", color=RColor.red)
    else:
        return RText(f"聊天日志操作: {action}", color=RColor.blue)

#============================================================#
# Find all configs for a plugin
def find_plugin_config_paths(plugin_id:str)->list:
    MCDR_plugin_folder = Path("./config") / plugin_id # config under ./config/plugin_id/*
    single_file_path = Path("./config") / plugin_id # config under ./config

    response = [] # list[config_path]
    config_suffix = [".json", ".yml", ".yaml"]
    single_file_paths = [single_file_path.with_suffix(suffix) for suffix in config_suffix]

    # Configs in ./config/plugin_id/
    if Path(MCDR_plugin_folder).exists():
        # 直接使用存在的目录
        response += [file for file in Path(MCDR_plugin_folder).rglob("*") if file.suffix.lower() in config_suffix]
    else:
        # 查找不区分大小写的目录
        config_dir = Path("./config")
        if config_dir.exists():
            for item in config_dir.iterdir():
                if item.is_dir() and item.name.lower() == plugin_id.lower():
                    response += [file for file in item.rglob("*") if file.suffix.lower() in config_suffix]
    
    # Configs in ./config/
    for file_path in single_file_paths:
        if file_path.exists():
            response.append(file_path)
        else:
            # 查找不区分大小写的文件
            parent_dir = file_path.parent
            if parent_dir.exists():
                for item in parent_dir.iterdir():
                    if item.is_file() and item.stem.lower() == plugin_id.lower() and item.suffix.lower() in config_suffix:
                        response.append(item)

    # filter out translation files
    response = [str(i) for i in response if not Path(i).stem.lower().endswith("_lang")]

    return response


# loading all the plugin information
def load_plugin_info(server_interface:PluginServerInterface):
    loaded_metadata = server_interface.get_all_metadata() #{plugin_id: metadata}
    disabled_plugins = server_interface.get_disabled_plugin_list()
    unloaded_plugins = server_interface.get_unloaded_plugin_list()

    unloaded_metadata = {}

    # extract metadata by reading files
    for plugin_path in disabled_plugins + unloaded_plugins:
        # 只处理.py和.mcdr文件
        if not (plugin_path.endswith('.py') or plugin_path.endswith('.mcdr')):
            continue
        
        # extract metadata
        metadata = extract_metadata(plugin_path)

        if not metadata: continue # cannot find the metadata

        if metadata['id'] in unloaded_metadata \
            and metadata['version'] <= unloaded_metadata[metadata["id"]]['version']:
            continue # not the highest version of the plugin

        metadata['path'] = plugin_path
        unloaded_metadata[metadata["id"]] = metadata

    return loaded_metadata, unloaded_metadata, unloaded_plugins, disabled_plugins


# Get gugu plugins metadata
def get_gugubot_plugins_info(server_interface:PluginServerInterface):
    target_plugin = ["player_ip_logger", "online_player_api", "gugubot", "cq_qq_api", "guguwebui"]
    loaded_metadata, unloaded_metadata, unloaded_plugins, disabled_plugins = load_plugin_info(server_interface)

    respond = []
    for plugin_name in target_plugin:
        if plugin_name in loaded_metadata: # loaded
            plugin_metadata = loaded_metadata[plugin_name]

        elif plugin_name in unloaded_metadata: # unloaded or disabled
            plugin_metadata = unloaded_metadata.get(plugin_name)

        else: continue # uninstall -> skip

        if not isinstance(plugin_metadata, Metadata): # convert dict to Metadata
            plugin_metadata = Metadata(plugin_metadata)

        respond.append({
            "id": plugin_name, 
            "version": str(plugin_metadata.version),
            "name": str(plugin_metadata.name) if plugin_metadata else plugin_name, 
            "status": "loaded" if plugin_name in loaded_metadata else "unloaded" if plugin_name in unloaded_metadata else "disabled",
            "path": plugin_name if plugin_name in unloaded_plugins + disabled_plugins else ""
        })
        
        # uninstall -> no return
    
    return respond

# get plugins' metadata 
def get_plugins_info(server_interface, detail=False):
    ignore_plugin = ["mcdreforged", "python"]
    main_page_ignore = ['gugubot', "cq_qq_api", "player_ip_logger", "online_player_api", "guguwebui"]
    loaded_metadata, unloaded_metadata, unloaded_plugins, disabled_plugins = load_plugin_info(server_interface)

    # 获取插件版本数据
    def fetch_plugin_versions():
        try:
            # 创建PIMHelper实例来获取插件元数据
            from guguwebui.utils.PIM import PIMHelper
            
            class DummySource:
                def reply(self, message):
                    pass
                    
                def get_server(self):
                    return server_interface
            
            # 初始化PIMHelper并获取插件目录元数据
            pim_helper = PIMHelper(server_interface)
            dummy_source = DummySource()
            cata_meta = pim_helper.get_cata_meta(dummy_source)
            
            # 获取所有插件数据并提取最新版本号
            plugins = cata_meta.get_plugins()
            return {plugin_id: plugin_data.latest_version for plugin_id, plugin_data in plugins.items()}
        except Exception as e:
            # print(f"Error fetching plugin versions from PIM: {e}")
            return {}

    # 获取插件版本
    plugin_versions = fetch_plugin_versions()

    respond = []

    # 合并已加载和未加载的插件元数据
    merged_metadata = copy.deepcopy(unloaded_metadata)
    merged_metadata.update(loaded_metadata)

    for plugin_name, plugin_metadata in merged_metadata.items():
        if plugin_name in ignore_plugin:
            continue  # 忽略 mcdr 和 python

        try:
            if not isinstance(plugin_metadata, Metadata):  # 将 dict 转换为 Metadata 对象
                plugin_metadata = Metadata(plugin_metadata)

            # 从API获取的最新版本号
            latest_version = plugin_versions.get(plugin_name, None)
            
            # 格式化版本号，去除插件ID前缀和v前缀
            if latest_version and ("-v" in latest_version or "-" in latest_version):
                version_parts = latest_version.split("-v")
                if len(version_parts) > 1:
                    latest_version = version_parts[1]  # 使用-v分隔的后半部分
                else:
                    # 尝试使用'-'分隔并保留最后一部分
                    version_parts = latest_version.split("-")
                    if len(version_parts) > 1:
                        latest_version = version_parts[-1]
                        # 如果最后一部分以'v'开头，去掉'v'
                        if latest_version.startswith("v"):
                            latest_version = latest_version[1:]

            if not detail and plugin_name not in main_page_ignore:  # 主页面插件信息
                respond.append({
                    "id": plugin_name, 
                    "name": str(plugin_metadata.name) if plugin_metadata else plugin_name,
                    "status": "loaded" if plugin_name in loaded_metadata else "disabled" if plugin_name in disabled_plugins else "unloaded",
                    "path": plugin_name if plugin_name in unloaded_plugins + disabled_plugins else ""
                })
            elif detail:  # 插件列表详细信息
                # 构造完整的描述：当为 dict 时返回包含多语言的完整对象；否则返回字符串
                try:
                    raw_desc = plugin_metadata.description
                    if isinstance(raw_desc, dict):
                        # 规范化 key：全部转为小写并用下划线
                        full_desc = {}
                        for k, v in raw_desc.items():
                            if not isinstance(v, str):
                                continue
                            key_norm = str(k).lower().replace('-', '_')
                            full_desc[key_norm] = v
                        description = full_desc
                    else:
                        description = str(raw_desc) if raw_desc is not None else ""
                except Exception:
                    description = "该插件数据异常"

                # 处理作者信息
                try:
                    author_info = plugin_metadata.author
                    if isinstance(author_info, list):
                        # 处理新的作者信息格式
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
                    "version_latest": str(latest_version) if latest_version else str(plugin_metadata.version) if hasattr(plugin_metadata, 'version') else "未知",
                    "status": "loaded" if str(plugin_metadata.id) in loaded_metadata else "disabled" if str(plugin_metadata.id) in disabled_plugins else "unloaded",
                    "path": plugin_name if plugin_name in unloaded_plugins + disabled_plugins else "",
                    "config_file": bool(find_plugin_config_paths(str(plugin_metadata.id))) if hasattr(plugin_metadata, 'id') else False,
                    "repository": None  # 初始化仓库信息为None，稍后通过API获取
                })
        except Exception as e:
            # 如果插件信息解析失败，添加基本信息
            respond.append({
                "id": plugin_name,
                "name": plugin_name,
                "description": "该插件数据异常",
                "author": "未知",
                "github": "",
                "version": "未知",
                "version_latest": "未知",
                "status": "loaded" if plugin_name in loaded_metadata else "disabled" if plugin_name in disabled_plugins else "unloaded",
                "path": plugin_name if plugin_name in unloaded_plugins + disabled_plugins else "",
                "config_file": False
            })

    return respond
#============================================================#
# loading metadata
def extract_metadata(plugin_path):
    if os.path.isdir(plugin_path):  # folder plugin
        return extract_folder_plugin_metadata(plugin_path)
    elif zipfile.is_zipfile(plugin_path):  # MCDR zipped plugin
        return extract_zip_plugin_metadata(plugin_path)
    elif os.path.isfile(plugin_path):  # single-py plugin
        return extract_single_file_plugin_metadata(plugin_path) 
    else:
        return None
    
def extract_single_file_plugin_metadata(plugin_file_path):
    # import the file
    module_name = os.path.basename(plugin_file_path).replace('.py', '')
    spec = importlib.util.spec_from_file_location(module_name, plugin_file_path)
    plugin_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin_module)

    # get the metadata
    metadata = getattr(plugin_module, 'PLUGIN_METADATA', None)

    return metadata if metadata else None

def extract_folder_plugin_metadata(plugin_path):
    # find mcdreforged.plugin.json in the folder
    for root, dirs, files in os.walk(plugin_path):
        for file in files:
            if file == 'mcdreforged.plugin.json': 
                with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                    return json.load(f)

def extract_zip_plugin_metadata(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # list all the file in zipped file
        for file in zip_ref.namelist():
            if file.endswith('mcdreforged.plugin.json'):
                with zip_ref.open(file) as f:
                    return json.load(f)
#============================================================#
# extract comments from ruamel.yaml's Comment object
def extract_comment(comment_object)->str:
    if not comment_object:
        return ""
    # Obtain first available comment
    comment = next((c[0].value if isinstance(c, list) and c else c.value for c in comment_object if c), "")
    # remove # & extract space
    comment = comment.split("\n", 1)[0].replace("#", "").strip()
    # segment by "::"
    return comment.split("::", 1) if "::" in comment else comment

# Read comment from yaml file
def get_comment(config:dict)->dict:
    name_map = {}

    for k,v in config.items(): 
        comment = extract_comment(config.ca.items.get(k))

        if comment: # save when it has comment
            name_map[k] = comment

        if isinstance(v,dict): # recurrsion for inner dict
            name_map.update(get_comment(v))

    return name_map

#============================================================#
# i18n helpers for YAML comment parsing
import re
from collections import OrderedDict

def _normalize_lang_code(raw_code: str) -> str:
    """Normalize language code to common forms like zh-CN / en-US.
    Fallback: keep original if unrecognized.
    """
    code = (raw_code or "").strip().strip("[] ")
    if not code:
        return "zh-CN"
    base = code.replace("_", "-")
    lower = base.lower()
    if lower in ("zh", "zh-cn", "zh_hans"):
        return "zh-CN"
    if lower in ("en", "en-us"):
        return "en-US"
    if "-" in base:
        parts = base.split("-", 1)
        return f"{parts[0].lower()}-{parts[1].upper()}"
    return base

def _parse_inline_and_prev_comments(file_text: str):
    """解析 YAML 文件中的行内注释与前一行普通注释，支持子项并生成完整键路径。

    返回: { full.key.path: comment_text }
    规则：
    - 优先使用同行注释（key: value # comment）
    - 否则使用与键同缩进层级、紧邻上一行的普通注释（排除语言块头与管道格式）
    - 根据缩进维护父子关系，生成如 command.ban_word 的完整键
    """
    result: dict[str, str] = {}
    # (indent_level, key_name) 栈
    indent_stack: list[tuple[int, str]] = []
    # 记录“上一行普通注释”，按缩进层级区分
    last_plain_comment_by_indent: dict[int, str] = {}

    for raw in file_text.splitlines():
        line = raw.rstrip("\n\r")
        if not line.strip():
            # 空行重置上一行注释，避免跨空行误关联
            last_plain_comment_by_indent.clear()
            continue

        indent = len(line) - len(line.lstrip())  # 包含空格与\t
        stripped = line.strip()

        # 注释行
        if stripped.startswith("#"):
            content = stripped[1:].strip()
            # 语言块头或语言定义行不计入普通注释
            if content.startswith("[") and content.endswith("]"):
                last_plain_comment_by_indent.pop(indent, None)
                continue
            if "|" in content:
                # 形如 key | name::desc
                continue
            last_plain_comment_by_indent[indent] = content
            continue

        # YAML 键行：key: value（value 可为空）
        logical = line.lstrip()
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*?)\s*(#\s*(.*))?$", logical)
        if not m:
            # 不是键定义，清空普通注释缓存，避免串行
            last_plain_comment_by_indent.clear()
            continue

        key = m.group(1)
        inline_comment = (m.group(4) or "").strip()

        # 维护缩进栈：当前缩进小于等于栈顶则出栈
        while indent_stack and indent_stack[-1][0] >= indent:
            indent_stack.pop()
        indent_stack.append((indent, key))

        full_key = ".".join(k for _, k in indent_stack)

        if inline_comment:
            result[full_key] = inline_comment
            # 使用了行内注释，清除此缩进上的上一行注释
            last_plain_comment_by_indent.pop(indent, None)
        else:
            prev = last_plain_comment_by_indent.pop(indent, None)
            if prev:
                result[full_key] = prev.strip()

    return result

def _parse_language_blocks(file_text: str):
    """Parse blocks like:
    # [en-US]
    # key | name::desc
    返回：(语言顺序列表, 语言->(key->[name,desc?]))
    """
    lang_order = []
    lang_map = {}
    current_lang = None
    for raw in file_text.splitlines():
        line = raw.rstrip("\n\r")
        stripped = line.strip()
        if stripped.startswith("#"):
            content = stripped[1:].strip()
            # 语言块头
            if content.startswith("[") and content.endswith("]") and len(content) >= 3:
                current_lang = _normalize_lang_code(content)
                if current_lang not in lang_map:
                    lang_map[current_lang] = {}
                    lang_order.append(current_lang)
                continue
            # 管道行：key | name::desc
            if current_lang and "|" in content:
                try:
                    key_part, right = [i.strip() for i in content.split("|", 1)]
                    if not key_part:
                        continue
                    # 右侧 name::desc 或仅 name
                    if "::" in right:
                        name_part, desc_part = [i.strip() for i in right.split("::", 1)]
                        value = [name_part, desc_part]
                    else:
                        value = [right]
                    lang_map[current_lang][key_part] = value
                except Exception:
                    continue
    return lang_order, lang_map

def _nest_translation_map(flat_map: dict) -> dict:
    """将扁平 full.key 映射转换为带 children 容器的嵌套结构，避免与实际键名冲突。

    输出节点结构：
    {
      key: {
        "name": str|None,
        "desc": str|None,
        "children": { sub_key: same-structure }
      }
    }
    """
    nested: dict = {}
    for full_key, meta in (flat_map or {}).items():
        if not isinstance(full_key, str):
            continue
        parts = [p for p in full_key.split(".") if p]
        if not parts:
            continue
        cur = nested
        for i, part in enumerate(parts):
            if part not in cur or not isinstance(cur.get(part), dict):
                cur[part] = {"name": None, "desc": None, "children": {}}
            # 最末级设置 name/desc
            if i == len(parts) - 1 and isinstance(meta, dict):
                if meta.get("name") is not None:
                    cur[part]["name"] = meta.get("name")
                if "desc" in meta:
                    cur[part]["desc"] = meta.get("desc")
            # 下降到 children 容器
            next_children = cur[part].get("children")
            if not isinstance(next_children, dict):
                cur[part]["children"] = {}
                next_children = cur[part]["children"]
            cur = next_children
    return nested

def build_yaml_i18n_translations(yaml_config: dict, file_text: str) -> dict:
    """根据两种方案提取多语言注释并返回统一结构。

    返回结构：
    {
      "default": "zh-CN",
      "translations": {
        "zh-CN": { key: {"name": str, "desc": str|null} },
        "en-US": { ... }
      }
    }
    规则：
    - 优先使用语言块（方案二）；
    - 方案一回退：若语言块缺失或某个键缺失，则使用同行注释或前一行注释；
    - default 语言优先使用配置中的 language 值，其次使用第一个语言块，否则 zh-CN。
    """
    file_text = file_text or ""
    # 语言块解析
    lang_order, lang_block_map = _parse_language_blocks(file_text)

    # 解析同行/上一行注释（方案一）
    inline_map = _parse_inline_and_prev_comments(file_text)

    # 从配置里识别默认语言
    default_lang = None
    try:
        conf_lang = None
        if isinstance(yaml_config, dict):
            conf_lang = yaml_config.get("language")
        if isinstance(conf_lang, str) and conf_lang.strip():
            default_lang = _normalize_lang_code(conf_lang)
    except Exception:
        pass
    if not default_lang:
        default_lang = lang_order[0] if lang_order else "zh-CN"

    # 构造 translations（扁平）
    translations = OrderedDict()
    # 先填充语言块
    for lang in lang_order:
        translations[lang] = {}
        for key, arr in lang_block_map.get(lang, {}).items():
            name = None
            desc = None
            if isinstance(arr, list):
                if len(arr) >= 1:
                    name = str(arr[0])
                if len(arr) >= 2:
                    desc = str(arr[1])
            elif isinstance(arr, str):
                name = arr
            if name is not None:
                translations[lang][key] = {"name": name, "desc": desc}

    # 使用方案一注释构建 zh-CN（扁平）。避免将中文注释混入默认语言（如 en-US）。
    zh_cn_key = "zh-CN"
    if zh_cn_key not in translations:
        translations[zh_cn_key] = {}
    for key, text in inline_map.items():
        if key not in translations[zh_cn_key]:
            if "::" in text:
                name_part, desc_part = [i.strip() for i in text.split("::", 1)]
                translations[zh_cn_key][key] = {"name": name_part, "desc": desc_part}
            else:
                translations[zh_cn_key][key] = {"name": text.strip(), "desc": None}

    # 将每种语言的扁平键转换为嵌套结构
    for lang in list(translations.keys()):
        translations[lang] = _nest_translation_map(translations[lang])

    return {"default": default_lang, "translations": translations}


def build_json_i18n_translations(json_obj: dict) -> dict:
    """将 JSON 多语言结构转换为统一结构。

    接受形如：
    {
      "zh_cn": { key: [name, desc], ... },
      "en_us": { ... }
    }

    返回：
    {
      "default": "zh-CN",
      "translations": {
        "zh-CN": { key: {"name": str, "desc": str|null} },
        "en-US": { ... }
      }
    }
    """
    if not isinstance(json_obj, dict):
        return {"default": "zh-CN", "translations": {}}

    def normalize_candidates(lang_code: str) -> list[str]:
        base = _normalize_lang_code(lang_code)
        a, b = (base.split('-', 1) + [""])[:2]
        cands = set([
            base,  # zh-CN
            base.lower(),  # zh-cn
            f"{a.lower()}_{b.lower()}",  # zh_cn
            a.lower(),  # zh
        ])
        return list(cands)

    # 构建 translations（扁平）
    translations = OrderedDict()
    avail_keys = set(json_obj.keys())
    for target in ["zh-CN", "en-US"]:
        cands = normalize_candidates(target)
        picked = None
        for c in cands:
            if c in json_obj:
                picked = c
                break
        if picked and isinstance(json_obj[picked], dict):
            translations[target] = {}
            for k, v in json_obj[picked].items():
                if isinstance(v, list) and len(v) >= 1:
                    name = str(v[0]) if v[0] is not None else ""
                    desc = str(v[1]) if len(v) >= 2 and v[1] is not None else None
                    translations[target][k] = {"name": name, "desc": desc}
                elif isinstance(v, dict):
                    name = str(v.get("name", ""))
                    desc_val = v.get("desc", None)
                    desc = str(desc_val) if desc_val is not None else None
                    translations[target][k] = {"name": name, "desc": desc}
                elif isinstance(v, str):
                    translations[target][k] = {"name": v, "desc": None}

    # 如果没有匹配到预期语言，但存在其它键，则收集一个作为默认
    if not translations and avail_keys:
        any_key = next(iter(avail_keys))
        normalized = _normalize_lang_code(any_key)
        inner = json_obj.get(any_key, {})
        translations[normalized] = {}
        if isinstance(inner, dict):
            for k, v in inner.items():
                if isinstance(v, list) and len(v) >= 1:
                    name = str(v[0]) if v[0] is not None else ""
                    desc = str(v[1]) if len(v) >= 2 and v[1] is not None else None
                    translations[normalized][k] = {"name": name, "desc": desc}
                elif isinstance(v, dict):
                    name = str(v.get("name", ""))
                    desc_val = v.get("desc", None)
                    desc = str(desc_val) if desc_val is not None else None
                    translations[normalized][k] = {"name": name, "desc": desc}
                elif isinstance(v, str):
                    translations[normalized][k] = {"name": v, "desc": None}

    # 将扁平结构转换为嵌套结构
    for lang in list(translations.keys()):
        translations[lang] = _nest_translation_map(translations[lang])

    default_lang = "zh-CN" if "zh-CN" in translations else (next(iter(translations.keys())) if translations else "zh-CN")
    return {"default": default_lang, "translations": translations}
#============================================================#
# read server status

# Get server port
def get_server_port()->int:
    with open(SERVER_PROPERTIES_PATH, "r", encoding="UTF-8") as f:
        data = javaproperties.load(f)
    return int( data["server-port"] )

# Get java MC status
# original code from https://github.com/Spark-Code-China/MC-Server-Info
def get_java_server_info():
    temp_ip = "127.0.0.1"
    port = get_server_port()
    result_dict = {}
    try:
        server = JavaServer.lookup(f"{temp_ip}:{port}")
        status = server.status()
        if status:
            result_dict["server_version"] = status.version.name
            result_dict["server_player_count"] = status.players.online
            result_dict["server_maxinum_player_count"] = status.players.max
        return result_dict
    except Exception as e:
        return result_dict

 
#============================================================#
# move file from MCDR package
def __copyFile(server, path, target_path): 
    # 对 custom 目录默认不覆盖，但对 server_lang.json 例外：始终覆盖为最新
    target_path = Path(target_path)
    if "custom" in target_path.parts and target_path.exists() and target_path.name != "server_lang.json":
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with server.open_bundled_file(path) as file_handler: # extract from MCDR file
        message = file_handler.read()
    with open(target_path, 'wb') as f:                   # copy to target_path
        f.write(message)

def __copyFolder(server, folder_path, target_folder):
    """
    从插件内部提取一个文件夹到指定目录
    
    :param server: PluginServerInterface实例
    :param folder_path: 插件内的文件夹路径
    :param target_folder: 目标目录路径
    """
    # 确保目标目录存在
    target_folder = Path(target_folder)
    target_folder.mkdir(parents=True, exist_ok=True)
    
    try:
        # 首先尝试作为文件处理，如果成功，则说明这是一个文件而不是文件夹
        try:
            with server.open_bundled_file(folder_path) as _:
                # 如果能打开，说明是文件，直接复制
                __copyFile(server, folder_path, target_folder)
                return True
        except FileNotFoundError:
            # 不是文件，继续作为文件夹处理
            pass
        except Exception as e:
            # 其他错误，记录并继续
            server.logger.debug(f"尝试作为文件处理'{folder_path}'时出错: {e}")
            pass

        # 尝试使用插件的内部方法列出文件夹内容
        items = []
        try:
            # 使用__plugin是插件内部属性，可能不稳定，但是尝试直接访问
            items = server._PluginServerInterface__plugin.list_directory(folder_path)
        except Exception:
            # 如果上面的方法失败，尝试其他方法
            # 直接使用MultiFilePlugin.list_directory方法
            from mcdreforged.plugin.type.multi_file_plugin import MultiFilePlugin
            if isinstance(server._PluginServerInterface__plugin, MultiFilePlugin):
                items = server._PluginServerInterface__plugin.list_directory(folder_path)
        
        if not items:
            server.logger.warning(f"无法获取文件夹 '{folder_path}' 的内容列表")
            return False
            
        for item in items:
            # 忽略__pycache__文件夹、utils文件夹和.py文件
            if item == "__pycache__" or item == "utils" or item.endswith(".py"):
                server.logger.debug(f"忽略文件/文件夹: {item}")
                continue
                
            # 构建插件内的完整路径
            plugin_item_path = f"{folder_path}/{item}"
            # 构建目标路径
            target_item_path = target_folder / item
            
            # 尝试判断是文件还是文件夹
            try:
                # 尝试作为文件打开
                with server.open_bundled_file(plugin_item_path) as _:
                    # 如果能打开，说明是文件，直接复制
                    __copyFile(server, plugin_item_path, target_item_path)
            except Exception:
                # 如果打开失败，可能是文件夹，尝试递归复制
                __copyFolder(server, plugin_item_path, target_item_path)
                
        server.logger.debug(f"成功从插件提取文件夹 '{folder_path}' 到 '{target_folder}'")
        return True
    except Exception as e:
        server.logger.error(f"提取插件文件夹 '{folder_path}' 时出错: {e}")
        return False
        
def amount_static_files(server):
    # 创建主目录
    os.makedirs('./guguwebui_static', exist_ok=True)
    
    # 使用新的文件夹复制函数来复制各个目录
    success = True
    # 复制各个子目录（新增 lang 用于前端多语言）
    for folder in ['src', 'css', 'js', 'templates', 'custom', 'lang']:
        if not __copyFolder(server, f'guguwebui/{folder}', f'./guguwebui_static/{folder}'):
            success = False
            server.logger.warning(f"复制 'guguwebui/{folder}' 目录失败")
    
    if success:
        server.logger.debug("成功复制所有guguwebui目录")
        return
    
    # 如果文件夹复制失败，退回到单文件复制方式
    server.logger.warning("部分文件夹复制失败")

# 检查是否存在旧配置，并自动继承旧的deepseek_api_key和deepseek_model参数
def migrate_old_config():
    try:
        plugin_config_dir = Path("./config") / "guguwebui"
        config_path = plugin_config_dir / "config.json"
        
        # 如果存在旧配置文件
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                old_config = json.load(f)
                
            # 检查是否存在旧的deepseek参数
            need_save = False
            
            # 如果存在旧的deepseek_api_key参数且ai_api_key为空
            if "deepseek_api_key" in old_config and old_config["deepseek_api_key"] and not old_config.get("ai_api_key"):
                old_config["ai_api_key"] = old_config["deepseek_api_key"]
                need_save = True
                
            # 如果存在旧的deepseek_model参数且ai_model为空
            if "deepseek_model" in old_config and old_config["deepseek_model"] and not old_config.get("ai_model"):
                old_config["ai_model"] = old_config["deepseek_model"]
                need_save = True
                
            # 删除旧参数
            if "deepseek_api_key" in old_config:
                del old_config["deepseek_api_key"]
                need_save = True
                
            if "deepseek_model" in old_config:
                del old_config["deepseek_model"]
                need_save = True
                
            # 如果有变更，保存配置
            if need_save:
                # 确保配置目录存在
                plugin_config_dir.mkdir(parents=True, exist_ok=True)
                
                # 保存更新后的配置
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(old_config, f, ensure_ascii=False, indent=4)
    except Exception as e:
        pass

#============================================================#

def get_minecraft_path(server_interface=None, path_type="working_directory"):
    """
    获取Minecraft服务器相关路径
    基于MCDR配置中的working_directory值
    
    Args:
        server_interface: MCDR服务器接口，用于获取配置
        path_type: 路径类型，支持以下值：
            - "working_directory": 服务器工作目录
            - "logs": 日志目录
            - "usercache": usercache.json文件路径
            - "server_jar": 服务器jar文件目录
            - "worlds": 世界文件夹目录
            - "plugins": 插件目录（如果有）
            - "mods": 模组目录（如果有）
        
    Returns:
        str: 请求的路径
    """
    try:
        import os
        from ruamel.yaml import YAML
        
        # 尝试通过服务器接口获取配置
        working_directory = None
        if server_interface:
            try:
                # 尝试获取MCDR配置中的工作目录
                mcdr_config = server_interface.get_mcdr_config()
                if hasattr(mcdr_config, 'working_directory'):
                    working_directory = mcdr_config.working_directory
            except:
                pass
        
        # 如果无法通过接口获取，尝试读取配置文件
        if not working_directory:
            # 尝试读取MCDR的配置文件
            mcdr_config_path = "config.yml"
            if not os.path.exists(mcdr_config_path):
                # 如果找不到配置文件，返回默认路径
                working_directory = "server"
            else:
                # 读取配置文件
                yaml = YAML()
                with open(mcdr_config_path, 'r', encoding='utf-8') as f:
                    config = yaml.load(f)
                
                # 获取工作目录
                working_directory = config.get('working_directory', 'server')
        
        # 根据请求的路径类型返回相应的路径
        if path_type == "working_directory":
            return working_directory
        elif path_type == "logs":
            return os.path.join(working_directory, "logs")
        elif path_type == "usercache":
            return os.path.join(working_directory, "usercache.json")
        elif path_type == "server_jar":
            return working_directory  # 服务器jar通常在根目录
        elif path_type == "worlds":
            return os.path.join(working_directory, "worlds")
        elif path_type == "plugins":
            return os.path.join(working_directory, "plugins")
        elif path_type == "mods":
            return os.path.join(working_directory, "mods")
        else:
            # 默认返回工作目录
            return working_directory
            
    except Exception as e:
        # 出错时返回默认路径
        if path_type == "working_directory":
            return "server"
        elif path_type == "logs":
            return "server/logs"
        elif path_type == "usercache":
            return "server/usercache.json"
        elif path_type == "server_jar":
            return "server"
        elif path_type == "worlds":
            return "server/worlds"
        elif path_type == "plugins":
            return "server/plugins"
        elif path_type == "mods":
            return "server/mods"
        else:
            return "server"

#============================================================#

def get_player_uuid(player_name, server_interface=None, use_api=True):
    """
    获取指定玩家的UUID
    
    Args:
        player_name: 玩家名称
        server_interface: MCDR服务器接口，用于获取配置
        use_api: 是否使用Mojang API在线查询（如果本地查询失败）
        
    Returns:
        str: 玩家的UUID，如果获取失败返回None
    """
    try:
        import json
        import requests
        from pathlib import Path
        
        # 首先尝试从本地usercache.json读取
        try:
            usercache_path = Path(get_minecraft_path(server_interface, "usercache"))
            if usercache_path.exists():
                with open(usercache_path, 'r', encoding='utf-8') as f:
                    usercache_data = json.load(f)
                
                # 在usercache中查找玩家
                for entry in usercache_data:
                    if entry.get('name') == player_name:
                        uuid = entry.get('uuid')
                        if uuid:
                            # 格式化UUID，添加连字符
                            return format_uuid(uuid)
        except Exception as e:
            # 本地查询失败，记录调试信息
            if server_interface:
                server_interface.logger.debug(f"从usercache.json获取UUID失败: {e}")
        
        # 如果本地查询失败且允许使用API，尝试在线查询
        if use_api:
            try:
                # 使用Mojang API查询
                api_url = f"https://api.mojang.com/users/profiles/minecraft/{player_name}"
                response = requests.get(api_url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    uuid = data.get('id')
                    if uuid:
                        # 格式化UUID，添加连字符
                        return format_uuid(uuid)
                elif response.status_code == 404:
                    # 玩家不存在
                    if server_interface:
                        server_interface.logger.debug(f"玩家 {player_name} 不存在")
                    return None
                else:
                    # API请求失败
                    if server_interface:
                        server_interface.logger.debug(f"Mojang API请求失败: {response.status_code}")
                    
            except requests.exceptions.Timeout:
                if server_interface:
                    server_interface.logger.debug(f"Mojang API请求超时")
            except Exception as e:
                if server_interface:
                    server_interface.logger.debug(f"Mojang API查询失败: {e}")
        
        # 所有方法都失败了
        return None
        
    except Exception as e:
        if server_interface:
            server_interface.logger.error(f"获取玩家UUID时发生错误: {e}")
        return None


def format_uuid(uuid_string):
    """
    格式化UUID字符串，添加连字符
    
    Args:
        uuid_string: 原始UUID字符串（32位无连字符）
        
    Returns:
        str: 格式化后的UUID字符串（带连字符）
    """
    try:
        # 移除可能存在的连字符
        uuid_clean = uuid_string.replace('-', '')
        
        # 检查是否为有效的32位十六进制字符串
        if len(uuid_clean) == 32 and all(c in '0123456789abcdefABCDEF' for c in uuid_clean):
            # 添加连字符：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
            formatted_uuid = f"{uuid_clean[:8]}-{uuid_clean[8:12]}-{uuid_clean[12:16]}-{uuid_clean[16:20]}-{uuid_clean[20:32]}"
            return formatted_uuid.lower()  # 转换为小写
        
        # 如果已经是格式化后的UUID，直接返回
        if len(uuid_string) == 36 and uuid_string.count('-') == 4:
            return uuid_string.lower()
        
        # 无效格式，返回原字符串
        return uuid_string
        
    except Exception:
        # 格式化失败，返回原字符串
        return uuid_string


def get_player_info(player_name, server_interface=None, include_uuid=True):
    """
    获取玩家信息，包括UUID和在线状态
    
    Args:
        player_name: 玩家名称
        server_interface: MCDR服务器接口
        include_uuid: 是否包含UUID信息
        
    Returns:
        dict: 玩家信息字典，包含以下字段：
            - name: 玩家名称
            - uuid: 玩家UUID（如果include_uuid为True）
            - online: 是否在线
            - last_seen: 最后在线时间（如果可用）
    """
    try:
        player_info = {
            'name': player_name,
            'online': False,
            'last_seen': None
        }
        
        # 获取UUID
        if include_uuid:
            uuid = get_player_uuid(player_name, server_interface)
            player_info['uuid'] = uuid
        
        # 检查在线状态
        if server_interface:
            try:
                # 尝试获取玩家信息
                player = server_interface.get_player_info(player_name)
                if player:
                    player_info['online'] = True
                    # 如果有更多信息，可以在这里添加
            except:
                pass
        
        # 尝试从usercache.json获取最后在线时间
        try:
            usercache_path = Path(get_minecraft_path(server_interface, "usercache"))
            if usercache_path.exists():
                with open(usercache_path, 'r', encoding='utf-8') as f:
                    usercache_data = json.load(f)
                
                for entry in usercache_data:
                    if entry.get('name') == player_name:
                        expires_on = entry.get('expiresOn')
                        if expires_on:
                            player_info['last_seen'] = expires_on
                        break
        except:
            pass
        
        return player_info
        
    except Exception as e:
        if server_interface:
            server_interface.logger.error(f"获取玩家信息时发生错误: {e}")
        return {'name': player_name, 'error': str(e)}

def is_player(name: str, server_interface=None) -> bool:
    """
    检查是否是真实玩家（多用于假人判断）
    
    Args:
        name: 玩家名称
        server_interface: MCDR服务器接口
        
    Returns:
        bool: 如果玩家存在记录返回True，否则返回False
    """
    try:
        if not server_interface:
            return True  # 如果没有服务器接口，默认返回True
        
        # 检查player_ip_logger插件是否存在
        loaded_metadata, _, _, _ = load_plugin_info(server_interface)
        
        if "player_ip_logger" not in loaded_metadata:
            # 插件不存在，默认返回True
            return True
        
        # 插件存在，尝试调用其is_player方法
        try:
            # 通过MCDR的插件管理器获取插件实例
            plugin_instance = server_interface.get_plugin_instance("player_ip_logger")
            if plugin_instance and hasattr(plugin_instance, 'is_player'):
                return plugin_instance.is_player(name)
            else:
                return True
        except Exception as e:
            if server_interface:
                server_interface.logger.debug(f"调用player_ip_logger.is_player失败: {e}")
            return True
            
    except Exception as e:
        if server_interface:
            server_interface.logger.debug(f"is_player检查失败: {e}")
        return True  # 出错时默认返回True，避免误判

def get_bot_list(server_interface=None) -> list:
    """
    获取假人列表
    
    Args:
        server_interface: MCDR服务器接口
        
    Returns:
        list: 假人名称列表
    """
    try:
        if not server_interface:
            return []
        
        # 获取在线玩家列表
        online_players = set()
        try:
            # 优先通过RCON获取具体在线玩家列表
            if hasattr(server_interface, "is_rcon_running") and server_interface.is_rcon_running():
                feedback = server_interface.rcon_query("list")
                if isinstance(feedback, str) and ":" in feedback:
                    names_part = feedback.split(":", 1)[1].strip()
                    if names_part:
                        for name in [n.strip() for n in names_part.split(",") if n.strip()]:
                            online_players.add(name)
        except Exception:
            pass
        
        # 如果没有获取到在线玩家，返回空列表
        if not online_players:
            return []
        
        # 检查每个在线玩家是否为假人
        bot_list = []
        for player_name in online_players:
            if not is_player(player_name, server_interface):
                bot_list.append(player_name)
        
        return bot_list
        
    except Exception as e:
        if server_interface:
            server_interface.logger.error(f"获取假人列表失败: {e}")
        return []

def send_message_to_webui(server_interface, source: str, message, message_type: str = "info", target_players: list = None, metadata: dict = None, is_rtext: bool = False):
    """
    供其他插件调用的函数，用于发送消息到WebUI并同步到游戏

    使用方法：
    from mcdreforged.api.all import VersionRequirement

    def your_function(server):
        # 获取WebUI插件实例
        webui_plugin = server.get_plugin_instance("guguwebui")
        if webui_plugin and hasattr(webui_plugin, 'send_message_to_webui'):
            # 发送普通消息
            webui_plugin.send_message_to_webui(
                server_interface=server,
                source="your_plugin_name",
                message="这是一条来自插件的消息",
                message_type="info"
            )
            # 发送RText消息
            webui_plugin.send_message_to_webui(
                server_interface=server,
                source="your_plugin_name",
                message=rtext_object,  # RText对象
                message_type="info",
                is_rtext=True
            )

    Args:
        server_interface: MCDR服务器接口
        source: 消息来源（插件名称等）
        message: 消息内容（字符串或RText对象）
        message_type: 消息类型（info, warning, error, success等）
        target_players: 目标玩家列表，None表示所有玩家
        metadata: 额外的元数据
        is_rtext: 是否为RText格式，如果为True，message应该是RText对象或JSON字符串

    Returns:
        bool: 是否成功发送
    """
    try:
        from mcdreforged.api.all import LiteralEvent
        import datetime
        import uuid
        import json
        import time

        # 处理RText消息
        processed_message = message
        rtext_data = None
        
        if is_rtext:
            if hasattr(message, 'to_json_object'):  # MCDR的RText对象
                rtext_data = message.to_json_object()
                processed_message = str(message)  # 获取纯文本版本
            elif isinstance(message, (dict, list)):  # 字典或列表格式的RText
                rtext_data = message
                processed_message = json.dumps(message, ensure_ascii=False)  # 转换为JSON字符串
            elif isinstance(message, str):  # JSON字符串格式
                try:
                    rtext_data = json.loads(message)
                    processed_message = message
                except json.JSONDecodeError:
                    # 如果不是有效的JSON，当作普通字符串处理
                    rtext_data = None
                    processed_message = message

        # 检查是否启用了聊天到游戏功能
        try:
            config = server_interface.load_config_simple("config.json", {}, echo_in_console=False)
            if not config.get("public_chat_to_game_enabled", False):
                server_interface.logger.debug("聊天到游戏功能未启用，仅记录消息")
        except Exception:
            # 如果无法读取配置，继续执行
            pass

        # 对于插件发送的消息，直接使用"插件"作为UUID，避免网络请求
        player_uuid = f"plugin_{source}"

        # 构建用于广播的 RText 消息
        if is_rtext and rtext_data:
            # 如果已经是RText格式，直接使用
            if hasattr(message, 'to_json_object'):
                rtext_message = message
            else:
                # 从rtext_data重新构建RText对象，但需要将RText数据转换为实际的RText对象
                rtext_message = create_rtext_from_data(source, rtext_data, player_uuid)
        else:
            # 创建RText格式的消息
            rtext_message = create_chat_message_rtext(source, processed_message, player_uuid)

        # 首先分发WebUI聊天消息事件，供其他插件监听和处理
        try:
            # 创建事件数据元组 - MCDR会将元组展开为多个参数
            event_data = (
                source,           # source
                source,           # player_id (使用source作为player_id)
                player_uuid,      # player_uuid
                processed_message, # message
                f"plugin_{source}", # session_id (使用插件名作为session_id)
                int(datetime.datetime.now(datetime.timezone.utc).timestamp())  # timestamp (Unix时间戳)
            )
            # 分发事件
            server_interface.dispatch_event(LiteralEvent("webui.chat_message_sent"), event_data)
        except Exception as e:
            server_interface.logger.error(f"分发WebUI聊天消息事件失败: {e}")

        # 如果当前服务器内没有玩家在线，则仅记录，不下发到游戏
        try:
            info = get_java_server_info()
            player_count_raw = info.get("server_player_count")
            player_count = int(player_count_raw) if player_count_raw is not None and str(player_count_raw).isdigit() else 0
        except Exception:
            player_count = 0

        if player_count <= 0:
            # 仅记录到聊天日志
            try:
                from guguwebui.utils.chat_logger import ChatLogger
                chat_logger = ChatLogger()
                # 记录RText格式的消息，标记为插件消息
                final_rtext_data = rtext_data if rtext_data else (rtext_message.to_json_object() if hasattr(rtext_message, 'to_json_object') else None)
                chat_logger.add_message(source, processed_message, rtext_data=final_rtext_data, message_type=2, server=server_interface)
            except Exception as e:
                server_interface.logger.warning(f"记录聊天消息失败: {e}")
            return True

        # 有玩家在线，使用广播发送消息
        server_interface.broadcast(rtext_message)

        # 记录Web在线心跳（发送者计为在线5秒）
        try:
            # 尝试获取WEB_ONLINE_PLAYERS，如果无法获取则跳过
            import sys
            if hasattr(sys.modules.get('guguwebui.api.chat', None), 'WEB_ONLINE_PLAYERS'):
                from guguwebui.api.chat import WEB_ONLINE_PLAYERS
                WEB_ONLINE_PLAYERS[source] = int(time.time()) + 5
        except Exception:
            pass

        # 记录到聊天日志
        try:
            from guguwebui.utils.chat_logger import ChatLogger
            chat_logger = ChatLogger()
            # 记录RText格式的消息，标记为插件消息，这样前端显示时就能正确渲染
            final_rtext_data = rtext_data if rtext_data else (rtext_message.to_json_object() if hasattr(rtext_message, 'to_json_object') else None)
            chat_logger.add_message(source, processed_message, rtext_data=final_rtext_data, message_type=2, server=server_interface)
        except Exception as e:
            server_interface.logger.warning(f"记录聊天消息失败: {e}")

        # 记录调试信息
        server_interface.logger.debug(f"插件 {source} 发送消息到游戏: {rtext_message}")

        return True

    except Exception as e:
        if server_interface:
            server_interface.logger.error(f"发送WebUI消息失败: {e}")
        return False


#============================================================#
# URL 路径处理工具函数
def get_plugin_version():
    """获取插件的真实版本号"""
    try:
        import mcdreforged.api.types as MCDRTypes
        # 获取当前插件的元数据
        metadata = MCDRTypes.PluginServerInterface.get_self_metadata()
        return metadata.version
    except Exception:
        # 如果无法获取，返回默认版本
        return "1.0.0"

def get_redirect_url(request, path: str) -> str:
    """根据当前应用路径生成正确的重定向URL

    Args:
        request: FastAPI请求对象
        path: 目标路径

    Returns:
        str: 完整的重定向URL
    """
    root_path = request.scope.get("root_path", "")
    if root_path:
        return f"{root_path}{path}"
    else:
        return path

def get_index_path(request) -> str:
    """根据当前应用路径生成正确的index路径

    Args:
        request: FastAPI请求对象

    Returns:
        str: index页面路径
    """
    root_path = request.scope.get("root_path", "")
    if root_path:
        return f"{root_path}/index"
    else:
        return "/index"

def get_nav_path(request, path: str) -> str:
    """根据当前应用路径生成正确的导航链接

    Args:
        request: FastAPI请求对象
        path: 导航路径

    Returns:
        str: 完整的导航路径
    """
    root_path = request.scope.get("root_path", "")
    if root_path:
        return f"{root_path}{path}"
    else:
        return path

#============================================================#
# 配置更新工具函数
def consistent_type_update(original, updates, remove_missing=False):
    """
    更新配置数据，保持类型一致性

    Args:
        original: 原始配置数据
        updates: 新的配置数据
        remove_missing: 是否删除原始数据中存在但新数据中不存在的键
    """
    # 如果启用删除功能，先找出需要删除的键
    if remove_missing and isinstance(original, dict) and isinstance(updates, dict):
        keys_to_remove = [key for key in original if key not in updates]
        for key in keys_to_remove:
            del original[key]

    # 更新现有键或添加新键
    for key, value in updates.items():
        # setting to None
        if key in original and original[key] is None and \
            (not value or (isinstance(value,list) and not any(value))):
            continue
        # dict -> recurssive update
        elif isinstance(value, dict) and key in original and isinstance(original[key], dict):
            consistent_type_update(original[key], value, remove_missing)
        # get previous type
        elif isinstance(value, list) and key in original:
            # 如果原值是字典而新值是列表，直接替换
            if isinstance(original[key], dict):
                original[key] = value
                continue

            # save old comment
            original_ca = original[key].ca.items if isinstance(original[key], CommentedSeq) else None

            targe_type = list( # search the first type in the original list
                {type(item) for item in original[key] if item}
            ) if original[key] else None

            temp_list = [
                (targe_type[0](item) if targe_type else item) if item else None
                for item in value
            ]

            if original_ca: # save comment to last attribute
                original[key] = CommentedSeq(temp_list)
                original[key].ca.items[len(original[key])-1] = original_ca[max(original_ca)]
            else:
                original[key] = temp_list

        # Force type convertion
        elif key in original and original[key]:
            original_type = type(original[key])
            original[key] = original_type(value)
        # new attributes
        else:
            original[key] = value

#============================================================#
# Pip 包管理工具函数
def get_installed_pip_packages():
    """获取已安装的pip包列表

    Returns:
        dict: 包含状态和包信息的字典
    """
    try:
        import subprocess
        import sys

        process = subprocess.Popen(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            return {"status": "error", "message": f"获取包列表失败: {stderr}"}

        packages = json.loads(stdout)
        return {"status": "success", "packages": packages}
    except Exception as e:
        return {"status": "error", "message": f"获取包列表时出错: {str(e)}"}

async def pip_task(task_id, action, package):
    """异步执行pip安装/卸载任务

    Args:
        task_id: 任务ID
        action: 操作类型 ('install' 或 'uninstall')
        package: 包名
    """
    try:
        import asyncio
        import subprocess
        import sys

        # 需要导入全局变量，这里会通过web_server.py导入
        from guguwebui.web_server import pip_tasks

        output = []

        if action == "install":
            cmd = [sys.executable, "-m", "pip", "install", package]
            output.append(f"正在安装包: {package}")
        elif action == "uninstall":
            cmd = [sys.executable, "-m", "pip", "uninstall", "-y", package]
            output.append(f"正在卸载包: {package}")
        else:
            pip_tasks[task_id] = {
                "completed": True,
                "success": False,
                "output": ["不支持的操作类型"],
            }
            return

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        # 更新初始状态
        pip_tasks[task_id] = {
            "completed": False,
            "success": False,
            "output": output.copy(),
        }

        # 读取输出
        while True:
            stdout_line = process.stdout.readline()
            if stdout_line:
                output.append(stdout_line.strip())
                pip_tasks[task_id]["output"] = output.copy()

            stderr_line = process.stderr.readline()
            if stderr_line:
                output.append(stderr_line.strip())
                pip_tasks[task_id]["output"] = output.copy()

            if not stdout_line and not stderr_line and process.poll() is not None:
                break

        # 获取最终退出码
        exit_code = process.wait()
        success = exit_code == 0

        if success:
            output.append("操作成功完成")
        else:
            output.append(f"操作失败，退出码: {exit_code}")

        # 更新最终状态
        pip_tasks[task_id] = {
            "completed": True,
            "success": success,
            "output": output,
        }
    except Exception as e:
        import asyncio
        from guguwebui.web_server import pip_tasks

        error_msg = f"执行pip操作时出错: {str(e)}"
        output.append(error_msg)
        pip_tasks[task_id] = {
            "completed": True,
            "success": False,
            "output": output,
        }

#============================================================#
# 仓库缓存检查工具函数
def check_repository_cache(server):
    """检查插件仓库缓存，如果不存在则尝试下载

    Args:
        server: MCDR服务器接口
    """
    try:
        # 获取PIM缓存目录
        from guguwebui.utils.PIM import PIMHelper

        pim_helper = PIMHelper(server)
        cache_dir = pim_helper.get_temp_dir()
        cache_file = os.path.join(cache_dir, "everything_slim.json")

        # 创建一个命令源模拟对象
        class CacheCheckSource:
            def __init__(self, server):
                self.server = server

            def reply(self, message):
                self.server.logger.info(f"[仓库缓存] {message}")

            def get_server(self):
                return self.server

        source = CacheCheckSource(server)

        # 检查缓存是否存在
        if not os.path.exists(cache_file):
            server.logger.info("插件仓库缓存不存在，尝试下载")

            # 使用PIM获取仓库数据，会自动缓存，使用ignore_ttl=False以利用PIM的失败缓存机制
            # 无需额外的try-except，因为PIM内部已经实现了失败处理和重试
            pim_helper.get_cata_meta(source, ignore_ttl=False)

            # 检查下载后缓存是否存在
            if os.path.exists(cache_file):
                server.logger.info("插件仓库缓存已成功下载")
            else:
                server.logger.warning("插件仓库缓存下载可能失败，但这是正常的，请参考日志了解详情")
                server.logger.info("WebUI将使用PIM模块的下载失败缓存机制，在15分钟内不会重复尝试下载失败的仓库")
        else:
            server.logger.debug("插件仓库缓存已存在")
    except Exception as e:
        server.logger.error(f"检查仓库缓存时出错: {e}")