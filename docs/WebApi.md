# MCDR WebUI API 文档

本文档记录 MCDR WebUI 前端界面使用的 API 接口，并与当前代码实现对齐。若与实际接口有差异，以服务端实现为准。

## 通用约定

### HTTP 状态与错误体

- **401 Unauthorized**：未登录或会话无效。常见 body：`{"detail": "User not logged in"}`（FastAPI `HTTPException`）。
- **403 Forbidden**：已登录但非管理员（`get_current_admin`），或子服场景下其它禁止访问的原因。常见 body：`{"detail": "Admin access required"}`。
- **业务异常**（`BusinessException`）：`{"status": "error", "message": "...", "data": ...}`，`data` 可选。
- **未实现的 API 路径**（`/api/*`）：`{"status": "error", "message": "API endpoint not found"}`，状态码 404。

### 认证方式

1. **浏览器会话**：Cookie `token` + Session `logged_in` / `username`（与多数页面一致）。
2. **子服模式（`panel_role` 为 `slave`）**：主服或自动化请求可携带请求头 **`X-Panel-Token`**，值为子服 `config.json` 中 `panel_master.allowed_tokens` 里已启用项的 `token`。可选配合 **`allowed_master_ips`** 限制来源 IP。通过该方式认证时，用户名为 `__panel__`，管理员校验对 Panel Token 会放行（权限由主服侧控制）。

### 多服面板代理（主服）

当主服配置为 `panel_role: master` 且存在子服时，对**可代理**的 `/api/*` 请求可指定目标：

- 请求头 **`X-Target-Server`**：子服 `id`（与 `panel_slaves[].id` 一致），或使用查询参数 **`serverId`**（转发时会从出站查询中去掉 `serverId`，避免重复）。
- 未指定或 `local` 表示当前实例本地执行。

**始终仅在主服本地处理、不代理**的示例：`/api/login`、`/api/logout`、`/api/checkLogin`、`/api/servers`、`/api/panel_merge_config`、`/api/langs`、`/api/online-plugins`、以及路径前缀 `/api/pairing/`。详见 `guguwebui/panel_merge/proxy.py` 中 `is_proxy_candidate_path`。

### 前端页面（非 API）

以下路径由服务端返回 React SPA 的 `index.html`（具体权限与 `web_server.py` 中 `Depends` 一致），例如：`GET /login`、`/index`、`/home`、`/mc`、`/mcdr`、`/plugins`、`/online-plugins`、`/settings`、`/about`、`/terminal`、`/chat`、`/player-chat` 等。非 `/api/*` 的未知路径多数也会回退到 SPA 由前端路由处理 404。

---

## 认证相关API

### 检查登录状态
- 端点: `/api/checkLogin`
- 方法: GET
- 功能: 校验当前会话；**仅当已登录时**返回成功 JSON。未登录不会返回 `status: error`，而是 **HTTP 401**。
- 权限: 需有效登录会话（或子服 `X-Panel-Token`）。
- 响应（200）: 

  ```json
  {
    "status": "success",
    "username": "用户名或账号",
    "nickname": null
  }
  ```

  `nickname` 为在 `user_db.qq_nicknames` 中配置的 QQ 昵称；无则为 `null`。

- 调用示例:

  ```javascript
  async function checkLoginStatus() {
    try {
      const response = await fetch('/api/checkLogin');
      if (response.status === 401) {
        console.log('未登录');
        return;
      }
      const data = await response.json();
      if (data.status === 'success') {
        console.log(`已登录，用户名: ${data.username}`, data.nickname);
      }
    } catch (error) {
      console.error('检查登录状态出错:', error);
    }
  }
  ```

- 使用位置: 所有需要认证的页面

### 登录
- 端点: `/api/login`（提交登录请求）
- 方法: POST
- 参数: 
  - `account`: 账号（表单字段）
  - `password`: 密码（表单字段）
  - `temp_code`: 临时登录码（可选，表单字段）
  - `remember`: 是否记住登录状态（表单字段）
- 功能: 用户登录。登录页面为 GET `/login`。
- 响应:
  - 成功时：重定向到首页或指定的 redirect 地址
  - 失败时：返回错误信息
- 调用示例（表单提交）:

  ```html
  <form action="/api/login" method="post">
    <input type="text" name="account" placeholder="账号" required>
    <input type="password" name="password" placeholder="密码" required>
    <input type="checkbox" name="remember" value="true"> 记住我
    <button type="submit">登录</button>
  </form>
  ```

- 使用位置: 登录页面

### 登出
- **页面登出**
  - 端点: `/logout`
  - 方法: GET
  - 功能: 清除会话并 **302 重定向** 到登录页（`get_redirect_url`）。
- **API 登出**
  - 端点: `/api/logout`
  - 方法: POST
  - 功能: 清除会话，返回 JSON（适合 SPA / `fetch`）。
  - 响应示例: `{"status": "success", "message": "Logged out"}`

- 调用示例:

  ```javascript
  function logoutPage() {
    window.location.href = '/logout';
  }

  async function logoutApi() {
    const r = await fetch('/api/logout', { method: 'POST', credentials: 'include' });
    return r.json();
  }
  ```

- 使用位置: 所有页面的退出登录按钮

### 获取语言列表
- 端点: `/api/langs`
- 方法: GET
- 功能: 获取前端可用的语言列表（来自 `/lang` 目录下的 JSON 文件及显示名）。无需登录。
- 响应: 数组，每项为 `{"code": "语言代码", "name": "显示名称"}`；异常时返回 `{"error": "错误信息"}`，状态码 500。

  ```json
  [
    {"code": "zh-CN", "name": "中文"},
    {"code": "en-US", "name": "English"}
  ]
  ```

- 使用位置: 前端语言切换、设置页

## 服务器状态API

### 获取服务器状态
- 端点: `/api/get_server_status`
- 方法: GET
- 功能: 获取 Minecraft 服务器运行状态与版本/玩家摘要。需登录。
- 响应: 成功时 HTTP 200，body 由 `ServerService.get_server_status()` 展开后再与外层合并；**顶层字段 `status` 表示服务器在线状态**（`online` / `offline`），不是固定的 `"success"`。

  ```json
  {
    "status": "online|offline",
    "version": "Version: ...",
    "players": "当前/最大 或空字符串"
  }
  ```

