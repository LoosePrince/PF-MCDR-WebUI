"""
服务器管理相关的API函数
迁移自 web_server.py 中的服务器管理端点
"""

import datetime
import traceback

from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse

from guguwebui.structures import ServerControl
from guguwebui.utils.api_cache import api_cache
from guguwebui.constant import user_db
from guguwebui.utils.mc_util import get_java_server_info, get_server_port


async def get_server_status(
    request: Request,
    server=None
) -> JSONResponse:
    """获取服务器状态（使用短期缓存，5秒）"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    # 认证：允许管理员已登录，或携带有效的聊天会话ID
    permitted = False
    try:
        if request.session.get("logged_in"):
            permitted = True
        else:
            session_id = request.query_params.get("session_id", "")
            if session_id and session_id in user_db["chat_sessions"]:
                sess = user_db["chat_sessions"][session_id]
                try:
                    expire_time = datetime.datetime.fromisoformat(sess["expire_time"].replace('Z', '+00:00'))
                    if datetime.datetime.now(datetime.timezone.utc) <= expire_time:
                        permitted = True
                    else:
                        # 过期则清理
                        del user_db["chat_sessions"][session_id]
                        user_db.save()
                except Exception:
                    pass
    except Exception:
        pass

    if not permitted:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    # 尝试从缓存获取（5秒缓存）
    cache_key = "server_status"
    cached_result = api_cache.get(cache_key, ttl=5.0)
    if cached_result is not None:
        return JSONResponse(cached_result)

    # 缓存未命中，执行实际查询
    server_status = "online" if server.is_server_running() or server.is_server_startup() else "offline"

    # 获取MC服务器端口
    mc_port = get_server_port(server)

    server_message = await get_java_server_info(mc_port)

    server_version = server_message.get("server_version", "")
    version_string = f"Version: {server_version}" if server_version else ""

    # 玩家在线数与最大在线数
    player_count = server_message.get("server_player_count")
    max_player = server_message.get("server_maxinum_player_count")

    # 注意：原本用 `if player_count and max_player` 会把 0 在线玩家视为 False，
    # 导致前端收到空字符串又回退成 "0/0"。这里改为：
    # - 只要拿到了最大在线数，就显示 "当前在线数/最大在线数"
    # - 当前在线数拿不到时按 0 处理
    if max_player is not None:
        safe_player_count = player_count if isinstance(player_count, int) else 0
        player_string = f"{safe_player_count}/{max_player}"
    else:
        player_string = ""

    result = {
        "status": server_status,
        "version": version_string,
        "players": player_string,
    }

    # 存储到缓存（5秒）
    api_cache.set(cache_key, result, ttl=5.0)

    return JSONResponse(result)


async def control_server(
    request: Request,
    control_info: ServerControl,
    server=None
) -> JSONResponse:
    """控制Minecraft服务器"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    action = control_info.action

    allowed_actions = ["start", "stop", "restart"]
    if action not in allowed_actions:
        return JSONResponse(
            {"status": "error", "message": f"无效的操作: {action}，允许的操作: {', '.join(allowed_actions)}"},
            status_code=400
        )

    try:
        # 发送命令到MCDR
        server.execute_command(f"!!MCDR server {action}")

        # 根据操作返回对应的消息
        messages = {
            "start": "服务器启动命令已发送",
            "stop": "服务器停止命令已发送",
            "restart": "服务器重启命令已发送"
        }

        return JSONResponse({
            "status": "success",
            "message": messages[action]
        })
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"执行命令出错: {str(e)}"},
            status_code=500
        )


