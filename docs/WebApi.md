# MCDR WebUI API 文档

本文档记录 MCDR WebUI 前端界面使用的 API 接口，并与当前代码实现对齐。若与实际接口有差异，以服务端实现为准。

## 认证相关API

### 检查登录状态
- 端点: `/api/checkLogin`
- 方法: GET
- 功能: 检查当前用户是否已登录
- 响应: 

  ```json
  {
    "status": "success|error",
    "username": "用户名"
  }
  ```

- 调用示例:

  ```javascript
  async function checkLoginStatus() {
    try {
      const response = await fetch('/api/checkLogin');
      const data = await response.json();
      if (data.status === 'success') {
        console.log(`已登录，用户名: ${data.username}`);
      } else {
        console.log('未登录');
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
- 端点: `/logout`
- 方法: GET
- 功能: 用户退出登录
- 响应: 重定向到登录页面
- 调用示例:

  ```javascript
  function logout() {
    window.location.href = '/logout';
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
- 功能: 获取Minecraft服务器状态
- 响应:

  ```json
  {
    "status": "online|offline|error",
    "version": "服务器版本信息",
    "players": "在线人数/最大人数"
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
        console.log('获取服务器状态出错');
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
  - `start_line`: 开始行号（默认 0）
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
  - `last_counter`: 客户端已有的最后一行计数器ID
  - `max_lines`: 最大返回行数（默认100，最大200）
- 功能: 获取最新的日志更新，用于实时更新日志显示
- 响应:

  ```json
  {
    "status": "success|error",
    "logs": [
      {
        "line_number": 行号,
        "content": "日志内容"
      }
    ],
    "total_lines": 总行数,
    "last_counter": 最后一行计数器ID,
    "new_logs_count": 新增日志数量
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
  - `plugin_id`: 指定插件ID（可选，字符串，提供时只返回该插件）
- 功能: 获取已安装的插件列表。未登录时仅返回 guguwebui 插件信息；未登录且无插件时返回 401。
- 响应:

  ```json
  {
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

  - 未登录时: `401`，body 为 `{"status": "error", "message": "User not logged in"}`

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
    "pages": [
      {
        "id": "插件ID",
        "path": "HTML 文件路径"
      }
    ]
  }
  ```

  - 未登录时: `401`，body 为 `{"status": "error", "message": "User not logged in"}`
- 使用位置: 布局侧边栏、插件网页入口

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
- 功能: 获取WebUI本身的配置
- 响应:

  ```json
  {
    "host": "主机地址",
    "port": "端口",
    "super_admin_account": "超级管理员账号",
    "disable_admin_login_web": "是否禁用其他管理员登录",
    "enable_temp_login_password": "是否启用临时登录密码",
    "ai_api_key": "AI API密钥（但是为空）",
    "ai_model": "AI模型名称",
    "ai_api_url": "AI API地址",
    "mcdr_plugins_url": "MCDR插件目录URL",
    "repositories": ["仓库列表"],
    "ssl_enabled": "是否启用SSL",
    "ssl_certfile": "SSL证书文件路径",
    "ssl_keyfile": "SSL密钥文件路径",
    "ssl_keyfile_password": "SSL密钥密码"
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
    ]
  }
  ```

- 未登录时: `401`，body 为 `{"status": "error", "message": "User not logged in"}`
- 使用位置: 终端页面命令输入补全

### 发送命令到MCDR终端
- 端点: `/api/send_command`
- 方法: POST
- 功能: 向MCDR服务器发送命令
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

### DeepSeek AI 查询
- 端点: `/api/deepseek`
- 方法: POST
- 功能: 向DeepSeek API发送问题并获取AI回答
- 参数:

  ```json
  {
    "query": "你的问题",
    "system_prompt": "可选的系统指令",
    "model": "可选指定模型名",
    "api_key": "可选的临时API密钥",
    "api_url": "可选的临时API地址",
    "chat_history": [
      {"role": "user", "content": "之前的问题"},
      {"role": "assistant", "content": "之前的回答"}
    ]
  }
  ```

- 响应:

  ```json
  {
    "status": "success|error",
    "answer": "AI回答内容",
    "model": "使用的模型名称"
  }
  ```

- 错误响应:

  ```json
  {
    "status": "error",
    "message": "错误信息"
  }
  ```

- 调用示例:

  ```javascript
  // 简单问答
  async function askAI(query, systemPrompt = null) {
    try {
      const requestData = {
        query: query
      };
      
      if (systemPrompt) {
        requestData.system_prompt = systemPrompt;
      }
      
      const response = await fetch('/api/deepseek', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        console.log(`AI回答: ${result.answer}`);
        return result.answer;
      } else {
        console.error(`查询失败: ${result.message}`);
        return null;
      }
    } catch (error) {
      console.error('AI查询出错:', error);
      return null;
    }
  }
  
  // 连续对话示例
  async function chatWithAI(query, chatHistory = []) {
    try {
      const requestData = {
        query: query,
        chat_history: chatHistory
      };
      
      const response = await fetch('/api/deepseek', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        // 更新聊天历史
        chatHistory.push(
          { role: 'user', content: query },
          { role: 'assistant', content: result.answer }
        );
        
        return {
          answer: result.answer,
          history: chatHistory
        };
      } else {
        console.error(`查询失败: ${result.message}`);
        return { answer: null, history: chatHistory };
      }
    } catch (error) {
      console.error('AI查询出错:', error);
      return { answer: null, history: chatHistory };
    }
  }
  ```

- 使用位置: 终端日志AI分析功能
- 备注: 
  - 需要在Web设置中配置有效的DeepSeek API密钥
  - chat_history参数用于支持连续对话，保留上下文
  - 支持的模型包括：`deepseek-chat`、`deepseek-coder`等
  - 可以通过临时参数覆盖配置中的API密钥和地址

## PIM插件安装器API

### 检查PIM状态
- 端点: `/api/check_pim_status`
- 方法: GET
- 功能: 检查PIM插件的安装状态
- 响应:

  ```json
  {
    "status": "success|error",
    "pim_status": "installed|not_installed",
    "message": "错误信息（如果失败）"
  }
  ```

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
- 功能: 将PIM作为独立插件安装到MCDR中
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

## Pip包管理API

### 获取已安装的Pip包列表
- 端点: `/api/pip/list`
- 方法: GET
- 功能: 获取已安装的Python包列表
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
- 参数: 
  - `package`: 包名
- 功能: 安装指定的Python包
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
  async function installPipPackage(packageName) {
    try {
      const response = await fetch('/api/pip/install', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          package: packageName
        })
      });
      
      const result = await response.json();
      if (result.success) {
        console.log(`开始安装包 ${packageName}, 任务ID: ${result.task_id}`);
        return result.task_id;
      } else {
        console.error(`安装失败: ${result.error || ''}`);
        return null;
      }
    } catch (error) {
      console.error('安装包出错:', error);
      return null;
    }
  }
  ```

- 使用位置: Pip包管理页面
- 备注: 返回的任务ID可用于查询安装进度

### 卸载Pip包
- 端点: `/api/pip/uninstall`
- 方法: POST
- 参数: 
  - `package`: 包名
- 功能: 卸载指定的Python包
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
  async function uninstallPipPackage(packageName) {
    try {
      const response = await fetch('/api/pip/uninstall', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          package: packageName
        })
      });
      
      const result = await response.json();
      if (result.success) {
        console.log(`开始卸载包 ${packageName}, 任务ID: ${result.task_id}`);
        return result.task_id;
      } else {
        console.error(`卸载失败: ${result.error || ''}`);
        return null;
      }
    } catch (error) {
      console.error('卸载包出错:', error);
      return null;
    }
  }
  ```

- 使用位置: Pip包管理页面
- 备注: 返回的任务ID可用于查询卸载进度

### 获取Pip任务状态
- 端点: `/api/pip/task_status`
- 方法: GET
- 参数: 
  - `task_id`: 任务ID
- 功能: 获取指定Pip任务的执行状态
- 响应:

  ```json
  {
    "success": true|false,
    "task_info": {
      "id": "任务ID",
      "action": "install|uninstall",
      "package": "包名",
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
  async function checkPipTaskStatus(taskId) {
    try {
      const response = await fetch(`/api/pip/task_status?task_id=${taskId}`);
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
  ```
  
- 使用位置: Pip包管理页面
- 备注: 
  - progress属性为0到1的小数，表示任务进度百分比
  - all_messages包含任务执行的完整日志
  - status可能的值：pending（等待中）、running（执行中）、completed（已完成）、failed（失败）