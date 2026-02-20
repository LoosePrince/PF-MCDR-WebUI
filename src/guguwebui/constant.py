from pathlib import Path

import ruamel.yaml
from passlib.context import CryptContext

from guguwebui.utils.table import Table

ALGORITHM = "HS256"
SECRET_KEY = "guguwebui"
STATIC_PATH = "./guguwebui_static"
USER_DB_PATH = Path(STATIC_PATH) / "db.json"
PATH_DB_PATH = Path("./config") / "guguwebui" / "config_path.json"

CSS_FILE = Path(STATIC_PATH) / "custom" / "overall.css"
JS_FILE = Path(STATIC_PATH) / "custom" / "overall.js"

# SERVER_PATH 读config.yml的 working_directory值
CONFIG_FILE_PATH = Path("./config.yml")
yaml = ruamel.yaml.YAML()
with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as config_file:
    config = yaml.load(config_file)
SERVER_PATH = Path(config.get("working_directory", "server"))

SERVER_PROPERTIES_PATH = SERVER_PATH / "server.properties"

# 仓库与项目链接
MCDR_OFFICIAL_CATALOGUE_URL = "https://api.mcdreforged.com/catalogue/everything_slim.json.xz"
PF_PLUGIN_CATALOGUE_URL = "https://pfingan-code.github.io/PluginCatalogue/plugins.json"
PROJECT_GITHUB_URL = "https://github.com/PFingan-Code/PF-MCDR-WebUI"
MCDR_SITE_URL = "https://mcdreforged.com"
MCDR_PLUGINS_PAGE_URL = "https://mcdreforged.com/zh-CN/plugins"

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# token: {token : {expire_time, user_name}}
# user : {username: password}
# temp : {temppassword: expire_time} 或 {temppassword: {expire_time: str, qq_id: str}} (新格式，如果关联了QQ号)
# chat_users: {player_id: {password: hashed_password, created_time: timestamp}}
# chat_verification: {code: {player_id: None, expire_time: timestamp, used: False}}
# chat_sessions: {session_id: {player_id: player_id, expire_time: timestamp}}
# qq_nicknames: {qq_id: nickname} - QQ号到昵称的映射
DEFALUT_DB = {
    "token": {},
    "user": {},
    "temp": {},
    "chat_users": {},
    "chat_verification": {},
    "chat_sessions": {},
    "qq_nicknames": {},
}
DEFALUT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8000,
    "super_admin_account": 123456789123456789,
    "disable_other_admin": False,
    "allow_temp_password": True,
    "force_standalone": False,  # 是否强制独立运行（忽略fastapi_mcdr插件）
    "ai_api_key": "",  # AI API密钥
    "ai_model": "deepseek-chat",  # AI模型名称
    "ai_api_url": "https://api.deepseek.com/chat/completions",  # 自定义API链接
    "mcdr_plugins_url": MCDR_OFFICIAL_CATALOGUE_URL,  # MCDR插件目录URL
    "repositories": [],  # 多仓库配置列表
    "ssl_enabled": False,  # 是否启用HTTPS
    "ssl_certfile": "",  # SSL证书文件路径
    "ssl_keyfile": "",  # SSL密钥文件路径
    "ssl_keyfile_password": "",  # SSL密钥文件密码（如果有）
    "public_chat_enabled": False,  # 是否启用公开聊天页
    "public_chat_to_game_enabled": False,  # 公开聊天页发送消息到游戏
    "chat_verification_expire_minutes": 10,  # 聊天页验证码过期时间（分钟）
    "chat_session_expire_hours": 24,  # 聊天页会话过期时间（小时）
    "icp_records": []  # ICP备案信息，最多两个，每个包含 icp 和 url 字段
    # 示例配置（请在 config.json 中添加）：
    # "icp_records": [
    #     {"icp": "浙ICP备12345678号", "url": "https://beian.miit.gov.cn/"},
    #     {"icp": "浙公网安备33010602000123号", "url": "https://www.beian.gov.cn/"}
    # ]
}

user_db = Table(USER_DB_PATH, default_content=DEFALUT_DB)

# 已注册的插件网页列表 (插件ID: HTML文件相对于插件config目录的路径)
REGISTERED_PLUGIN_PAGES: dict[str, str] = {}
