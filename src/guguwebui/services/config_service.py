import ipaddress
import json
import logging
import secrets
import socket
import string
from pathlib import Path
from typing import List, Optional

from guguwebui.constant import DEFALUT_CONFIG, MCDR_OFFICIAL_CATALOGUE_URL, PF_PLUGIN_CATALOGUE_URL, SERVER_PROPERTIES_PATH
from guguwebui.utils.api_cache import api_cache
from guguwebui.utils.chat_logger import ChatLogger
from guguwebui.utils.i18n_util import (
    build_json_i18n_translations,
    build_yaml_i18n_translations,
    consistent_type_update,
    get_comment,
)
from guguwebui.utils.mc_util import find_plugin_config_paths, get_server_port
from guguwebui.utils.path_util import SafePath, get_base_dirs

logger = logging.getLogger(__name__)


class ConfigService:
    def __init__(self, server):
        self.server = server

    @staticmethod
    def find_plugin_config_paths(plugin_id: str) -> list:
        config_dir = Path("./config")
        response = []
        config_suffix = [".json", ".yml", ".yaml"]

        # Check ./config/plugin_id/
        plugin_folder = config_dir / plugin_id
        if plugin_folder.exists():
            response += [
                file
                for file in plugin_folder.rglob("*")
                if file.suffix.lower() in config_suffix
            ]
        else:
            # Case-insensitive check for folder
            if config_dir.exists():
                for item in config_dir.iterdir():
                    if item.is_dir() and item.name.lower() == plugin_id.lower():
                        response += [
                            file
                            for file in item.rglob("*")
                            if file.suffix.lower() in config_suffix
                        ]

        # Check ./config/plugin_id.json etc.
        for suffix in config_suffix:
            file_path = (config_dir / plugin_id).with_suffix(suffix)
            if file_path.exists():
                response.append(file_path)
            else:
                # Case-insensitive check for file
                if config_dir.exists():
                    for item in config_dir.iterdir():
                        if (
                            item.is_file()
                            and item.stem.lower() == plugin_id.lower()
                            and item.suffix.lower() == suffix
                        ):
                            response.append(item)

        return [str(i) for i in response if not Path(i).stem.lower().endswith("_lang")]

    def list_config_files(self, plugin_id: str):
        config_path_list = self.find_plugin_config_paths(plugin_id)
        web_mapping = {}
        if config_path_list:
            try:
                config_dir = Path(config_path_list[0]).parent
                main_json_path = config_dir / "main.json"
                if main_json_path.exists():
                    with open(main_json_path, "r", encoding="UTF-8") as f:
                        main_json = json.load(f)
                        for cfg_name, html_name in main_json.items():
                            if isinstance(html_name, str) and html_name.endswith(
                                ".html"
                            ):
                                web_mapping[cfg_name] = True
            except Exception:
                pass

        files_info = []
        for p in config_path_list:
            path_obj = Path(p)
            if path_obj.name.lower() == "main.json":
                continue
            files_info.append(
                {
                    "path": p,
                    "name": path_obj.name,
                    "has_web": web_mapping.get(path_obj.name, False),
                }
            )
        return files_info

    def get_config(self):
        """获取原始配置字典"""
        return self.server.load_config_simple(
            "config.json", DEFALUT_CONFIG, echo_in_console=False
        )

    async def get_web_config(self):
        config = self.server.load_config_simple(
            "config.json", DEFALUT_CONFIG, echo_in_console=False
        )
        ai_api_key_value = config.get("ai_api_key", "")
        ai_api_key_configured = bool(ai_api_key_value and ai_api_key_value.strip())

        chat_message_count = 0
        try:
            chat_logger = ChatLogger()
            chat_message_count = chat_logger.get_message_count()
        except Exception:
            pass

        return {
            "host": config["host"],
            "port": config["port"],
            "super_admin_account": config["super_admin_account"],
            "disable_admin_login_web": config["disable_other_admin"],
            "enable_temp_login_password": config["allow_temp_password"],
            "ai_api_key": "",
            "ai_api_key_configured": ai_api_key_configured,
            "ai_model": config.get("ai_model", "deepseek-chat"),
            "ai_api_url": config.get(
                "ai_api_url", "https://api.deepseek.com/chat/completions"
            ),
            "mcdr_plugins_url": config.get(
                "mcdr_plugins_url",
                MCDR_OFFICIAL_CATALOGUE_URL,
            ),
            "pf_plugin_catalogue_url": PF_PLUGIN_CATALOGUE_URL,
            "repositories": config.get("repositories", []),
            "ssl_enabled": config.get("ssl_enabled", False),
            "ssl_certfile": config.get("ssl_certfile", ""),
            "ssl_keyfile": config.get("ssl_keyfile", ""),
            "ssl_keyfile_password": config.get("ssl_keyfile_password", ""),
            "public_chat_enabled": config.get("public_chat_enabled", False),
            "public_chat_to_game_enabled": config.get(
                "public_chat_to_game_enabled", False
            ),
            "chat_verification_expire_minutes": config.get(
                "chat_verification_expire_minutes", 10
            ),
            "chat_session_expire_hours": config.get("chat_session_expire_hours", 24),
            "force_standalone": config.get("force_standalone", False),
            "icp_records": config.get("icp_records", []),
            "chat_message_count": chat_message_count,
        }

    def save_web_config(self, config_info):
        web_config = self.server.load_config_simple(
            "config.json", DEFALUT_CONFIG, echo_in_console=False
        )
        action = config_info.action

        if action == "config":
            if config_info.host:
                web_config["host"] = config_info.host
            if config_info.port:
                web_config["port"] = int(config_info.port)
            if config_info.super_account:
                web_config["super_admin_account"] = int(config_info.super_account)
            if config_info.ai_api_key is not None:
                web_config["ai_api_key"] = config_info.ai_api_key
            if config_info.ai_model is not None:
                web_config["ai_model"] = config_info.ai_model
            if config_info.ai_api_url is not None:
                web_config["ai_api_url"] = config_info.ai_api_url
            if config_info.mcdr_plugins_url is not None:
                web_config["mcdr_plugins_url"] = config_info.mcdr_plugins_url
            if config_info.repositories is not None:
                web_config["repositories"] = config_info.repositories
            if config_info.ssl_enabled is not None:
                web_config["ssl_enabled"] = config_info.ssl_enabled
            if config_info.ssl_certfile is not None:
                web_config["ssl_certfile"] = config_info.ssl_certfile
            if config_info.ssl_keyfile is not None:
                web_config["ssl_keyfile"] = config_info.ssl_keyfile
            if config_info.ssl_keyfile_password is not None:
                web_config["ssl_keyfile_password"] = config_info.ssl_keyfile_password
            if config_info.public_chat_enabled is not None:
                web_config["public_chat_enabled"] = config_info.public_chat_enabled
            if config_info.public_chat_to_game_enabled is not None:
                web_config["public_chat_to_game_enabled"] = (
                    config_info.public_chat_to_game_enabled
                )
            if config_info.chat_verification_expire_minutes is not None:
                web_config["chat_verification_expire_minutes"] = (
                    config_info.chat_verification_expire_minutes
                )
            if config_info.chat_session_expire_hours is not None:
                web_config["chat_session_expire_hours"] = (
                    config_info.chat_session_expire_hours
                )
            if config_info.force_standalone is not None:
                web_config["force_standalone"] = config_info.force_standalone
            if config_info.icp_records is not None:
                web_config["icp_records"] = config_info.icp_records
            response = {"status": "success", "message": "配置已保存，重启插件后生效"}
        elif action in ["disable_admin_login_web", "enable_temp_login_password"]:
            config_map = {
                "disable_admin_login_web": "disable_other_admin",
                "enable_temp_login_password": "allow_temp_password",
            }
            web_config[config_map[action]] = not web_config[config_map[action]]
            response = {"status": "success", "message": web_config[config_map[action]]}
        elif action == "toggle_ssl":
            web_config["ssl_enabled"] = not web_config.get("ssl_enabled", False)
            response = {"status": "success", "message": web_config["ssl_enabled"]}
        else:
            return {"status": "error", "message": "Invalid action"}

        try:
            config_dir = self.server.get_data_folder()
            Path(config_dir).mkdir(parents=True, exist_ok=True)
            config_path = Path(config_dir) / "config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(web_config, f, ensure_ascii=False, indent=4)
            return response
        except Exception as e:
            logger.error(f"保存配置文件时出错: {e}")
            return {"status": "error", "message": f"保存配置文件失败: {str(e)}"}

    def load_config(
        self, path: str, translation: bool = False, config_type: str = "auto"
    ):
        try:
            path_obj = SafePath.get_safe_path(path, get_base_dirs(self.server))
        except ValueError as e:
            return {"status": "error", "message": str(e), "code": 403}

        config_dir = path_obj.parent
        main_json_path = config_dir / "main.json"

        if config_type == "auto":
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
                            return {
                                "status": "success",
                                "type": "html",
                                "content": f.read(),
                            }
                    except Exception:
                        return {
                            "status": "error",
                            "message": "Failed to read HTML file",
                            "code": 500,
                        }

        if translation:
            if path_obj.suffix in [".json", ".properties"]:
                path_obj = path_obj.with_stem(f"{path_obj.stem}_lang")
            if path_obj.suffix == ".properties":
                path_obj = path_obj.with_suffix(f".json")

        if not path_obj.exists():
            return {}

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
                    config = {
                        k: (
                            v
                            if v not in ["true", "false"]
                            else True if v == "true" else False
                        )
                        for k, v in config.items()
                    }
        except Exception:
            config = {}

        if translation:
            if path_obj.suffix == ".json":
                try:
                    return self._maybe_nest_i18n(build_json_i18n_translations(config))
                except Exception:
                    pass
            elif path_obj.suffix in [".yml", ".yaml"]:
                try:
                    return self._maybe_nest_i18n(
                        build_yaml_i18n_translations(config, raw_text or "")
                    )
                except Exception:
                    return get_comment(config)

        return config

    def save_config(self, file_path: str, config_data: dict):
        try:
            config_path = SafePath.get_safe_path(file_path, get_base_dirs(self.server))
        except ValueError as e:
            return {"status": "error", "message": str(e), "code": 403}

        if config_path == Path(self.server.get_data_folder()) / "config.json":
            return {"status": "error", "message": "无法在此处修改guguwebui配置文件"}

        if not config_path.exists():
            return {"status": "fail", "message": "plugin config not found"}

        try:
            with open(config_path, "r", encoding="UTF-8") as f:
                if config_path.suffix == ".json":
                    data = json.load(f)
                elif config_path.suffix in [".yml", ".yaml"]:
                    from ..utils.table import yaml

                    data = yaml.load(f)
                elif config_path.suffix == ".properties":
                    import javaproperties

                    data = javaproperties.load(f)
                    config_data = {
                        k: v if not isinstance(v, bool) else "true" if v else "false"
                        for k, v in config_data.items()
                    }

            if config_path.suffix == ".json":
                if config_path.name == "help_msg.json" and isinstance(
                    config_data, dict
                ):
                    for field in ["admin_help_msg", "group_help_msg"]:
                        if field in config_data:
                            data[field] = config_data[field]
                elif (
                    isinstance(config_data, dict)
                    and len(config_data) == 0
                    and len(data) > 0
                ):
                    data.clear()
                else:
                    consistent_type_update(data, config_data, remove_missing=True)
            else:
                consistent_type_update(data, config_data, remove_missing=False)

            with open(config_path, "w", encoding="UTF-8") as f:
                if config_path.suffix == ".json":
                    json.dump(data, f, ensure_ascii=False, indent=4)
                elif config_path.suffix in [".yml", ".yaml"]:
                    from ..utils.table import yaml

                    yaml.dump(data, f)
                elif config_path.suffix == ".properties":
                    import javaproperties

                    javaproperties.dump(data, f)
            return {"status": "success", "message": "配置文件保存成功"}
        except Exception as e:
            logger.error(f"Error saving config file: {e}")
            return {"status": "error", "message": str(e), "code": 500}

    def setup_rcon(self):
        try:
            mc_server_port = get_server_port(self.server)
            rcon_host = "127.0.0.1"
            rcon_port = self._find_available_port(mc_server_port + 1, rcon_host)
            rcon_password = self._generate_random_password(16)

            # Update server.properties
            if SERVER_PROPERTIES_PATH.exists():
                import javaproperties

                with open(SERVER_PROPERTIES_PATH, "r", encoding="UTF-8") as f:
                    mc_config = javaproperties.load(f)
                mc_config.update(
                    {
                        "enable-rcon": "true",
                        "rcon.port": str(rcon_port),
                        "rcon.password": rcon_password,
                        "broadcast-rcon-to-ops": "false",
                    }
                )
                with open(SERVER_PROPERTIES_PATH, "w", encoding="UTF-8") as f:
                    javaproperties.dump(mc_config, f)
            else:
                return {"status": "error", "message": "找不到server.properties文件"}

            # Update MCDR config.yml
            config_path = Path("config.yml")
            if config_path.exists():
                from ..utils.table import yaml

                with open(config_path, "r", encoding="UTF-8") as f:
                    mcdr_config = yaml.load(f)
                if "rcon" not in mcdr_config:
                    mcdr_config["rcon"] = {}
                mcdr_config["rcon"].update(
                    {
                        "enable": True,
                        "address": rcon_host,
                        "port": rcon_port,
                        "password": rcon_password,
                    }
                )
                with open(config_path, "w", encoding="UTF-8") as f:
                    yaml.dump(mcdr_config, f)
            else:
                return {"status": "error", "message": "找不到MCDR config.yml文件"}

            api_cache.invalidate("rcon_status")
            self.server.execute_command("!!MCDR reload config")
            return {
                "status": "success",
                "message": "RCON配置已成功启用",
                "config": {
                    "rcon_host": rcon_host,
                    "rcon_port": rcon_port,
                    "rcon_password": rcon_password,
                },
            }
        except Exception as e:
            return {"status": "error", "message": f"配置RCON时发生错误: {str(e)}"}

    def _maybe_nest_i18n(self, i18n: dict) -> dict:
        try:
            if not isinstance(i18n, dict):
                return i18n
            trans = i18n.get("translations", {})
            if isinstance(trans, dict):
                for lang, mapping in list(trans.items()):
                    if isinstance(mapping, dict) and any(
                        isinstance(k, str) and "." in k for k in mapping.keys()
                    ):
                        trans[lang] = self._nest_translation_map_simple(mapping)
            i18n["translations"] = trans
            return i18n
        except Exception:
            return i18n

    def _nest_translation_map_simple(self, flat_map: dict) -> dict:
        nested = {}
        for full_key, meta in (flat_map or {}).items():
            if not isinstance(full_key, str):
                continue
            parts = [p for p in full_key.split(".") if p]
            cur = nested
            for i, part in enumerate(parts):
                if part not in cur or not isinstance(cur.get(part), dict):
                    cur[part] = {"name": None, "desc": None, "children": {}}
                if i == len(parts) - 1 and isinstance(meta, dict):
                    if "name" in meta:
                        cur[part]["name"] = meta.get("name")
                    if "desc" in meta:
                        cur[part]["desc"] = meta.get("desc")
                cur = cur[part]["children"]
        return nested

    def _find_available_port(self, start_port: int, host: str = "127.0.0.1") -> int:
        port = start_port
        while port <= 65535:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((host, port))
                    return port
            except socket.error:
                port += 1
        raise RuntimeError(f"无法找到可用端口")

    def _generate_random_password(self, length: int = 16) -> str:
        return "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(length)
        )

    def load_config_file_raw(self, path: str) -> str:
        """读取原始配置文件内容"""
        try:
            with open(path, "r", encoding="utf-8") as file:
                return file.read()
        except FileNotFoundError:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"File not found: {path}")

    def save_config_file_raw(self, path: str, content: str):
        """保存原始配置文件内容"""
        if "config/guguwebui/config.json" in path.replace("\\", "/"):
            from guguwebui.structures import BusinessException

            raise BusinessException("无法在此处修改 guguwebui 配置文件")

        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(content)
            return {"status": "success", "message": f"{path} saved successfully"}
        except Exception as e:
            from guguwebui.structures import BusinessException

            raise BusinessException(f"保存文件失败: {str(e)}")
