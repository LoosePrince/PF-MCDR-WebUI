# GUGU WebUI Frontend

这是 GUGU WebUI 的前端项目，使用 React + Vite + TypeScript + Tailwind CSS 构建。

## 开发环境要求

- Node.js >= 18.0.0
- npm >= 9.0.0

## 安装依赖

```bash
cd src/guguwebui/frontend
npm install
```

## 开发

启动开发服务器（会自动代理 API 请求到后端）：

```bash
npm run dev
```

开发服务器将在 `http://localhost:5173` 启动。

## 构建

构建生产版本：

```bash
npm run build
```

构建产物将输出到 `src/guguwebui/static/` 目录，这些文件会被打包进 MCDR 插件。

## 项目结构

```
frontend/
├── src/
│   ├── main.tsx          # React 入口文件
│   ├── App.tsx           # 主应用组件
│   ├── index.css         # 全局样式（包含 Tailwind）
│   ├── components/       # 通用组件
│   ├── pages/            # 页面组件
│   ├── hooks/            # 自定义 Hooks
│   ├── i18n/             # 国际化配置
│   │   ├── config.ts     # i18n 配置
│   │   └── locales/      # 语言文件
│   └── ...
├── public/                # 公共静态资源
├── index.html             # HTML 入口
├── package.json
├── vite.config.ts         # Vite 配置
├── tsconfig.json          # TypeScript 配置
└── tailwind.config.js     # Tailwind CSS 配置
```

## 注意事项

1. **前端源文件不会被打包进插件**：只有构建后的 `static/` 目录会被打包
2. **构建是必需的**：在发布前必须运行 `npm run build` 生成静态文件
3. **GitHub Actions 会自动构建**：推送代码到仓库时，工作流会自动构建前端并打包

## 技术栈

- **React 18** - UI 框架
- **Vite 5** - 构建工具
- **TypeScript** - 类型安全
- **Tailwind CSS 3** - 样式框架
- **React Router 6** - 路由管理
- **react-i18next** - 国际化
