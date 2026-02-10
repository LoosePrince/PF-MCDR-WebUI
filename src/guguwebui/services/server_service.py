from ..utils.mc_util import get_java_server_info, get_server_port


class ServerService:
    def __init__(self, server, log_watcher=None):
        self.server = server
        self.log_watcher = log_watcher

    async def get_server_status(self):
        cache_key = "server_status"
        cached_result = api_cache.get(cache_key, ttl=5.0)
        if cached_result is not None: return cached_result

        server_status = "online" if self.server.is_server_running() or self.server.is_server_startup() else "offline"

        # 获取MC服务器端口
        mc_port = get_server_port(self.server)

        server_message = await get_java_server_info(mc_port)
        player_count = server_message.get("server_player_count")
        max_player = server_message.get("server_maxinum_player_count")

        player_string = f"{player_count if player_count is not None else 0}/{max_player}" if max_player is not None else ""

        result = {
            "status": server_status,
            "version": f"Version: {server_message.get('server_version', '')}" if server_message.get('server_version') else "",
            "players": player_string,
        }
        api_cache.set(cache_key, result, ttl=5.0)
        return result

    def execute_action(self, action: str):
        allowed_actions = ["start", "stop", "restart"]
        if action not in allowed_actions: return False
        self.server.execute_command(f"!!MCDR server {action}")
        return True