- 调用示例:

  ```javascript
  async function checkServerStatus() {
    try {
      const response = await fetch('/api/get_server_status');
      const data = await response.json();
      
      if (data.status === 'online') {
        console.log(`服务器在线，版本: ${data.version}, 玩家: ${data.players}`);
      } else if (data.status === 'offline') {
        console.log('服务器离线');
      } else {
        console.log('未知状态:', data.status);
      }
    } catch (error) {
      console.error('检查服务器状态出错:', error);
    }
  }
  ```

- 使用位置: 首页、控制面板

### 控制服务器
- 端点: `/api/control_server`
- 方法: POST
- 参数:
  - `action`: 操作类型（"start"/"stop"/"restart"）
- 功能: 启动、停止或重启Minecraft服务器
- 响应:

  ```json
  {
    "status": "success|error",
    "message": "操作结果信息"
  }
  ```

- 调用示例:

  ```javascript
  async function controlServer(action) {
    try {
      const response = await fetch('/api/control_server', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ action: action })
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        console.log(`服务器${action}命令已发送: ${result.message}`);
      } else {
        console.error(`操作失败: ${result.message}`);
      }
    } catch (error) {
      console.error('控制服务器出错:', error);
    }
  }
  
  // 使用示例
  // controlServer('start');   // 启动服务器
  // controlServer('stop');    // 停止服务器
  // controlServer('restart'); // 重启服务器
  ```

- 使用位置: 服务器控制面板

### 获取服务器日志
- 端点: `/api/server_logs`
- 方法: GET
- 参数:
  - `start_line`: 查询参数仍存在，**当前服务端实现未传入日志逻辑，实际被忽略**（保留兼容）；分页请以返回的 `current_start` / `current_end` 与 `total_lines` 为准或配合 `/api/new_logs`。
  - `max_lines`: 最大返回行数（默认 100，最大 500）
- 功能: 获取合并后的服务器日志（MCDR + Minecraft）。需登录。
- 响应:

  ```json
  {
    "status": "success|error",
    "logs": [
      {
        "line_number": 0,
        "content": "日志内容",
        "source": "mcdr|minecraft",
        "counter": 计数器ID
      }
    ],
    "total_lines": 总行数,
    "current_start": 开始行号,
    "current_end": 结束行号
  }
  ```

- 调用示例:

  ```javascript
  async function getServerLogs(startLine = 0, maxLines = 100) {
    try {
      const params = new URLSearchParams({
        start_line: startLine,
        max_lines: maxLines
      });
      
      const response = await fetch(`/api/server_logs?${params.toString()}`);
      const data = await response.json();
      
      if (data.status === 'success') {
        console.log(`获取到 ${data.logs.length} 行日志`);
        console.log(`总行数: ${data.total_lines}`);
        // 处理日志
        data.logs.forEach(log => {
          console.log(`${log.line_number}: ${log.content}`);
        });
      } else {
        console.error('获取日志失败');
      }
    } catch (error) {
      console.error('获取服务器日志出错:', error);
    }
  }
  ```

- 使用位置: 日志查看页面
- 备注: 返回的日志为 MCDR 与 Minecraft 合并结果，每条包含 `source` 字段标识来源

### 获取最新日志更新
- 端点: `/api/new_logs`
- 方法: GET
- 参数:
  - `last_counter`: 客户端已有的最后一行计数器 ID（`counter`）
  - `max_lines`: 最大返回行数（默认 100，最大 200）
- 功能: 自 `last_counter` 之后增量拉取日志，用于轮询刷新。需登录。
- 响应（成功时 `status` 为 `"success"`，以下为 `LogWatcher.get_logs_since_counter` 合并后的结构）:

  ```json
  {
    "status": "success",
    "logs": [
      {
        "line_number": 0,
        "counter": 123,
        "timestamp": "2025-01-01 12:00:00",
        "content": "日志行文本\\n",
        "source": "all",
        "is_command": false
      }
    ],
    "total_lines": 总行数,
    "last_counter": 最后一行计数器ID,
    "new_logs_count": 新增条数
  }
  ```

- 调用示例:

  ```javascript
  async function fetchNewLogs(lastCounter, maxLines = 100) {
    try {
      const response = await fetch(`/api/new_logs?last_counter=${lastCounter}&max_lines=${maxLines}`);
      const data = await response.json();
      
      if (data.status === 'success') {
        console.log(`获取到 ${data.new_logs_count} 行新日志`);
        // 处理新日志
        data.logs.forEach(log => {
          console.log(`${log.line_number}: ${log.content}`);
        });
        
        // 更新最后一行计数器ID
        return data.last_counter;
      }
      
      return lastCounter; // 没有新日志，返回原计数器ID
    } catch (error) {
      console.error('获取新日志出错:', error);
      return lastCounter;
    }
  }
  
  // 定时获取新日志
  let lastCounter = 0;
  setInterval(async () => {
    lastCounter = await fetchNewLogs(lastCounter);
  }, 3000);
  ```

- 使用位置: 日志实时监控页面
- 备注: 通常与`setInterval`配合使用，定期轮询获取新日志

## 插件管理API

### 获取插件列表
- 端点: `/api/plugins`
- 方法: GET
- 参数: 
  - `plugin_id`: 指定插件 ID（可选；提供时只返回至多一条）
- 功能: 获取已安装的插件列表。**必须登录**（或子服 `X-Panel-Token`）；未登录为 **401**。
- 响应:

  ```json
  {
    "status": "success",
    "plugins": [
      {
        "id": "插件ID",
        "name": "插件名称",
        "version": "插件版本",
        "description": "插件描述",
        "status": "loaded|unloaded|disabled",
        "author": "插件作者",
        "link": "插件链接",
        "dependencies": ["依赖插件列表"],
        "repository": "代码仓库地址"
      }
    ]
  }
  ```

