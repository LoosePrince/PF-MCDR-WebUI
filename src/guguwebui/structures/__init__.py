from typing import Optional

from pydantic import BaseModel


class LoginData(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    remember: Optional[bool] = False


class SaveConfig(BaseModel):
    action: str
    host: Optional[str] = None
    port: Optional[str] = None
    super_account: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None
    ai_api_url: Optional[str] = None
    mcdr_plugins_url: Optional[str] = None
    repositories: Optional[list] = None
    ssl_enabled: Optional[bool] = None
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
    ssl_keyfile_password: Optional[str] = None
    public_chat_enabled: Optional[bool] = None
    public_chat_to_game_enabled: Optional[bool] = None
    chat_verification_expire_minutes: Optional[int] = None
    chat_session_expire_hours: Optional[int] = None
    force_standalone: Optional[bool] = None
    icp_records: Optional[list] = None


class ToggleConfig(BaseModel):
    plugin_id: str
    status: bool


class SaveContent(BaseModel):
    action: str
    content: str


class PluginInfo(BaseModel):
    plugin_id: str


class ConfigData(BaseModel):
    file_path: str
    config_data: dict


class ServerControl(BaseModel):
    action: str


class DeepseekQuery(BaseModel):
    query: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
