"""
配置管理相关的API函数
迁移自 web_server.py 中的配置管理端点
"""

import json
import os
import socket
import string
import secrets
import ipaddress
from pathlib import Path
from typing import List, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi import status, Depends
from ..utils.constant import DEFALUT_CONFIG, saveconfig, config_data, SERVER_PROPERTIES_PATH
from ..utils.i18n_util import (
    build_json_i18n_translations, build_yaml_i18n_translations, get_comment, consistent_type_update
)
from ..utils.mc_util import get_server_port, find_plugin_config_paths
from ..utils.chat_logger import ChatLogger
from ..utils.api_cache import api_cache
from ..utils.server_util import verify_token


async def list_config_files(
    request: Request,
    plugin_id: str,
    server=None
) -> JSONResponse:
    """列出插件的配置文件及网页配置信息"""
    config_path_list: List[str] = find_plugin_config_paths(plugin_id)
    
    # 查找对应的 main.json 以检测网页配置
    web_mapping = {}
    if config_path_list:
        try:
            config_dir = Path(config_path_list[0]).parent
            main_json_path = config_dir / "main.json"
            if main_json_path.exists():
                with open(main_json_path, "r", encoding="UTF-8") as f:
                    main_json = json.load(f)
                    # 记录哪些文件名有对应的 html
                    for cfg_name, html_name in main_json.items():
                        if isinstance(html_name, str) and html_name.endswith(".html"):
                            web_mapping[cfg_name] = True
        except Exception:
            pass

    files_info = []
    for p in config_path_list:
        path_obj = Path(p)
        if path_obj.name.lower() == "main.json":
            continue
        files_info.append({
            "path": p,
            "name": path_obj.name,
            "has_web": web_mapping.get(path_obj.name, False)
        })

    return JSONResponse({"files": files_info})


