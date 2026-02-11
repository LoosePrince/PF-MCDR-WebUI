from pathlib import Path

from guguwebui.constant import DEFALUT_CONFIG


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
            response += [file for file in plugin_folder.rglob("*") if file.suffix.lower() in config_suffix]
        else:
            # Case-insensitive check for folder
            if config_dir.exists():
                for item in config_dir.iterdir():
                    if item.is_dir() and item.name.lower() == plugin_id.lower():
                        response += [file for file in item.rglob("*") if file.suffix.lower() in config_suffix]

        # Check ./config/plugin_id.json etc.
        for suffix in config_suffix:
            file_path = (config_dir / plugin_id).with_suffix(suffix)
            if file_path.exists():
                response.append(file_path)
            else:
                # Case-insensitive check for file
                if config_dir.exists():
                    for item in config_dir.iterdir():
                        if item.is_file() and item.stem.lower() == plugin_id.lower() and item.suffix.lower() == suffix:
                            response.append(item)

        return [str(i) for i in response if not Path(i).stem.lower().endswith("_lang")]

    async def get_web_config(self):
        config = self.server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
        ai_api_key_value = config.get("ai_api_key", "")
        ai_api_key_configured = bool(ai_api_key_value and ai_api_key_value.strip())

        # Note: ChatLogger count logic is omitted here for brevity, should be handled via ChatService or similar
        return {
            "host": config["host"],
            "port": config["port"],
            "super_admin_account": config["super_admin_account"],
            "disable_admin_login_web": config["disable_other_admin"],
            "enable_temp_login_password": config["allow_temp_password"],
            "ai_api_key": "",
            "ai_api_key_configured": ai_api_key_configured,
            "ai_model": config.get("ai_model", "deepseek-chat"),
            "ai_api_url": config.get("ai_api_url", "https://api.deepseek.com/chat/completions"),
            "mcdr_plugins_url": config.get("mcdr_plugins_url",
                                           "https://api.mcdreforged.com/catalogue/everything_slim.json.xz"),
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
        }