- 调用示例:

  ```javascript
  // 获取所有插件
  async function getAllPlugins() {
    try {
      const response = await fetch('/api/plugins');
      const data = await response.json();
      
      if (data.plugins) {
        console.log(`获取到 ${data.plugins.length} 个插件`);
        // 处理插件列表
        data.plugins.forEach(plugin => {
          console.log(`${plugin.name} (${plugin.id}) - ${plugin.status}`);
        });
      } else {
        console.error('获取插件列表失败或未登录');
      }
    } catch (error) {
      console.error('获取插件列表出错:', error);
    }
  }

  // 获取指定插件
  async function getPluginById(pluginId) {
    try {
      const response = await fetch(`/api/plugins?plugin_id=${encodeURIComponent(pluginId)}`);
      const data = await response.json();
      
      if (data.plugins && data.plugins.length > 0) {
        const plugin = data.plugins[0];
        console.log(`插件信息: ${plugin.name} (${plugin.id}) - ${plugin.status}`);
        return plugin;
      } else {
        console.error('未找到指定插件或获取失败');
        return null;
      }
    } catch (error) {
      console.error('获取插件信息出错:', error);
      return null;
    }
  }
  ```

- 使用位置: 插件管理页面
- 备注: 接口始终返回详细信息，包括作者、链接等

### 获取在线插件目录（everything_slim 等）
- 端点: `/api/online-plugins`
- 方法: GET
- 查询参数: `repo_url`（可选，覆盖默认目录地址）
- 功能: 返回在线插件目录 JSON（由 `PluginService.get_online_plugins` 拉取并解析）。**需管理员**；多服场景下**不代理到子服**，始终请求主服本地。

### 获取咕咕机器人插件（已移除）
- 端点: `/api/gugubot_plugins`
- 状态: **已移除**。该接口已从当前版本中移除，请使用 `/api/plugins` 获取插件列表。

### 切换插件状态
- 端点: `/api/toggle_plugin`
- 方法: POST
- 参数: 
  - `plugin_id`: 插件ID
  - `status`: 目标状态（true为启用，false为禁用）
- 功能: 启用或禁用指定插件
- 响应:

  ```json
  {
    "status": "success|error",
    "message": "操作结果信息"
  }
  ```

- 调用示例:

  ```javascript
  async function togglePlugin(pluginId, enable) {
    try {
      const response = await fetch('/api/toggle_plugin', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          plugin_id: pluginId,
          status: enable
        })
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        console.log(`插件 ${pluginId} ${enable ? '已启用' : '已禁用'}: ${result.message}`);
      } else {
        console.error(`操作失败: ${result.message}`);
      }
    } catch (error) {
      console.error('切换插件状态出错:', error);
    }
  }
  
  // 使用示例
  // togglePlugin('example_plugin', true);  // 启用插件
  // togglePlugin('example_plugin', false); // 禁用插件
  ```

- 使用位置: 插件管理页面

### 重载插件
- 端点: `/api/reload_plugin`
- 方法: POST
- 参数: 
  - `plugin_id`: 插件ID
- 功能: 重新加载指定插件
- 响应:

  ```json
  {
    "status": "success|error",
    "message": "操作结果信息"
  }
  ```

- 调用示例:

  ```javascript
  async function reloadPlugin(pluginId) {
    try {
      const response = await fetch('/api/reload_plugin', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          plugin_id: pluginId
        })
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        console.log(`插件 ${pluginId} 已重载: ${result.message}`);
      } else {
        console.error(`重载失败: ${result.message}`);
      }
    } catch (error) {
      console.error('重载插件出错:', error);
    }
  }
  ```

- 使用位置: 插件管理页面

### 获取已注册的插件网页列表（侧边栏）
- 端点: `/api/plugins/web_pages`
- 方法: GET
- 功能: 获取所有通过 `register_plugin_page` 注册的插件网页列表，用于侧边栏「插件网页」展示。需登录。
- 响应:

  ```json
  {
    "status": "success",
    "pages": [
      {
        "id": "插件ID",
        "path": "HTML 文件路径"
      }
    ]
  }
  ```

  - 未登录时: **401**
- 使用位置: 布局侧边栏、插件网页入口

### 插件后端 API 代理（可选）

插件在调用 `register_plugin_page` 时可传入 `api_handler`，则 WebUI 将以下路径的请求转发给该处理器（需登录，与多数业务 API 一致）。

- **根路径（子路径为空）**
  - 端点: `/api/plugin/{plugin_id}`
  - 方法: `GET`、`POST`、`PUT`、`PATCH`、`DELETE`、`OPTIONS`、`HEAD`
- **带子路径**
  - 端点: `/api/plugin/{plugin_id}/{subpath}`
  - `subpath` 可含多级，例如 `abc` 或 `foo/bar`，对应处理器第一个参数 `url_path` 的字符串。

**处理器约定**（Python）：

- 签名为 `(url_path: str, params: dict) -> ...`
- `url_path`：去掉 `/api/plugin/{plugin_id}/` 前缀后的子路径；根路径请求时为 `""`。
- `params` 固定包含：
  - `method`：HTTP 方法字符串
  - `query`：查询参数，`dict[str, str | list[str]]`（同名多值为列表）
  - `body`：请求体；无体或未解析时为 `None`。支持 `application/json` 与 `application/x-www-form-urlencoded` / `multipart/form-data`（**不含文件上传**；含文件字段时返回 `415`）

**返回值**：可为 `starlette.responses.Response` 子类（原样返回），或可被 JSON 序列化的对象（封装为 JSON 响应）。

**错误**：

- 未注册 `api_handler` 或该 `plugin_id` 未注册页面：`404`
- 不支持的 `Content-Type`（非上述类型）：`415`
- JSON 体非法：`400`

**多服**：主服选中子服时，若请求经面板代理转发，子服本地执行对应插件的 `api_handler`（与 RCON 等一致）。

## 配置相关API

### 获取配置文件列表
- 端点: `/api/list_config_files`
- 方法: GET
- 参数: 
  - `plugin_id`: 插件ID
- 功能: 获取指定插件的配置文件列表
- 响应:

  ```json
  {
    "status": "success|error",
    "files": ["配置文件路径列表"],
    "message": "错误信息（如果失败）"
  }
  ```