async def get_server_logs(
    request: Request,
    start_line: int = 0,
    max_lines: int = 100,
    server=None,
    log_watcher=None
) -> JSONResponse:
    """获取服务器日志"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    try:
        # 限制最大返回行数，防止过多数据导致性能问题
        if max_lines > 500:
            max_lines = 500

        # 获取合并日志
        result = log_watcher.get_merged_logs(max_lines)

        # 格式化合并日志内容
        formatted_logs = []
        for i, log in enumerate(result["logs"]):
            formatted_logs.append({
                "line_number": i,
                "content": log["content"],
                "source": log["source"],
                "counter": log.get("sequence_num", i)
            })

        return JSONResponse({
            "status": "success",
            "logs": formatted_logs,
            "total_lines": result["total_lines"],
            "current_start": result["start_line"],
            "current_end": result["end_line"]
        })

    except Exception as e:
        error_msg = f"获取日志失败: {str(e)}\n{traceback.format_exc()}"
        if server:
            server.logger.error(error_msg)
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )


async def get_new_logs(
    request: Request,
    last_counter: int = 0,
    max_lines: int = 100,
    server=None,
    log_watcher=None
) -> JSONResponse:
    """获取新增日志（基于计数器）"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    try:
        # 限制最大返回行数
        if max_lines > 200:
            max_lines = 200

        # 获取新增日志
        result = log_watcher.get_logs_since_counter(last_counter, max_lines)

        return JSONResponse({
            "status": "success",
            "logs": result["logs"],
            "total_lines": result["total_lines"],
            "last_counter": result["last_counter"],
            "new_logs_count": result["new_logs_count"]
        })

    except Exception as e:
        error_msg = f"获取新日志失败: {str(e)}\n{traceback.format_exc()}"
        if server:
            server.logger.error(error_msg)
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )


