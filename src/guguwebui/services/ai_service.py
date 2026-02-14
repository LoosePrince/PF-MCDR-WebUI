import json
from typing import Optional

import aiohttp

from guguwebui.structures import BusinessException


class AIService:
    def __init__(self, server, config_service=None):
        self.server = server
        self.config_service = config_service

    async def query(
        self,
        query: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ):
        """向 AI API 发送查询"""
        config = self.config_service.get_config() if self.config_service else {}

        api_key = api_key or config.get("ai_api_key", "")
        model = model or config.get("ai_model", "deepseek-chat")
        api_url = api_url or config.get(
            "ai_api_url", "https://api.deepseek.com/chat/completions"
        )
        system_prompt = system_prompt or config.get(
            "ai_system_prompt", "你是一个专业的 Minecraft 服务器管理员助手。"
        )

        if not api_key:
            raise BusinessException("未配置 AI API Key", status_code=400)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            "stream": False,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url, headers=headers, json=payload, timeout=60
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.server.logger.error(
                            f"AI API 请求失败: {response.status}, {error_text}"
                        )
                        raise BusinessException(
                            f"AI API 请求失败: {response.status}",
                            status_code=response.status,
                        )

                    result = await response.json()
                    return result
        except Exception as e:
            if isinstance(e, BusinessException):
                raise e
            self.server.logger.error(f"AI API 调用异常: {e}")
            raise BusinessException(f"AI API 调用异常: {str(e)}", status_code=500)