- 调用示例:

  ```javascript
  async function getConfigFiles(pluginId) {
    try {
      const response = await fetch(`/api/list_config_files?plugin_id=${encodeURIComponent(pluginId)}`);
      const data = await response.json();
      
      if (data.status === 'success') {
        console.log(`获取到 ${data.files.length} 个配置文件`);
        // 处理文件列表
        data.files.forEach(file => {
          console.log(`配置文件: ${file}`);
        });
        return data.files;
      } else {
        console.error(`获取配置文件列表失败: ${data.message}`);
        return [];
      }
    } catch (error) {
      console.error('获取配置文件列表出错:', error);
      return [];
    }
  }
  ```

- 使用位置: 插件配置页面

### 加载配置文件
- 端点: `/api/load_config`
- 方法: GET
- 参数: 
  - `path`: 配置文件路径
  - `translation`: 是否需要翻译（可选，布尔值）
  - `type`: 配置类型（可选，默认为"auto"）
- 功能: 加载指定配置文件内容
- 使用位置: 配置编辑页面

### 保存配置文件
- 端点: `/api/save_config`
- 方法: POST
- 参数（JSON body）: 
  - `file_path`: 配置文件路径（字符串）
  - `config_data`: 配置内容（对象）
- 功能: 保存指定路径的配置文件。禁止通过此接口修改 `config\guguwebui\config.json`。
- 响应: `{"status": "success"}` 或 `{"status": "error", "message": "..."}`
- 使用位置: 配置编辑页面

### 加载配置文件内容
- 端点: `/api/load_config_file`
- 方法: GET
- 参数: 
  - `path`: 配置文件路径
- 功能: 加载指定配置文件的原始内容
- 响应: 文件内容（纯文本）
- 使用位置: 配置编辑页面

### 保存配置文件内容
- 端点: `/api/save_config_file`
- 方法: POST
- 参数（JSON body）: 
  - `action`: 文件路径（字符串）
  - `content`: 文件内容（字符串）
- 功能: 保存配置文件原始内容。禁止通过此接口修改 `config\guguwebui\config.json`。
- 响应: `{"status": "success", "message": "..."}` 或 `{"status": "error", "message": "..."}`
- 使用位置: 配置编辑页面

### 获取WebUI配置
- 端点: `/api/get_web_config`
- 方法: GET
- 功能: 获取 WebUI 配置（用于设置页）。**不返回真实 AI 密钥**：`ai_api_key` 恒为空字符串，请用 `ai_api_key_configured` 判断是否已配置。
- 响应（字段与 `ConfigService.get_web_config` 一致，节选）:

  ```json
  {
    "host": "0.0.0.0",
    "port": 8080,
    "super_admin_account": "超级管理员账号",
    "disable_admin_login_web": false,
    "enable_temp_login_password": false,
    "panel_role": "master|slave",
    "panel_slaves": [],
    "panel_master": { "allowed_tokens": [], "allowed_master_ips": [] },
    "ai_api_key": "",
    "ai_api_key_configured": true,
    "ai_model": "deepseek-chat",
    "ai_api_url": "https://api.deepseek.com/chat/completions",
    "mcdr_plugins_url": "…",
    "pf_plugin_catalogue_url": "…",
    "repositories": [],
    "ssl_enabled": false,
    "ssl_certfile": "",
    "ssl_keyfile": "",
    "ssl_keyfile_password": "",
    "public_chat_enabled": false,
    "public_chat_to_game_enabled": false,
    "chat_verification_expire_minutes": 10,
    "chat_session_expire_hours": 24,
    "force_standalone": false,
    "icp_records": [],
    "chat_message_count": 0
  }
  ```

- 使用位置: WebUI设置页面

### 保存WebUI配置
- 端点: `/api/save_web_config`
- 方法: POST
- 参数: 
  - `action`: 操作类型（"config"/"disable_admin_login_web"/"enable_temp_login_password"）
  - `host`: 主机地址（可选）
  - `port`: 端口（可选）
  - `super_account`: 超级管理员账号（可选）
  - `ai_api_key`: AI API密钥（可选）
  - `ai_model`: AI模型选择（可选）
  - `ai_api_url`: AI API地址（可选）
  - `mcdr_plugins_url`: MCDR插件目录URL（可选）
  - `repositories`: 仓库列表（可选）
  - `ssl_enabled`: 是否启用SSL（可选）
  - `ssl_certfile`: SSL证书文件路径（可选）
  - `ssl_keyfile`: SSL密钥文件路径（可选）
  - `ssl_keyfile_password`: SSL密钥密码（可选）
  - `panel_role`、`panel_slaves`、`panel_master`: 多服面板相关（与 `/api/panel_merge_config` 写入的语义一致，见下文「多服面板与配对 API」）
- 功能: 保存WebUI配置
- 响应:

  ```json
  {
    "status": "success|error",
    "message": "操作结果信息（如果有）"
  }
  ```

- 调用示例:

  ```javascript
  // 保存基本配置
  async function saveWebConfig(config) {
    try {
      const response = await fetch('/api/save_web_config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          action: 'config',
          ...config
        })
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        console.log('WebUI配置保存成功');
      } else {
        console.error(`保存失败: ${result.message}`);
      }
    } catch (error) {
      console.error('保存WebUI配置出错:', error);
    }
  }
  
  // 使用示例
  saveWebConfig({
    host: '0.0.0.0',
    port: 8080,
    super_account: 'admin',
    ai_api_key: 'your-api-key',
    ai_model: 'deepseek-chat',
    ai_api_url: 'https://api.deepseek.com/chat/completions',
    mcdr_plugins_url: 'https://api.mcdreforged.com/catalogue/everything_slim.json.xz',
    repositories: ['https://example.com/repo'],
    ssl_enabled: true,
    ssl_certfile: '/path/to/cert.pem',
    ssl_keyfile: '/path/to/key.pem',
    ssl_keyfile_password: 'your-password'
  });
  ```

- 使用位置: WebUI设置页面
- 备注: 保存AI API密钥时，如果不提供值，将保持原值不变。可选参数还包括：`public_chat_enabled`、`public_chat_to_game_enabled`、`chat_verification_expire_minutes`、`chat_session_expire_hours` 等。

### 获取 ICP 备案信息
- 端点: `/api/config/icp-records`
- 方法: GET
- 功能: 获取 WebUI 配置中的 ICP 备案信息（用于页脚展示等）。无需登录。
- 响应:

  ```json
  {
    "status": "success",
    "icp_records": []
  }
  ```