async def get_rcon_status(
    request: Request,
    server=None
) -> JSONResponse:
    """获取RCON连接状态（使用短期缓存，因为RCON状态可能随服务器状态改变）"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    try:
        # 检查是否已登录
        if not request.session.get("logged_in"):
            return JSONResponse(
                {"status": "error", "message": "User not logged in"},
                status_code=401
            )

        # 尝试从缓存获取（短期缓存，5秒）
        cache_key = "rcon_status"
        cached_result = api_cache.get(cache_key, ttl=5.0)
        if cached_result is not None:
            return JSONResponse(cached_result)

        # 缓存未命中，执行实际查询
        # 检查RCON是否启用和连接
        rcon_enabled = False
        rcon_connected = False
        rcon_info = {}

        # 读取MCDR配置检查RCON是否启用
        try:
            import ruamel.yaml
            from pathlib import Path
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
        if hasattr(server, "is_rcon_running") and server.is_rcon_running():
            rcon_connected = True

            # 尝试执行/list命令获取在线玩家信息
            try:
                feedback = server.rcon_query("list")
                rcon_info["list_response"] = feedback
                if isinstance(feedback, str) and ":" in feedback:
                    parts = feedback.split(":", 1)
                    if len(parts) == 2:
                        player_info = parts[1].strip()
                        rcon_info["player_info"] = player_info
            except Exception as e:
                rcon_info["error"] = str(e)

        result = {
            "status": "success",
            "rcon_enabled": rcon_enabled,
            "rcon_connected": rcon_connected,
            "rcon_info": rcon_info
        }

        # 存储到短期缓存（5秒）
        api_cache.set(cache_key, result, ttl=5.0)

        return JSONResponse(result)

    except Exception as e:
        error_msg = f"获取RCON状态失败: {str(e)}\n{traceback.format_exc()}"
        if server:
            server.logger.error(error_msg)
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )


from ..utils.mcdr_adapter import MCDRAdapter

async def get_command_suggestions(
    request: Request,
    input: str = "",
    server=None
) -> JSONResponse:
    """获取MCDR命令补全建议"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    try:
        # 获取根命令节点
        root_nodes = MCDRAdapter.get_root_nodes(server)

        # 命令建议列表
        suggestions = []

        # 将输入分割为命令部分
        parts = input.strip().split()

        # 检查输入是否以空格结尾，这表示用户需要子命令补全
        input_ends_with_space = input.endswith(' ')

        # 如果是空输入或者只有 !! 前缀，返回所有根命令
        if not parts or (len(parts) == 1 and parts[0].startswith("!!") and not input_ends_with_space):
            prefix = parts[0] if parts else ""
            # 收集所有以输入前缀开头的根命令
            for root_command in root_nodes.keys():
                if root_command.startswith(prefix):
                    suggestions.append({
                        "command": root_command,
                        "description": f"命令: {root_command}"
                    })
        # 如果是根命令后面跟空格，需要返回子命令
        elif len(parts) == 1 and parts[0] in root_nodes and input_ends_with_space:
            root_command = parts[0]
            # 遍历所有持有该根命令的插件
            for holder in root_nodes[root_command]:
                node = holder.node
                # 遍历根命令的所有子节点，返回所有可能的子命令
                for child in node.get_children():
                    # 字面量节点
                    if hasattr(child, "literals"):
                        for literal in child.literals:
                            suggestions.append({
                                "command": f"{root_command} {literal}",
                                "description": f"子命令: {literal}"
                            })
                    # 参数节点
                    elif hasattr(child, "get_name"):
                        param_name = child.get_name()
                        suggestions.append({
                            "command": f"{root_command} <{param_name}>",
                            "description": f"参数: {param_name}"
                        })
        # 否则尝试查找命令树中的补全
        else:
            # 当前输入的第一个部分（根命令）
            root_command = parts[0]

            # 查找匹配的根命令
            if root_command in root_nodes:
                # 遍历所有持有该根命令的插件
                for holder in root_nodes[root_command]:
                    node = holder.node
                    current_node = node

                    # 依次匹配输入的每个部分
                    matched = True
                    # 如果最后一部分不是完整的命令（没有空格结尾），只处理到倒数第二部分
                    process_until = len(parts) - (0 if parts[-1].strip() and input_ends_with_space else 1)

                    # 保存当前节点的路径，用于记录经过的参数节点
                    path_nodes = []

                    for i in range(1, process_until):
                        part = parts[i]
                        found = False

                        # 先尝试字面量节点匹配
                        for child in current_node.get_children():
                            # 字面量节点匹配
                            if hasattr(child, "literals"):
                                for literal in child.literals:
                                    if literal == part:  # 完全匹配
                                        current_node = child
                                        found = True
                                        path_nodes.append({"type": "literal", "node": child, "value": part})
                                        break
                                if found:
                                    break

                        # 如果字面量节点未匹配，尝试参数节点
                        if not found:
                            for child in current_node.get_children():
                                if hasattr(child, "get_name"):
                                    # 参数节点，记录参数名称和值
                                    current_node = child
                                    found = True
                                    path_nodes.append({
                                        "type": "argument",
                                        "node": child,
                                        "name": child.get_name(),
                                        "value": part
                                    })
                                    break

                        if not found:
                            matched = False
                            break

                    # 如果前面的部分都匹配，找最后一部分的补全建议
                    if matched:
                        # 获取最后一部分作为前缀
                        last_part = parts[-1] if len(parts) > 1 and not input_ends_with_space else ""

                        # 获取完整的命令前缀（不包括最后一部分）
                        prefix = " ".join(parts[:-1]) if last_part else " ".join(parts)
                        if prefix and not prefix.endswith(" "):
                            prefix += " "

                        # 如果输入以空格结尾，我们应该提供下一级的完整建议列表
                        if input_ends_with_space:
                            # 遍历当前节点的所有子节点，查找可能的补全
                            for child in current_node.get_children():
                                # 字面量节点
                                if hasattr(child, "literals"):
                                    for literal in child.literals:
                                        # 构建完整的命令补全
                                        full_command = prefix + literal
                                        suggestions.append({
                                            "command": full_command,
                                            "description": f"子命令: {literal}"
                                        })
                                # 参数节点
                                elif hasattr(child, "get_name"):
                                    param_name = child.get_name()
                                    # 构建带参数提示的命令补全
                                    full_command = prefix + f"<{param_name}>"
                                    suggestions.append({
                                        "command": full_command,
                                        "description": f"参数: {param_name}"
                                    })
                        else:
                            # 处理没有以空格结尾的情况，对最后一部分进行前缀匹配
                            # 遍历当前节点的所有子节点，查找可能的补全
                            for child in current_node.get_children():
                                # 字面量节点
                                if hasattr(child, "literals"):
                                    for literal in child.literals:
                                        # 如果最后部分为空，或者literal以最后部分开头，则添加为建议
                                        if not last_part or literal.startswith(last_part):
                                            # 构建完整的命令补全
                                            full_command = prefix + literal
                                            suggestions.append({
                                                "command": full_command,
                                                "description": f"子命令: {literal}"
                                            })
                                # 参数节点
                                elif hasattr(child, "get_name"):
                                    param_name = child.get_name()
                                    # 仅当最后部分为空或没有明确指定参数时才添加参数建议
                                    if not last_part or last_part.startswith("<"):
                                        # 构建带参数提示的命令补全
                                        full_command = prefix + f"<{param_name}>"
                                        suggestions.append({
                                            "command": full_command,
                                            "description": f"参数: {param_name}"
                                        })

                        # 如果最后一个参数有可能的匹配值（例如命令+参数情况下）
                        # 并且前一个节点是参数节点，尝试提供参数后的可能子命令
                        if input_ends_with_space and path_nodes and path_nodes[-1]["type"] == "argument":
                            # 假设用户已经输入了参数值，展示参数后可能的子命令
                            param_node = path_nodes[-1]["node"]
                            # 构建用于显示的完整命令前缀
                            param_prefix = prefix.strip()  # 移除末尾空格

                            # 遍历参数节点的子节点
                            for child in param_node.get_children():
                                if hasattr(child, "literals"):
                                    for literal in child.literals:
                                        # 添加参数后可能的子命令
                                        full_command = f"{param_prefix} {literal}"
                                        suggestions.append({
                                            "command": full_command,
                                            "description": f"子命令: {literal}"
                                        })
                                elif hasattr(child, "get_name"):
                                    # 参数节点后还有参数
                                    next_param_name = child.get_name()
                                    full_command = f"{param_prefix} <{next_param_name}>"
                                    suggestions.append({
                                        "command": full_command,
                                        "description": f"参数: {next_param_name}"
                                    })

        # 按命令字母排序
        suggestions.sort(key=lambda x: x["command"])

        # 限制返回数量，避免太多
        max_suggestions = 100
        if len(suggestions) > max_suggestions:
            suggestions = suggestions[:max_suggestions]

        return JSONResponse({
            "status": "success",
            "suggestions": suggestions,
            "input": input
        })

    except Exception as e:
        error_msg = f"获取命令补全失败: {str(e)}\n{traceback.format_exc()}"
        if server:
            server.logger.error(error_msg)
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )


