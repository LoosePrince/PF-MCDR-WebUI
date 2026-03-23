# WebUI 事件系统文档

## 概述

WebUI 提供 **LiteralEvent** 事件与 **侧边栏注册** 扩展点，供其他 MCDR 插件：

- **事件系统**：如 `webui.chat_message_sent`（聊天）
- **侧边栏注册**：在 WebUI 侧边栏「插件网页」中注册自定义页面入口，并在可选情况下注册 `/api/plugin/{plugin_id}/...` 后端处理器

**持久化（MCDR 进程内）**：`init_app` 会把注册表绑定到 **MCDR 的 `PluginServerInterface` 实例**（属性名 `_guguwebui_registered_plugin_pages`）。仅重载 `guguwebui` 时 **不会** 丢失其它插件已注册的 `html_path` 与 `api_handler` 引用（同一 MCDR 进程、同一 `server` 对象）。

与 HTTP API 相关的路径、权限与 `api_handler` 约定见 **`docs/WebApi.md`**（「插件后端 API 代理」「获取已注册的插件网页列表」等）。

本功能会持续演进，请以仓库内实现为准。

---

## 可用事件

### `webui.chat_message_sent`

**事件类型**：`LiteralEvent("webui.chat_message_sent")`（`from mcdreforged.api.event import LiteralEvent`）

**触发时机**（两处实现，负载结构一致为 **长度为 6 的元组**）：

1. **公开聊天页**：玩家在 WebUI 中发送消息到游戏时，由 `ChatService.send_message` 在通过校验且将发往游戏（或仅落库）之前分发。  
   - 实现：`src/guguwebui/services/chat_service.py`
2. **其它插件调用 `send_message_to_webui`**：在广播到游戏与写入聊天日志之前分发。  
   - 实现：`src/guguwebui/utils/mc_util.py` 中 `send_message_to_webui`

**事件负载（元组下标与含义）**：

| 索引 | WebUI 聊天发送 | `send_message_to_webui`（插件） |
|------|----------------|----------------------------------|
| `[0]` | 固定字符串 `"webui"` | 插件传入的 `source`（插件名/来源标识） |
| `[1]` | 游戏内玩家 ID（`player_id`） | **再次为** `source`（与 `[0]` 相同） |
| `[2]` | 玩家 UUID 字符串，解析失败时为 `"未知"` | 固定为 `f"plugin_{source}"`（占位，非 Mojang UUID） |
| `[3]` | 用户输入的纯文本消息 | `processed_message`（纯文本或 RText 转字符串/JSON 后的展示串） |
| `[4]` | 聊天会话 `session_id` | 固定为 `f"plugin_{source}"`（占位，非 WebUI session） |
| `[5]` | `int(time.time())`（Unix 秒） | `int(datetime.now(timezone.utc).timestamp())`（Unix 秒） |

**说明**：

- 插件路径下 `[0]`、`[1]` 均为 `source`，便于与 WebUI 路径统一按「发送方标识」读取；若需区分两条路径，请判断 `[0] == "webui"`。
- WebUI 侧 `[5]` 使用 `time.time()`，插件侧使用 UTC `datetime` 时间戳；均为 Unix 秒。
- 消息写入聊天日志、RText 广播等逻辑在事件分发**之后**执行；监听器内请勿假设日志中已可见该条消息。

---

## 监听示例

```python
from mcdreforged.api.event import LiteralEvent


def on_webui_chat_message(server, event):
    # MCDR 将事件负载作为第二个参数传入；此处为 6 元组
    src, pid, puuid, text, sess, ts = event
    if src == "webui":
        server.logger.info(f"[WebUI] {pid}: {text}")
    else:
        server.logger.info(f"[Plugin:{src}] {text}")


def on_load(server, old):
    server.register_event_listener(
        LiteralEvent("webui.chat_message_sent"),
        on_webui_chat_message,
    )
```

具体监听器参数形式以当前 MCDR 版本为准；若第二参数为元组，按上表解包即可。

---

## 向 WebUI 发送消息：`send_message_to_webui`

其它插件应通过 **WebUI 插件模块** 上的入口调用（与 `register_plugin_page` 相同，使用 `server.get_plugin_instance("guguwebui")` 获取实例后调用模块级函数），以避免硬编码包内路径。

### 推荐调用方式

```python
from mcdreforged.api.types import PluginServerInterface

def on_load(server: PluginServerInterface, old):
    webui = server.get_plugin_instance("guguwebui")
    if webui is None:
        return
    if hasattr(webui, "send_message_to_webui"):
        webui.send_message_to_webui(
            server_interface=server,
            source="your_plugin_id",
            message="纯文本或 RText",
            message_type="info",
        )
```

### 函数签名（`guguwebui.__init__.py`）