- 使用位置: 页脚、关于页

## 文件操作API

### 加载CSS/JS文件
- 端点: `/api/load_file`
- 方法: GET
- 参数: 
  - `file`: 文件类型（css/js）
- 功能: 加载overall.css或overall.js文件内容
- 响应: 文件内容（纯文本）
- 使用位置: 自定义样式/脚本编辑页面

### 保存CSS/JS文件
- 端点: `/api/save_file`
- 方法: POST
- 参数: 
  - `action`: 文件类型（css/js）
  - `content`: 文件内容
- 功能: 保存overall.css或overall.js文件
- 使用位置: 自定义样式/脚本编辑页面

## 外部API

### 获取QQ昵称
- 端点: `https://api.leafone.cn/api/qqnick`
- 方法: GET
- 参数:
  - `qq`: QQ号码
- 功能: 获取QQ昵称和头像信息
- 响应:

  ```json
  {
    "code": 200,
    "msg": "获取成功",
    "data": {
      "nickname": "QQ昵称",
      "avatar": "头像信息"
    }
  }
  ```

- 使用位置: 用户信息显示

### 获取QQ头像
- 端点: `https://q1.qlogo.cn/g`
- 方法: GET
- 参数:
  - `b`: 固定值为"qq"
  - `nk`: QQ号码
  - `s`: 图像尺寸（640为最大）
- 功能: 获取QQ头像图片
- 响应: 图片文件
- 使用位置: 用户头像显示

## AI 辅助 API

### 获取命令补全建议
- 端点: `/api/command_suggestions`
- 方法: GET
- 参数:
  - `input`: 当前输入内容（可选，用于补全子命令）
- 功能: 获取 MCDR 命令补全建议，用于终端输入框自动补全。需登录。
- 响应:

  ```json
  {
    "status": "success",
    "suggestions": [
      {
        "command": "命令名或补全片段",
        "description": "描述"
      }
    ],
    "input": "与请求参数 input 相同的回显字符串"
  }
  ```

- 未登录时: **401**
- 使用位置: 终端页面命令输入补全

### 发送命令到MCDR终端
- 端点: `/api/send_command`
- 方法: POST
- 功能: 向MCDR服务器发送命令。**需管理员**。
- 参数:

  ```json
  {
    "command": "要执行的命令"
  }
  ```

- 响应:

  ```json
  {
    "status": "success|error",
    "message": "操作结果信息",
    "feedback": "命令执行反馈（RCON模式下）" 
  }
  ```

- 调用示例:

  ```javascript
  async function sendCommand(command) {
    try {
      const response = await fetch('/api/send_command', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ command: command })
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        console.log(`命令已发送: ${result.message}`);
        
        // 如果有RCON反馈
        if (result.feedback) {
          console.log(`命令反馈: ${result.feedback}`);
        }
        
        return true;
      } else {
        console.error(`发送失败: ${result.message}`);
        return false;
      }
    } catch (error) {
      console.error('发送命令出错:', error);
      return false;
    }
  }
  
  // 使用示例
  // sendCommand('list');            // MCDR命令
  // sendCommand('/say Hello');      // 带/前缀的MC命令，会尝试通过RCON发送
  ```

- 使用位置: 终端页面
- 备注: 
  - 当命令以"/"开头时，如果RCON已启用并连接，会优先使用RCON发送命令并返回直接反馈
  - 如果RCON未启用或执行失败，会回退到使用普通方式发送命令
  - 禁止执行以下命令以保护WebUI功能：`!!MCDR plugin reload guguwebui`、`!!MCDR plugin unload guguwebui`
  - 若命令被策略禁止：HTTP **403**，body 中 `message` 为「该命令已被禁止执行」

### 获取 RCON 状态
- 端点: `/api/get_rcon_status`
- 方法: GET
- 功能: 读取 MCDR `config.yml` 中 RCON 是否启用，并探测 RCON 是否已连接、可选 `list` 查询摘要。需登录。
- 响应（成功时 `status` 为 `"success"`，与 `ServerService.get_rcon_status` 一致）:

  ```json
  {
    "status": "success",
    "rcon_enabled": true,
    "rcon_connected": true,
    "rcon_info": {
      "list_response": "…",
      "player_info": "…",
      "error": "可选错误信息"
    }
  }
  ```

### DeepSeek AI 查询
- 端点: `/api/deepseek`
- 方法: POST
- 功能: 调用 `AIService.query` 向配置的 AI API（默认 DeepSeek 兼容地址）发起请求。**需管理员**。
- 请求体（`DeepseekQuery`，仅下列字段会被解析）:

  ```json
  {
    "query": "你的问题",
    "system_prompt": "可选的系统指令",
    "model": "可选模型名",
    "api_key": "可选临时密钥",
    "api_url": "可选临时 API 地址"
  }
  ```

- 响应: 

  ```json
  {
    "status": "success"
  }
  ```

  其后字段为 **上游 API 返回的 JSON**（OpenAI 兼容接口时通常含 `choices` 等）。若未配置密钥且非免密钥线路，会返回业务错误（如 400「未配置 AI API Key」）。**当前服务端实现未支持通过本接口传递 `chat_history` 多轮上下文**；若需连续对话须在客户端自行拼接进 `query` 或扩展后端。

- 错误响应: 业务错误时为 `{"status":"error","message":"..."}`；未登录 **401**，非管理员 **403**。

- 调用示例:

  ```javascript
  async function askAI(query, systemPrompt = null) {
    const requestData = { query };
    if (systemPrompt) requestData.system_prompt = systemPrompt;
    const response = await fetch('/api/deepseek', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestData),
      credentials: 'include'
    });
    const result = await response.json();
    if (result.status === 'success') {
      // 上游多为 OpenAI 兼容结构，例如从 choices[0].message.content 取文本
      return result.choices?.[0]?.message?.content ?? result;
    }
    console.error(result.message || response.status);
    return null;
  }
  ```

- 使用位置: 终端日志 AI 分析功能
- 备注: 
  - 默认需在 Web 设置中配置有效 API 密钥（部分内置地址可免密钥，以实现为准）
  - 可通过请求体临时覆盖 `api_key`、`api_url`、`model`

