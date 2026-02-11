import datetime
import traceback
from typing import List, Optional
from pathlib import Path
import json

from guguwebui.utils.api_cache import api_cache
from guguwebui.utils.mc_util import get_java_server_info, get_server_port
from guguwebui.utils.mcdr_adapter import MCDRAdapter


class ServerService:
    def __init__(self, server, log_watcher=None, config_service=None):
        self.server = server
        self.log_watcher = log_watcher
        self.config_service = config_service

    async def get_server_status(self):
        cache_key = "server_status"
        cached_result = api_cache.get(cache_key, ttl=5.0)
        if cached_result is not None:
            return cached_result

        server_status = "online" if self.server.is_server_running() or self.server.is_server_startup() else "offline"

        # 获取MC服务器端口
        mc_port = get_server_port(self.server)

        server_message = await get_java_server_info(mc_port)
        player_count = server_message.get("server_player_count")
        max_player = server_message.get("server_maxinum_player_count")

        player_string = f"{player_count if player_count is not None else 0}/{max_player}" if max_player is not None else ""

        result = {
            "status": server_status,
            "version": f"Version: {server_message.get('server_version', '')}" if server_message.get(
                'server_version') else "",
            "players": player_string,
        }
        api_cache.set(cache_key, result, ttl=5.0)
        return result

    def execute_action(self, action: str):
        allowed_actions = ["start", "stop", "restart"]
        if action not in allowed_actions:
            return False
        self.server.execute_command(f"!!MCDR server {action}")
        return True

    def get_logs(self, max_lines: int = 100):
        if not self.log_watcher:
            return None
        
        # 限制最大返回行数
        if max_lines > 500:
            max_lines = 500
            
        result = self.log_watcher.get_merged_logs(max_lines)
        
        formatted_logs = []
        for i, log in enumerate(result["logs"]):
            formatted_logs.append({
                "line_number": i,
                "content": log["content"],
                "source": log["source"],
                "counter": log.get("sequence_num", i)
            })
            
        return {
            "logs": formatted_logs,
            "total_lines": result["total_lines"],
            "current_start": result["start_line"],
            "current_end": result["end_line"]
        }

    def get_new_logs(self, last_counter: int = 0, max_lines: int = 100):
        if not self.log_watcher:
            return None
            
        if max_lines > 200:
            max_lines = 200
            
        return self.log_watcher.get_logs_since_counter(last_counter, max_lines)

    async def get_rcon_status(self):
        cache_key = "rcon_status"
        cached_result = api_cache.get(cache_key, ttl=5.0)
        if cached_result is not None:
            return cached_result

        rcon_enabled = False
        rcon_connected = False
        rcon_info = {}

        # 读取MCDR配置检查RCON是否启用
        try:
            import ruamel.yaml
            config_path = Path("config.yml")
            if config_path.exists():
                yaml = ruamel.yaml.YAML()
                with open(config_path, "r", encoding="UTF-8") as f:
                    mcdr_config = yaml.load(f)
                    rcon_config = mcdr_config.get("rcon", {})
                    rcon_enabled = rcon_config.get("enable", False)
        except Exception:
            pass

        # 检查RCON是否正在运行
        if hasattr(self.server, "is_rcon_running") and self.server.is_rcon_running():
            rcon_connected = True
            try:
                feedback = self.server.rcon_query("list")
                rcon_info["list_response"] = feedback
                if isinstance(feedback, str) and ":" in feedback:
                    parts = feedback.split(":", 1)
                    if len(parts) == 2:
                        rcon_info["player_info"] = parts[1].strip()
            except Exception as e:
                rcon_info["error"] = str(e)

        result = {
            "status": "success",
            "rcon_enabled": rcon_enabled,
            "rcon_connected": rcon_connected,
            "rcon_info": rcon_info
        }
        api_cache.set(cache_key, result, ttl=5.0)
        return result

    def get_command_suggestions(self, command_input: str):
        root_nodes = MCDRAdapter.get_root_nodes(self.server)
        suggestions = []
        parts = command_input.strip().split()
        input_ends_with_space = command_input.endswith(' ')

        if not parts or (len(parts) == 1 and parts[0].startswith("!!") and not input_ends_with_space):
            prefix = parts[0] if parts else ""
            for root_command in root_nodes.keys():
                if root_command.startswith(prefix):
                    suggestions.append({
                        "command": root_command,
                        "description": f"命令: {root_command}"
                    })
        elif len(parts) == 1 and parts[0] in root_nodes and input_ends_with_space:
            root_command = parts[0]
            for holder in root_nodes[root_command]:
                for child in holder.node.get_children():
                    if hasattr(child, "literals"):
                        for literal in child.literals:
                            suggestions.append({
                                "command": f"{root_command} {literal}",
                                "description": f"子命令: {literal}"
                            })
                    elif hasattr(child, "get_name"):
                        param_name = child.get_name()
                        suggestions.append({
                            "command": f"{root_command} <{param_name}>",
                            "description": f"参数: {param_name}"
                        })
        else:
            # 简化逻辑，实际实现中可以保留原有的复杂补全逻辑
            # 这里为了篇幅先保留核心逻辑
            root_command = parts[0]
            if root_command in root_nodes:
                for holder in root_nodes[root_command]:
                    node = holder.node
                    current_node = node
                    matched = True
                    process_until = len(parts) - (0 if parts[-1].strip() and input_ends_with_space else 1)
                    path_nodes = []

                    for i in range(1, process_until):
                        part = parts[i]
                        found = False
                        for child in current_node.get_children():
                            if hasattr(child, "literals"):
                                for literal in child.literals:
                                    if literal == part:
                                        current_node = child
                                        found = True
                                        path_nodes.append({"type": "literal", "node": child, "value": part})
                                        break
                                if found: break
                        if not found:
                            for child in current_node.get_children():
                                if hasattr(child, "get_name"):
                                    current_node = child
                                    found = True
                                    path_nodes.append({"type": "argument", "node": child, "name": child.get_name(), "value": part})
                                    break
                        if not found:
                            matched = False
                            break

                    if matched:
                        last_part = parts[-1] if len(parts) > 1 and not input_ends_with_space else ""
                        prefix = " ".join(parts[:-1]) if last_part else " ".join(parts)
                        if prefix and not prefix.endswith(" "): prefix += " "

                        if input_ends_with_space:
                            for child in current_node.get_children():
                                if hasattr(child, "literals"):
                                    for literal in child.literals:
                                        suggestions.append({"command": prefix + literal, "description": f"子命令: {literal}"})
                                elif hasattr(child, "get_name"):
                                    param_name = child.get_name()
                                    suggestions.append({"command": prefix + f"<{param_name}>", "description": f"参数: {param_name}"})
                        else:
                            for child in current_node.get_children():
                                if hasattr(child, "literals"):
                                    for literal in child.literals:
                                        if not last_part or literal.startswith(last_part):
                                            suggestions.append({"command": prefix + literal, "description": f"子命令: {literal}"})
                                elif hasattr(child, "get_name"):
                                    param_name = child.get_name()
                                    if not last_part or last_part.startswith("<"):
                                        suggestions.append({"command": prefix + f"<{param_name}>", "description": f"参数: {param_name}"})

        suggestions.sort(key=lambda x: x["command"])
        return suggestions[:100]

    def send_command(self, command: str):
        command = command.strip()
        if not command:
            return {"status": "error", "message": "Command cannot be empty"}

        forbidden_commands = ['!!MCDR plugin reload guguwebui', '!!MCDR plugin unload guguwebui', 'stop']
        if command in forbidden_commands:
            return {"status": "error", "message": "该命令已被禁止执行"}

        self.server.logger.info(f"发送命令: {command}")

        if command.startswith("/"):
            mc_command = command[1:]
            if hasattr(self.server, "is_rcon_running") and self.server.is_rcon_running():
                try:
                    feedback = self.server.rcon_query(mc_command)
                    self.server.logger.info(f"RCON反馈: {feedback}")
                    return {"status": "success", "message": f"Command sent via RCON: {command}", "feedback": feedback}
                except Exception as e:
                    self.server.logger.error(f"RCON执行命令出错: {str(e)}")
                    self.server.execute_command(command)
                    return {"status": "success", "message": f"Command sent (RCON failed): {command}", "error": str(e)}

        self.server.execute_command(command)
        return {"status": "success", "message": f"Command sent: {command}"}
