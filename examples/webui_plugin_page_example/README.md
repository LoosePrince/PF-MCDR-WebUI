# WebUI 插件页与自定义 API 示例

本示例演示如何：

1. **注册插件网页**：在 WebUI 侧边栏「插件网页」中出现入口，并在面板内以 iframe 展示 HTML。
2. **注册可选后端处理器**：浏览器请求 `/api/plugin/<plugin_id>/...` 时，由 MCDR 进程内 Python 函数处理（路径与查询/体见 `params`）。

## 安装

1. 将本目录**整个文件夹**复制到 MCDR 的 `plugins/` 下，保持结构为：
   - `plugins/webui_plugin_page_example/mcdreforged.plugin.json`
   - `plugins/webui_plugin_page_example/webui_plugin_page_example.py`
   - `plugins/webui_plugin_page_example/static/demo.html`
2. 确保已安装并启用 **guguwebui**（PF-MCDR-WebUI）。
3. 重载插件或重启 MCDR：`!!MCDR plugin reload webui_plugin_page_example`（名称以你实际文件名为准）。

## 使用

1. 浏览器登录 WebUI。
2. 左侧边栏展开 **插件网页**，应出现 **webui_plugin_page_example**。
3. 打开后页面内可点击按钮，调用本插件注册的 API（`hello`、`echo` 等）。

## 说明

- **网页路径**：在 `on_load` 中用 `Path(__file__).parent / "static" / "demo.html"` 指向静态 HTML，避免写死工作目录。
- **侧边栏**：由 `register_plugin_page` 自动登记；列表数据来自 `GET /api/plugins/web_pages`。
- **自定义 API**：`register_plugin_page(..., api_handler=..., upload_max_bytes=...)`；`upload_max_bytes` 可选，用于单插件覆盖上传大小上限。前端请求形如  
  `GET ${root}/api/plugin/webui_plugin_page_example/hello`（若部署在子路径，`root` 为 `/guguwebui` 等，示例 HTML 内从 `window.parent.__GUGU_CONFIG__` 读取）。

更多字段与状态码见仓库 `docs/WebApi.md` 中「插件后端 API 代理」一节（含 **`multipart/form-data` 文件字段** 解析与单文件大小上限）。