```text
send_message_to_webui(
    server_interface,
    source: str,
    message,
    message_type: str = "info",
    target_players: list = None,
    metadata: dict = None,
    is_rtext: bool = False,
) -> bool
```

| 参数 | 说明 |
|------|------|
| `server_interface` | MCDR `PluginServerInterface` |
| `source` | 来源标识，会出现在事件 `[0]`、`[1]` 及游戏内展示逻辑中 |
| `message` | 字符串、RText 对象、或 RText JSON（`dict`/`list`/`str`） |
| `message_type` | 保留参数，当前实现未参与分支逻辑 |
| `target_players` | **当前实现未使用**，保留兼容 |
| `metadata` | **当前实现未使用**，保留兼容 |
| `is_rtext` | `True` 时按 RText 解析（`to_json_object` / JSON / `create_rtext_from_data`） |

**返回值**：成功为 `True`，异常为 `False`。

**行为概要**（`mc_util.send_message_to_webui`）：

1. 构造 RText 并 **分发** `webui.chat_message_sent`
2. **`server_interface.broadcast(rtext_message)`** 同步到游戏内聊天
3. 写入 WebUI 聊天日志（`ChatLogger`，`message_type=2` 表示插件来源）

### RText 与 JSON

- `is_rtext=True` 且 `message` 为 MCDR RText / 可 `to_json_object()`：生成 JSON 用于日志与展示。
- `is_rtext=True` 且为 `dict`/`list`：作为 JSON 组件树处理。
- `is_rtext=True` 且为 `str`：尝试 `json.loads` 为 RText 数据，失败则退化为纯文本。

JSON 组件字段（`clickEvent` / `hoverEvent` / `extra` 等）与前端解析见 `guguwebui.utils.mc_util` 与 `frontend` 内 RText 解析逻辑。

---

## 注册插件网页：`register_plugin_page`

```python
def register_plugin_page(
    plugin_id: str,
    html_path: str,
    *,
    name: Optional[str] = None,
    api_handler: Optional[Callable[..., Any]] = None,
    upload_max_bytes: Optional[int] = None,
) -> None
```

- **`plugin_id`**：侧边栏与前端路由 `/plugin-page/<plugin_id>` 使用的标识，建议与 `mcdreforged.plugin.json` 的 `id` 一致。
- **`html_path`**：HTML 文件的**绝对路径**，或相对 **`config` 目录**的路径（见 `guguwebui.__init__` 文档字符串）。实际打开时会经 `SafePath.get_safe_path` 与 `get_base_dirs` 校验，禁止越权路径。
- **`name`**：可选。用于侧边栏与页面标题的友好显示名称；不传则回退为 `plugin_id`。
- **`api_handler`**：可选。已登录用户访问 `/api/plugin/{plugin_id}/...` 时由 WebUI 转发，签名与返回值见 **`docs/WebApi.md`**。
- **`upload_max_bytes`**：可选。该插件单文件上传上限（字节）；不传则使用全局默认值（当前为 1 MiB）。

前端行为简述：

1. `GET /api/plugins/web_pages` 拉取 `{ id, path }` 列表（需登录）。
   - 若注册了 `name`，则响应包含 `name` 字段，侧边栏优先显示 `name`，否则回退显示 `id`。
2. 侧栏链接打开 `/plugin-page/:pluginId`（React 路由）。
3. 页面内再请求 `/api/load_config?path=<注册的 path>&type=auto`；若同目录存在 **`main.json`**，且其中 **以当前文件名为 key** 映射到同目录下另一 `.html`，则加载映射目标文件；否则直接读取该路径对应 HTML。

iframe 使用 `srcDoc` 注入 HTML 内容（见 `frontend/src/pages/PluginPage.tsx`）。

---

## 其它说明

1. **加载顺序**：请在 WebUI 插件已加载后再调用 `register_plugin_page` / `send_message_to_webui`；若 `get_plugin_instance("guguwebui")` 为 `None`，应跳过或延迟重试。
2. **WebUI 重载**：注册表已绑定到 `server`，一般无需在重载后再次注册；若仍丢失，请检查是否在 `init_app` 前注册。
3. **重复注册**：同一 `plugin_id` 会覆盖 `REGISTERED_PLUGIN_PAGES` 中的页面与 `api_handler`。
4. **事件与异常**：监听器内异常可能影响 MCDR 事件分发行为，请自行 try/except；不要假设「其它插件监听器一定与本插件错误隔离」。
5. **时间戳**（`webui.chat_message_sent`）：事件 `[5]` 为 Unix 秒；WebUI 与插件路径取值方式略有不同，见上表。
6. **多服面板**：主服对子服的 API 代理不改变 LiteralEvent 的订阅方式；事件仅在执行 `dispatch_event` 的 **当前 MCDR 进程** 内触发。