async def get_web_config(
    request: Request,
    server=None
) -> JSONResponse:
    """获取Web配置"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)

    # 检查是否已配置 API 密钥（出于安全考虑不返回实际密钥值）
    ai_api_key_value = config.get("ai_api_key", "")
    ai_api_key_configured = bool(ai_api_key_value and ai_api_key_value.strip())

    # 获取聊天消息数量
    try:
        chat_logger = ChatLogger()
        chat_message_count = chat_logger.get_message_count()

        # 更新返回数据中的聊天消息数量
        response_data = {
            "host": config["host"],
            "port": config["port"],
            "super_admin_account": config["super_admin_account"],
            "disable_admin_login_web": config["disable_other_admin"],
            "enable_temp_login_password": config["allow_temp_password"],
            "ai_api_key": "",  # 出于安全考虑不返回实际密钥
            "ai_api_key_configured": ai_api_key_configured,  # 新增：指示是否已配置
            "ai_model": config.get("ai_model", "deepseek-chat"),
            "ai_api_url": config.get("ai_api_url", "https://api.deepseek.com/chat/completions"),
            "mcdr_plugins_url": config.get("mcdr_plugins_url", "https://api.mcdreforged.com/catalogue/everything_slim.json.xz"),
            "repositories": config.get("repositories", []),
            "ssl_enabled": config.get("ssl_enabled", False),
            "ssl_certfile": config.get("ssl_certfile", ""),
            "ssl_keyfile": config.get("ssl_keyfile", ""),
            "ssl_keyfile_password": config.get("ssl_keyfile_password", ""),
            "public_chat_enabled": config.get("public_chat_enabled", False),
            "public_chat_to_game_enabled": config.get("public_chat_to_game_enabled", False),
            "chat_verification_expire_minutes": config.get("chat_verification_expire_minutes", 10),
            "chat_session_expire_hours": config.get("chat_session_expire_hours", 24),
            "force_standalone": config.get("force_standalone", False),
            "icp_records": config.get("icp_records", []),
            "chat_message_count": chat_message_count,
        }

        return JSONResponse(response_data)
    except Exception as e:
        # 如果获取聊天消息数量失败，返回默认值
        response_data = {
            "host": config["host"],
            "port": config["port"],
            "super_admin_account": config["super_admin_account"],
            "disable_admin_login_web": config["disable_other_admin"],
            "enable_temp_login_password": config["allow_temp_password"],
            "ai_api_key": "",  # 出于安全考虑不返回实际密钥
            "ai_api_key_configured": ai_api_key_configured,  # 新增：指示是否已配置
            "ai_model": config.get("ai_model", "deepseek-chat"),
            "ai_api_url": config.get("ai_api_url", "https://api.deepseek.com/chat/completions"),
            "mcdr_plugins_url": config.get("mcdr_plugins_url", "https://api.mcdreforged.com/catalogue/everything_slim.json.xz"),
            "repositories": config.get("repositories", []),
            "ssl_enabled": config.get("ssl_enabled", False),
            "ssl_certfile": config.get("ssl_certfile", ""),
            "ssl_keyfile": config.get("ssl_keyfile", ""),
            "ssl_keyfile_password": config.get("ssl_keyfile_password", ""),
            "public_chat_enabled": config.get("public_chat_enabled", False),
            "public_chat_to_game_enabled": config.get("public_chat_to_game_enabled", False),
            "chat_verification_expire_minutes": config.get("chat_verification_expire_minutes", 10),
            "chat_session_expire_hours": config.get("chat_session_expire_hours", 24),
            "force_standalone": config.get("force_standalone", False),
            "icp_records": config.get("icp_records", []),
            "chat_message_count": 0,
        }

        return JSONResponse(response_data)


async def save_web_config(
    request: Request,
    config: saveconfig,
    server=None
) -> JSONResponse:
    """保存Web配置"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    web_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)

    # change port & account
    if config.action == "config":
        if config.host:
            web_config["host"] = config.host
        if config.port:
            web_config["port"] = int(config.port)
        if config.superaccount:
            web_config["super_admin_account"] = int(config.superaccount)
        # 更新AI配置 - 处理None值，避免将None保存到配置中
        if config.ai_api_key is not None:
            # JavaScript端undefined会被转为null，处理这种情况
            if isinstance(config.ai_api_key, str):
                web_config["ai_api_key"] = config.ai_api_key
        if config.ai_model is not None:
            if isinstance(config.ai_model, str):
                web_config["ai_model"] = config.ai_model
        if config.ai_api_url is not None:
            if isinstance(config.ai_api_url, str):
                web_config["ai_api_url"] = config.ai_api_url
        # 更新MCDR插件目录URL
        if config.mcdr_plugins_url is not None:
            if isinstance(config.mcdr_plugins_url, str):
                web_config["mcdr_plugins_url"] = config.mcdr_plugins_url
        # 更新仓库列表
        if config.repositories is not None:
            web_config["repositories"] = config.repositories
        # 更新SSL配置
        if config.ssl_enabled is not None:
            web_config["ssl_enabled"] = config.ssl_enabled
        if config.ssl_certfile is not None:
            if isinstance(config.ssl_certfile, str):
                web_config["ssl_certfile"] = config.ssl_certfile
        if config.ssl_keyfile is not None:
            if isinstance(config.ssl_keyfile, str):
                web_config["ssl_keyfile"] = config.ssl_keyfile
        if config.ssl_keyfile_password is not None:
            if isinstance(config.ssl_keyfile_password, str):
                web_config["ssl_keyfile_password"] = config.ssl_keyfile_password
        # 更新公开聊天页配置
        if config.public_chat_enabled is not None:
            web_config["public_chat_enabled"] = config.public_chat_enabled
        if config.public_chat_to_game_enabled is not None:
            web_config["public_chat_to_game_enabled"] = config.public_chat_to_game_enabled
        # 更新聊天页验证和会话配置
        if config.chat_verification_expire_minutes is not None:
            web_config["chat_verification_expire_minutes"] = config.chat_verification_expire_minutes
        if config.chat_session_expire_hours is not None:
            web_config["chat_session_expire_hours"] = config.chat_session_expire_hours
        if config.force_standalone is not None:
            web_config["force_standalone"] = config.force_standalone
        if config.icp_records is not None:
            web_config["icp_records"] = config.icp_records

        response = {"status": "success", "message": "配置已保存，重启插件后生效"}
    # disable_admin_login_web & enable_temp_login_password
    elif config.action in ["disable_admin_login_web", "enable_temp_login_password"]:
        config_map = {
            "disable_admin_login_web": "disable_other_admin",
            "enable_temp_login_password": "allow_temp_password",
        }
        web_config[config_map[config.action]] = not web_config[
            config_map[config.action]
        ]
        response = {
            "status": "success",
            "message": web_config[config_map[config.action]],
        }
    elif config.action == "toggle_ssl":
        web_config["ssl_enabled"] = not web_config.get("ssl_enabled", False)
        response = {
            "status": "success",
            "message": web_config["ssl_enabled"],
        }
    else:
        response = {"status": "error", "message": "Invalid action"}

    try:
        # 检查MCDR服务器接口的save_config_simple方法签名
        # 打印出调试信息
        server.logger.debug(f"保存配置: file_name='config.json'")

        # 直接使用模块函数而不是server.save_config_simple
        from pathlib import Path
        import json

        # 确保配置目录存在
        config_dir = server.get_data_folder()
        Path(config_dir).mkdir(parents=True, exist_ok=True)

        # 构建配置文件路径
        config_path = Path(config_dir) / "config.json"

        # 直接保存JSON文件
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(web_config, f, ensure_ascii=False, indent=4)

        server.logger.debug(f"配置已保存到 {config_path}")
        return JSONResponse(response)
    except Exception as e:
        import traceback
        error_stack = traceback.format_exc()
        server.logger.error(f"保存配置文件时出错: {str(e)}\n{error_stack}")
        return JSONResponse({"status": "error", "message": f"保存配置文件失败: {str(e)}"}, status_code=500)