async def send_command(
    request: Request,
    server=None
) -> JSONResponse:
    """发送命令到MCDR终端"""
    if not server:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "服务器接口未提供"}
        )

    try:
        # 获取请求体中的命令
        data = await request.json()
        command = data.get("command", "").strip()

        if not command:
            return JSONResponse(
                {"status": "error", "message": "Command cannot be empty"},
                status_code=400
            )

        # 检查是否为禁止的命令
        forbidden_commands = [
            '!!MCDR plugin reload guguwebui',
            '!!MCDR plugin unload guguwebui',
            'stop'
        ]
        if command in forbidden_commands:
            return JSONResponse(
                {"status": "error", "message": "该命令已被禁止执行"},
                status_code=403
            )

        # 输出到MCDR的日志
        server.logger.info(f"发送命令: {command}")

        # 处理以/开头的命令，尝试通过RCON发送
        if command.startswith("/"):
            # 去掉开头的/，因为RCON不需要
            mc_command = command[1:]

            # 检查RCON是否已连接
            if hasattr(server, "is_rcon_running") and server.is_rcon_running():
                try:
                    # 通过RCON发送命令并获取反馈
                    feedback = server.rcon_query(mc_command)
                    server.logger.info(f"RCON反馈: {feedback}")
                    return JSONResponse({
                        "status": "success",
                        "message": f"Command sent via RCON: {command}",
                        "feedback": feedback
                    })
                except Exception as e:
                    server.logger.error(f"RCON执行命令出错: {str(e)}")
                    # RCON执行失败，回退到普通方式执行
                    server.execute_command(command)
                    return JSONResponse({
                        "status": "success",
                        "message": f"Command sent (RCON failed): {command}",
                        "error": str(e)
                    })
            else:
                server.logger.info("RCON未启用，使用普通方式发送命令")

        # 普通方式执行命令
        server.execute_command(command)

        return JSONResponse({
            "status": "success",
            "message": f"Command sent: {command}"
        })
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Error sending command: {str(e)}"},
            status_code=500
        )