## PIM插件安装器API

### 检查PIM状态
- 端点: `/api/check_pim_status`
- 方法: GET
- 功能: 检查 PIM（`pim_helper`）是否已作为插件安装。**需管理员**。
- 响应: `{"status":"success","pim_status":"installed|not_installed","message":"..."}`（与 `PluginService.check_pim_status` 合并到统一 JSON）

- 调用示例:

  ```javascript
  async function checkPimStatus() {
    try {
      const response = await fetch('/api/check_pim_status');
      const data = await response.json();
      
      if (data.status === 'success') {
        if (data.pim_status === 'installed') {
          console.log('PIM插件已安装');
          return true;
        } else {
          console.log('PIM插件未安装');
          return false;
        }
      } else {
        console.error(`检查PIM状态失败: ${data.message}`);
        return false;
      }
    } catch (error) {
      console.error('检查PIM状态出错:', error);
      return false;
    }
  }
  ```

- 使用位置: 插件管理页面
- 备注: 用于检查PIM插件是否已安装，以便决定是否显示安装PIM插件的选项

### 安装PIM插件
- 端点: `/api/install_pim_plugin`
- 方法: GET
- 功能: 将 PIM 作为独立插件安装到 MCDR 中。**需管理员**。
- 响应:

  ```json
  {
    "status": "success|error",
    "message": "操作结果信息"
  }
  ```

- 调用示例:

  ```javascript
  async function installPimPlugin() {
    try {
      const response = await fetch('/api/install_pim_plugin');
      const data = await response.json();
      
      if (data.status === 'success') {
        console.log(`PIM插件安装成功: ${data.message}`);
        return true;
      } else {
        console.error(`安装失败: ${data.message}`);
        return false;
      }
    } catch (error) {
      console.error('安装PIM插件出错:', error);
      return false;
    }
  }
  ```

- 使用位置: 插件管理页面
- 备注: 将PIM插件从WebUI中提取出来，作为独立插件安装到MCDR中

### 安装插件
- 端点: `/api/pim/install_plugin`
- 方法: POST
- 参数: 
  - `plugin_id`: 插件ID
- 功能: 安装指定插件（使用PIM插件安装器）
- 响应:

  ```json
  {
    "success": true|false,
    "task_id": "任务ID",
    "message": "操作结果信息",
    "error": "错误信息（如果失败）"
  }
  ```

- 调用示例:

  ```javascript
  async function installPlugin(pluginId) {
    if (pluginId === "guguwebui") {
      console.error("不允许安装WebUI自身，这可能会导致WebUI无法正常工作");
      return;
    }
    
    try {
      const response = await fetch('/api/pim/install_plugin', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          plugin_id: pluginId
        })
      });
      
      const result = await response.json();
      if (result.success) {
        console.log(`开始安装插件 ${pluginId}, 任务ID: ${result.task_id}`);
        return result.task_id;
      } else {
        console.error(`安装失败: ${result.error || ''}`);
        return null;
      }
    } catch (error) {
      console.error('安装插件出错:', error);
      return null;
    }
  }
  ```

- 使用位置: 插件管理页面和在线插件页面
- 备注: 
  - 返回的任务ID可用于查询安装进度
  - 不允许安装ID为"guguwebui"的插件，以保护WebUI自身的稳定性

### 更新插件
- 端点: `/api/pim/update_plugin`
- 方法: POST
- 参数: 
  - `plugin_id`: 插件ID
  - `version`: 指定版本号（可选）
  - `repo_url`: 指定仓库URL（可选）
- 功能: 更新指定插件（使用PIM插件安装器）
- 响应:

  ```json
  {
    "success": true|false,
    "task_id": "任务ID",
    "message": "操作结果信息",
    "error": "错误信息（如果失败）"
  }
  ```

- 调用示例:

  ```javascript
  async function updatePlugin(pluginId, version = null, repoUrl = null) {
    if (pluginId === "guguwebui") {
      console.error("不允许更新WebUI自身，这可能会导致WebUI无法正常工作");
      return;
    }
    
    try {
      const requestData = {
        plugin_id: pluginId
      };
      
      if (version) {
        requestData.version = version;
      }
      
      if (repoUrl) {
        requestData.repo_url = repoUrl;
      }
      
      const response = await fetch('/api/pim/update_plugin', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
      });
      
      const result = await response.json();
      if (result.success) {
        console.log(`开始更新插件 ${pluginId}, 任务ID: ${result.task_id}`);
        return result.task_id;
      } else {
        console.error(`更新失败: ${result.error || ''}`);
        return null;
      }
    } catch (error) {
      console.error('更新插件出错:', error);
      return null;
    }
  }
  ```

- 使用位置: 插件管理页面
- 备注: 
  - 返回的任务ID可用于查询更新进度
  - 不允许更新ID为"guguwebui"的插件，以保护WebUI自身的稳定性
  - 可以通过version参数指定要更新到的版本
  - 可以通过repo_url参数指定要使用的仓库地址

### 卸载插件
- 端点: `/api/pim/uninstall_plugin`
- 方法: POST
- 参数: 
  - `plugin_id`: 插件ID
- 功能: 卸载指定插件并删除相关文件（使用PIM插件安装器）
- 响应:

  ```json
  {
    "success": true|false,
    "task_id": "任务ID",
    "message": "操作结果信息",
    "error": "错误信息（如果失败）"
  }
  ```

- 调用示例:

  ```javascript
  async function uninstallPlugin(pluginId) {
    if (pluginId === "guguwebui") {
      console.error("不允许卸载WebUI自身，这将导致WebUI无法正常工作");
      return;
    }
    
    try {
      const response = await fetch('/api/pim/uninstall_plugin', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          plugin_id: pluginId
        })
      });
      
      const result = await response.json();
      if (result.success) {
        console.log(`开始卸载插件 ${pluginId}, 任务ID: ${result.task_id}`);
        return result.task_id;
      } else {
        console.error(`卸载失败: ${result.error || ''}`);
        return null;
      }
    } catch (error) {
      console.error('卸载插件出错:', error);
      return null;
    }
  }
  ```