from ..utils.path_util import SafePath, get_base_dirs

async def load_config(
    request: Request,
    path: str,
    translation: bool = False,
    type: str = "auto",
    server=None
) -> JSONResponse:
    """加载配置文件"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    try:
        path_obj = SafePath.get_safe_path(path, get_base_dirs(server))
    except ValueError as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=403)

    mcdr_language: str = server.get_mcdr_language()

    # 提取 config/chat_with_deepseek 目录
    config_dir = path_obj.parent
    main_json_path = config_dir / "main.json"

    # 网页模式：仅当 type 为 auto 且 main.json 中有定义时返回 HTML
    if type == "auto":
        # 读取 main.json
        main_config = {}
        if main_json_path.exists():
            try:
                with open(main_json_path, "r", encoding="UTF-8") as f:
                    main_config = json.load(f)
            except Exception:
                pass

        config_value = main_config.get(path_obj.name)
        if config_value:
            html_path = config_dir / config_value
            if html_path.exists() and html_path.suffix == ".html":
                try:
                    with open(html_path, "r", encoding="UTF-8") as f:
                        return JSONResponse({"status": "success", "type": "html", "content": f.read()})
                except Exception:
                    return JSONResponse(
                        {"status": "error", "message": "Failed to read HTML file"},
                        status_code=500,
                    )

    # 如果 type 为 json 或其它，或者没有匹配的网页，则继续加载原始配置数据
    # Translation for xxx.json -> xxx_lang.json
    if translation:
        # 为前端提供兼容：将扁平的 translations[lang]["a.b"] 结构转换为嵌套结构
        def _nest_translation_map_simple(flat_map: dict) -> dict:
            nested = {}
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
                    if i == len(parts) - 1 and isinstance(meta, dict):
                        if "name" in meta:
                            cur[part]["name"] = meta.get("name")
                        if "desc" in meta:
                            cur[part]["desc"] = meta.get("desc")
                    if "children" not in cur[part] or not isinstance(cur[part]["children"], dict):
                        cur[part]["children"] = {}
                    cur = cur[part]["children"]
            return nested

        def _maybe_nest_i18n(i18n: dict) -> dict:
            try:
                if not isinstance(i18n, dict):
                    return i18n
                trans = i18n.get("translations", {})
                # 若 zh-CN 缺失但存在中文注释生成内容，则确保添加
                if isinstance(trans, dict):
                    for lang, mapping in list(trans.items()):
                        # 扁平 -> 嵌套
                        if isinstance(mapping, dict) and any(isinstance(k, str) and "." in k for k in mapping.keys()):
                            trans[lang] = _nest_translation_map_simple(mapping)
                i18n["translations"] = trans
                return i18n
            except Exception:
                return i18n

        if path_obj.suffix in [".json", ".properties"]:
            path_obj = path_obj.with_stem(f"{path_obj.stem}_lang")
        if path_obj.suffix == ".properties":
            path_obj = path_obj.with_suffix(f".json")

    if not path_obj.exists(): # file not exists
        return JSONResponse({}, status_code=200)

    try:
        raw_text = None
        with open(path_obj, "r", encoding="UTF-8") as f:
            raw_text = f.read()
            f.seek(0)
            if path_obj.suffix == ".json":
                config = json.load(f)
            elif path_obj.suffix in [".yml", ".yaml"]:
                from ..utils.table import yaml
                config = yaml.load(f)
            elif path_obj.suffix == ".properties":
                import javaproperties
                config = javaproperties.load(f)
                # convert string "true" "false" to True False
                config = {k:v if v not in ["true", "false"] else
                          True if v == "true" else False
                          for k,v in config.items()}
    except json.JSONDecodeError:
        if path_obj.suffix == ".json":
            config = {}
    except UnicodeDecodeError:
        # Handle encoding errors
        with open(path_obj, "r", encoding="UTF-8", errors="replace") as f:
            if path_obj.suffix == ".json":
                config = json.load(f)

    if translation:
        # Get corresponding language
        if path_obj.suffix in [".json", ".properties"]:
            if path_obj.suffix == ".json":
                try:
                    # 支持JSON多语言结构：统一输出 default+translations
                    i18n = build_json_i18n_translations(config)
                    return JSONResponse(_maybe_nest_i18n(i18n))
                except Exception:
                    pass
            # 原有行为回退
            config = config.get(mcdr_language) or config.get("en_us") or {}
            return JSONResponse(config)
        # YAML: 返回多语言结构
        elif path_obj.suffix in [".yml", ".yaml"]:
            try:
                i18n = build_yaml_i18n_translations(config, raw_text or "")
                return JSONResponse(_maybe_nest_i18n(i18n))
            except Exception:
                # 回退到原有的注释抽取
                return JSONResponse(get_comment(config))

    return JSONResponse(config)


async def save_config(
    request: Request,
    config_data: config_data,
    server=None
) -> JSONResponse:
    """保存配置文件"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    try:
        config_path = SafePath.get_safe_path(config_data.file_path, get_base_dirs(server))
    except ValueError as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=403)

    if config_path == Path(server.get_data_folder()) / "config.json":
        return JSONResponse({"status": "error", "message": "无法在此处修改guguwebui配置文件"})

    plugin_config = config_data.config_data

    if not config_path.exists():
        return JSONResponse({"status": "fail", "message": "plugin config not found"})

    try:
        # load original config data
        with open(config_path, "r", encoding="UTF-8") as f:
            if config_path.suffix == ".json":
                data = json.load(f)
            elif config_path.suffix in [".yml", ".yaml"]:
                from ..utils.table import yaml
                data = yaml.load(f)
            elif config_path.suffix == ".properties":
                import javaproperties
                data = javaproperties.load(f)
                # convert back the True False to "true" "false"
                plugin_config = {k: v if not isinstance(v, bool) else
                                 "true" if v else "false"
                                 for k, v in plugin_config.items()}
    except Exception as e:
        print(f"Error loading config file: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    # ensure type will not change
    try:
        # 对于JSON文件，允许删除不存在的键
        if config_path.suffix == ".json":
            # 特殊处理help_msg.json配置
            if config_path.name == "help_msg.json" and isinstance(plugin_config, dict):
                # 对于help_msg.json，只更新admin_help_msg和group_help_msg字段
                allowed_fields = ['admin_help_msg', 'group_help_msg']
                # 仅更新允许的字段
                for field in allowed_fields:
                    if field in plugin_config:
                        data[field] = plugin_config[field]
            # 如果提交的配置是空对象，则需确认用户是否真的想清空
            elif isinstance(plugin_config, dict) and len(plugin_config) == 0 and len(data) > 0:
                # 执行删除所有键的操作
                data.clear()
            else:
                # 正常更新操作，同时删除缺失的键
                consistent_type_update(data, plugin_config, remove_missing=True)
        else:
            # 对于YAML和properties文件，保持原有行为，不删除键
            consistent_type_update(data, plugin_config, remove_missing=False)
    except Exception as e:
        print(f"Error updating config data: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    try:
        # save config data
        with open(config_path, "w", encoding="UTF-8") as f:
            if config_path.suffix == ".json":
                json.dump(data, f, ensure_ascii=False, indent=4)
            elif config_path.suffix in [".yml", ".yaml"]:
                from ..utils.table import yaml
                yaml.dump(data, f)
            elif config_path.suffix == ".properties":
                import javaproperties
                javaproperties.dump(data, f)
        return JSONResponse({"status": "success", "message": "配置文件保存成功"})
    except Exception as e:
        print(f"Error saving config file: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


def _check_port_available(host: str, port: int) -> bool:
    """检查端口是否可用（未被占用），支持 IPv4 与 IPv6"""
    try:
        try:
            ip = ipaddress.ip_address(host)
            family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
        except ValueError:
            family = socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind((host, port))
            return True
    except socket.error:
        return False
    except Exception:
        return False


def _generate_random_password(length: int = 16) -> str:
    """生成随机密码（英文大小写+数字）"""
    # 定义字符集：大写字母、小写字母、数字
    charset = string.ascii_letters + string.digits
    # 生成随机密码
    return ''.join(secrets.choice(charset) for _ in range(length))


def _find_available_port(start_port: int, host: str = "127.0.0.1") -> int:
    """查找可用端口，从指定端口开始递增"""
    port = start_port
    while port <= 65535:
        if _check_port_available(host, port):
            return port
        port += 1
    raise RuntimeError(f"无法找到从 {start_port} 开始的可用端口")


async def setup_rcon_config(
    request: Request,
    server=None
) -> JSONResponse:
    """一键启用RCON配置"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    try:
        # 获取Minecraft服务器端口
        try:
            mc_server_port = get_server_port(server)
        except Exception as e:
            return JSONResponse(
                {"status": "error", "message": f"无法获取Minecraft服务器端口: {str(e)}"},
                status_code=500
            )

        # 计算RCON端口（服务器端口+1，如果被占用则继续+1）
        rcon_host = "127.0.0.1"
        try:
            rcon_port = _find_available_port(mc_server_port + 1, rcon_host)
        except RuntimeError as e:
            return JSONResponse(
                {"status": "error", "message": str(e)},
                status_code=500
            )

        # 生成随机密码
        rcon_password = _generate_random_password(16)

        # 更新MC配置
        mc_config_updated = False
        try:
            # 读取server.properties配置
            from ..utils.constant import SERVER_PROPERTIES_PATH
            if SERVER_PROPERTIES_PATH.exists():
                import javaproperties
                with open(SERVER_PROPERTIES_PATH, "r", encoding="UTF-8") as f:
                    mc_config = javaproperties.load(f)
                
                # 更新RCON设置
                mc_config["enable-rcon"] = "true"
                mc_config["rcon.port"] = str(rcon_port)
                mc_config["rcon.password"] = rcon_password
                mc_config["broadcast-rcon-to-ops"] = "false"  # 可选：不广播RCON到OP
                
                # 保存MC配置
                with open(SERVER_PROPERTIES_PATH, "w", encoding="UTF-8") as f:
                    javaproperties.dump(mc_config, f)
                
                mc_config_updated = True
            else:
                return JSONResponse(
                    {"status": "error", "message": "找不到server.properties文件"},
                    status_code=500
                )
        except Exception as e:
            return JSONResponse(
                {"status": "error", "message": f"更新MC配置失败: {str(e)}"},
                status_code=500
            )

        # 更新MCDR配置
        mcdr_config_updated = False
        try:
            # 读取MCDR config.yml配置
            config_path = Path("config.yml")
            if config_path.exists():
                from ..utils.table import yaml
                with open(config_path, "r", encoding="UTF-8") as f:
                    mcdr_config = yaml.load(f)
                
                # 确保rcon配置节存在
                if "rcon" not in mcdr_config:
                    mcdr_config["rcon"] = {}
                
                # 更新MCDR RCON设置
                mcdr_config["rcon"]["enable"] = True
                mcdr_config["rcon"]["address"] = rcon_host
                mcdr_config["rcon"]["port"] = rcon_port
                mcdr_config["rcon"]["password"] = rcon_password
                
                # 保存MCDR配置
                with open(config_path, "w", encoding="UTF-8") as f:
                    yaml.dump(mcdr_config, f)
                
                mcdr_config_updated = True
            else:
                return JSONResponse(
                    {"status": "error", "message": "找不到MCDR config.yml文件"},
                    status_code=500
                )
        except Exception as e:
            return JSONResponse(
                {"status": "error", "message": f"更新MCDR配置失败: {str(e)}"},
                status_code=500
            )

        # 清除RCON状态缓存，因为配置已更改
        api_cache.invalidate("rcon_status")

        # 直接重载MCDR配置，MCDR会自动等待服务器重启完成
        try:
            server.execute_command("!!MCDR reload config")
            server.logger.info("RCON配置完成，已自动重载MCDR配置")
        except Exception as e:
            server.logger.warning(f"自动重载MCDR配置时出错: {e}")

        # 返回成功结果
        return JSONResponse({
            "status": "success",
            "message": "RCON配置已成功启用",
            "config": {
                "rcon_host": rcon_host,
                "rcon_port": rcon_port,
                "rcon_password": rcon_password,
                "mc_config_updated": mc_config_updated,
                "mcdr_config_updated": mcdr_config_updated
            }
        })

    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"配置RCON时发生错误: {str(e)}"},
            status_code=500
        )