- 使用位置: 插件管理页面
- 备注: 
  - 返回的任务ID可用于查询卸载进度
  - 不允许卸载ID为"guguwebui"的插件，以保护WebUI自身的稳定性
  - 卸载操作会同时删除插件的文件，是永久性的操作
  - 如果插件被其他插件依赖，可能会需要额外确认

### 获取任务状态
- 端点: `/api/pim/task_status`
- 方法: GET
- 参数: 
  - `task_id`: 任务ID（可选，与plugin_id二选一）
  - `plugin_id`: 插件ID（可选，与task_id二选一）
- 功能: 获取指定任务的执行状态，或获取指定插件最近的任务状态
- 响应:

  ```json
  {
    "success": true|false,
    "task_info": {
      "id": "任务ID",
      "plugin_id": "插件ID",
      "status": "pending|running|completed|failed",
      "progress": 0.0-1.0,
      "message": "当前状态描述",
      "start_time": 开始时间戳,
      "end_time": 结束时间戳,
      "all_messages": ["任务执行过程中的所有消息列表"],
      "error_messages": ["错误消息列表"]
    },
    "error": "错误信息（如果请求失败）"
  }
  ```

- 调用示例:

  ```javascript
  // 通过任务ID查询
  async function checkTaskStatus(taskId, pluginId = null) {
    try {
      let url = `/api/pim/task_status?task_id=${taskId}`;
      if (pluginId) {
        url += `&plugin_id=${pluginId}`;
      }
      
      const response = await fetch(url);
      const data = await response.json();
      
      if (data.success && data.task_info) {
        console.log(`任务 ${taskId} 状态:`, data.task_info);
        return data.task_info;
      } else {
        console.error(`获取任务状态失败: ${data.error || '未知错误'}`);
        return null;
      }
    } catch (error) {
      console.error('查询任务状态出错:', error);
      return null;
    }
  }
  
  // 通过插件ID查询
  async function checkPluginTaskStatus(pluginId) {
    try {
      const response = await fetch(`/api/pim/task_status?plugin_id=${pluginId}`);
      const data = await response.json();
      
      if (data.success && data.task_info) {
        console.log(`插件 ${pluginId} 最近任务状态:`, data.task_info);
        return data.task_info;
      } else {
        console.error(`获取插件任务状态失败: ${data.error || '未知错误'}`);
        return null;
      }
    } catch (error) {
      console.error('查询插件任务状态出错:', error);
      return null;
    }
  }
  ```
  
- 使用位置: 插件管理页面和在线插件页面
- 备注: 
  - 可以通过任务ID或插件ID查询任务状态
  - 当任务未找到但提供了插件ID时，会尝试查找关联该插件的最新任务
  - progress属性为0到1的小数，表示任务进度百分比
  - all_messages包含任务执行的完整日志
  - status可能的值：pending（等待中）、running（执行中）、completed（已完成）、failed（失败）

### 获取插件所属仓库信息
- 端点: `/api/pim/plugin_repository`
- 方法: GET
- 查询参数: `plugin_id`
- 功能: 返回 `PluginService.get_plugin_repository` 结果（结构依实现而定）。需登录。

### 获取插件版本列表
- 端点: `/api/pim/plugin_versions`
- 方法: GET
- 参数:
  - `plugin_id`: 插件ID
  - `repo_url`: 指定仓库URL（可选）
- 功能: 获取指定插件的所有可用版本列表。需登录。
- 响应:

  ```json
  {
    "success": true,
    "versions": [
      {
        "version": "版本号",
        "tag_name": "标签名",
        "created_at": "创建时间",
        "download_url": "下载地址",
        "download_count": 下载次数,
        "size": 文件大小,
        "description": "版本描述"
      }
    ]
  }
  ```

- 使用位置: 插件管理页面（更新/安装指定版本）

## Pip包管理API

### 获取已安装的Pip包列表
- 端点: `/api/pip/list`
- 方法: GET
- 功能: 获取已安装的 Python 包列表。**需管理员**。
- 响应:

  ```json
  {
    "status": "success|error",
    "packages": [
      {
        "name": "包名",
        "version": "版本号"
      }
    ]
  }
  ```

- 调用示例:

  ```javascript
  async function getPipPackages() {
    try {
      const response = await fetch('/api/pip/list');
      const data = await response.json();
      
      if (data.status === 'success') {
        console.log(`获取到 ${data.packages.length} 个包`);
        // 处理包列表
        data.packages.forEach(pkg => {
          console.log(`${pkg.name} (${pkg.version})`);
        });
        return data.packages;
      } else {
        console.error('获取包列表失败');
        return [];
      }
    } catch (error) {
      console.error('获取包列表出错:', error);
      return [];
    }
  }
  ```

- 使用位置: Pip包管理页面

### 安装Pip包
- 端点: `/api/pip/install`
- 方法: POST
- 参数（JSON）: 
  - `package`: 包名
- 功能: 异步安装指定的 Python 包。**需管理员**。
- 响应:

  ```json
  {
    "status": "success",
    "task_id": "uuid"
  }
  ```

- 调用示例:

  ```javascript
  async function installPipPackage(packageName) {
    const response = await fetch('/api/pip/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ package: packageName }),
      credentials: 'include'
    });
    const result = await response.json();
    if (result.status === 'success' && result.task_id) {
      return result.task_id;
    }
    return null;
  }
  ```

- 使用位置: Pip包管理页面
- 备注: 使用返回的 `task_id` 调用 `/api/pip/task_status` 查询进度；任务体见 `PipService` 内存表

### 卸载Pip包
- 端点: `/api/pip/uninstall`
- 方法: POST
- 参数（JSON）: 
  - `package`: 包名
- 功能: 异步卸载指定的 Python 包。**需管理员**。
- 响应: 与安装相同，`{"status":"success","task_id":"..."}`

- 调用示例:

  ```javascript
  async function uninstallPipPackage(packageName) {
    const response = await fetch('/api/pip/uninstall', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ package: packageName }),
      credentials: 'include'
    });
    return (await response.json()).task_id;
  }
  ```

- 使用位置: Pip包管理页面
- 备注: 使用 `/api/pip/task_status` 轮询任务状态

### 获取Pip任务状态
- 端点: `/api/pip/task_status`
- 方法: GET
- 参数: 
  - `task_id`: 任务 ID（必填）
- 功能: 获取指定 Pip 异步任务的执行状态。**需管理员**。若 `task_id` 不存在则 **404**（`BusinessException`）。
- 响应: `{"status":"success", ...}` ，展开部分为 `pip_tasks[task_id]` 字典，常见字段：`status`（`running`/`success`/`error`）、`message`。

  ```json
  {
    "status": "success",
    "message": "正在install xxx... 或 完成/错误信息"
  }
  ```

- 调用示例:

  ```javascript
  async function checkPipTaskStatus(taskId) {
    const response = await fetch(`/api/pip/task_status?task_id=${encodeURIComponent(taskId)}`, {
      credentials: 'include'
    });
    return response.json();
  }
  ```
  
- 使用位置: Pip包管理页面
- 备注: 与 PIM 任务不同，Pip 任务状态为内存字典、结构较简（见 `guguwebui/services/pip_service.py`）

## WebUI 自身更新

### 触发 WebUI 插件更新
- 端点: `/api/self_update`
- 方法: POST
- 功能: 向 MCDR 发送 `!!MCDR plugin install -U -y guguwebui`。**需管理员**。
- 响应示例: `{"status":"success","success":true,"message":"已发送更新指令到 MCDR，插件将自动重启并完成更新"}`

### 查询 WebUI 更新信息
- 端点: `/api/self_update_info`
- 方法: GET
- 功能: 返回 `app.state.self_update_info`（若未采集则为 `available: false`）。**需管理员**。
- 响应: `{"success":true,"info":{...}}`

## 公开聊天 API

以下接口用于 `/chat`、`/player-chat` 等公开聊天页（需在配置中启用 `public_chat_enabled` 等）。与 **Web 管理端登录**（Cookie）相互独立，使用 **聊天会话 `session_id`**（`/api/chat/login` 返回）。

### 生成验证码
- 端点: `/api/chat/generate_code`
- 方法: POST
- 功能: 生成游戏内验证用码；未启用公开聊天时 **400**。
- 响应: `{"status":"success","code":"...","expire_minutes":n}`

### 查询验证码状态
- 端点: `/api/chat/check_verification`
- 方法: POST
- 请求体: `{"code":"验证码"}`
- 响应: 已验证时 `verified: true` 且含 `player_id`；否则 `pending` 等（见 `ChatService.check_verification_status`）。

### 设置聊天密码
- 端点: `/api/chat/set_password`
- 方法: POST
- 请求体: `{"code":"...","password":"..."}`（密码至少 6 位）
- 功能: 在验证码已在游戏内绑定玩家后设置密码。

### 聊天用户登录
- 端点: `/api/chat/login`
- 方法: POST
- 请求体: `{"player_id":"...","password":"..."}`
- 响应: 成功时含 `session_id`、`player_id`；同一账号活跃 IP 过多时 **429**（见服务端文案）。

### 校验聊天会话
- 端点: `/api/chat/check_session`
- 方法: POST
- 请求体: `{"session_id":"..."}`

### 聊天用户登出
- 端点: `/api/chat/logout`
- 方法: POST
- 请求体: `{"session_id":"..."}`

### 拉取消息（分页）
- 端点: `/api/chat/get_messages`
- 方法: POST
- 请求体: `{"limit":50,"offset":0}` 或 `after_id` / `before_id` 组合（见 `ChatService.get_messages`）
- 响应: `{"status":"success",...}` 内含 `messages`、`has_more`

### 拉取新消息与在线信息
- 端点: `/api/chat/get_new_messages`
- 方法: POST
- 请求体: `{"after_id":0,"player_id":"可选，用于 Web 端在线心跳"}`
- 响应: 含 `messages`、`last_message_id`、`online`（`web` / `game` / `bot` 列表）

### 清空聊天记录
- 端点: `/api/chat/clear_messages`
- 方法: POST
- 功能: 清空聊天日志。**需管理员**（Web 管理端权限）。

### 发送消息到游戏
- 端点: `/api/chat/send_message`
- 方法: POST
- 功能: 将聊天内容以 RText 广播到游戏；需 `public_chat_to_game_enabled`。请求体含 `message`、`player_id`、`session_id`；当 **Web 管理端已登录用户** 的 `username` 与 `player_id` 一致时，可按管理员路径跳过聊天会话校验（见 `ChatService.send_message` 的 `is_admin`）。

## 多服面板与配对 API

路由前缀均为 `/api`（见 `guguwebui/panel_merge/routes.py`）。配对相关请求**不经过**主服 API 代理，须在目标机器上直连。

### 服务器列表
- `GET /api/servers`：返回本地 + `panel_slaves` 中启用的子服摘要。需登录。

### 读取/保存面板合并配置
- `GET /api/panel_merge_config`：返回 `panel_role`、`panel_slaves`、`panel_master`。**需管理员**。
- `POST /api/panel_merge_config`：JSON body 同上字段，写入 `config.json`。**需管理员**。

### 子服：开关接受配对
- `POST /api/pairing/enable`：子服开启约 5 分钟接受窗口，返回 `expires_at`。
- `POST /api/pairing/disable`：关闭窗口并清空 pending。

### 子服：接收主服连接请求
- `POST /api/pairing/request`：主服在窗口内向子服 POST；**无需登录**；body 可含 `master_name`。返回 `pending` + `request_id`（首个请求后窗口关闭）。

### 子服：管理待处理请求
- `GET /api/pairing/pending`：列出待确认请求。**需管理员**。
- `POST /api/pairing/deny`：body `request_id`。
- `POST /api/pairing/accept`：body `request_id`，生成 token 并写入子服 `panel_master.allowed_tokens`。

### 查询配对结果（子服侧）
- `GET /api/pairing/status?request_id=...`：返回 `pending` 或 `accepted`（含 `token`）或 `denied`。

### 主服：发起连接与轮询
- `POST /api/pairing/connect_request`：body `slave_name`、`base_url`（子服根 URL）。由主服请求子服 `/api/pairing/request`，返回 `connect_id`。
- `GET /api/pairing/connect_status?connect_id=...`：轮询子服 `pairing/status`；成功时主服将子服写入 `panel_slaves` 并返回 `accepted` 与 `server` 摘要。
