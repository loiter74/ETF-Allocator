# dashboard/ — ETF-Allocator 前端

React 19 | TypeScript 6 | Vite 8 | Tailwind 4 | Recharts | Framer Motion

消费 FastAPI 后端（`:8000/api/*`），提供可视化月报、模拟器和趋势分析。

## STRUCTURE

```
dashboard/
├── package.json            # React 19, Vite 8, Tailwind 4, Recharts, Framer Motion
├── vite.config.ts          # Vite 配置，代理 /api → localhost:8000
├── vitest.config.ts        # 前端测试配置（vitest + jsdom）
├── eslint.config.js        # ESLint v10
├── components.json         # shadcn/ui 配置
├── public/                 # 静态资源（favicon, icons）
├── e2e/                    # E2E 测试（Playwright Python）
├── dist/                   # 构建输出（由 npm run build 生成）
└── src/
    ├── main.tsx            # React 入口，StrictMode
    ├── App.tsx             # 根组件，BrowserRouter
    ├── index.css           # Tailwind 全局样式
    ├── types.ts            # 前端类型定义
    ├── pages/
    │   ├── AiriDashboard.tsx  # 主面板（拖拽布局 + 8 个 Widget）
    │   ├── Trends.tsx         # 历史趋势
    │   └── _archive/          # 已废弃的旧页面
    ├── widgets/
    │   ├── registry.ts        # Widget 注册中心（发现机制）
    │   └── *.tsx              # 8 个可拖拽 Widget
    ├── components/
    │   ├── layout/            # GlassPane, GridDashboard, RippleBackground, ThemeSwitcher, NavBar
    │   └── *.tsx              # GlassCard, ProgressBar, Skeleton
    ├── hooks/
    │   ├── useReport.ts       # GET/POST /api/report
    │   ├── useDashboardData.ts
    │   └── useHistory.ts      # GET /api/history
    ├── contexts/
    │   └── ThemeContext.tsx    # 暗色/亮色主题
    ├── design-system/
    │   └── theme.ts           # 设计令牌（颜色/间距/字体）
    └── lib/
        └── utils.ts           # 通用工具函数
```

## WHERE TO LOOK

| 需求 | 位置 | 说明 |
|------|------|------|
| 改页面布局 | `src/pages/AiriDashboard.tsx` | 拖拽网格配置 + Widget 排列 |
| 加新 Widget | `src/widgets/` | 创建 .tsx + 在 registry.ts 注册 |
| 改 API 接口 | `src/hooks/useReport.ts` | 前端 API 调用封装 |
| 改主题/颜色 | `src/design-system/theme.ts` | 设计令牌集中管理 |
| 改 Vite 配置 | `vite.config.ts` | 代理、端口、构建 |
| 跑前端测试 | `npm run dev` | Vite 开发服务器，端口 5173 |

## CONVENTIONS

- **Widget 注册机制**：所有 Widget 通过 `registry.ts` 动态发现，不在页面中硬编码
- **API 调用统一走 hooks**：不直接在组件中 fetch，封装在 `hooks/` 中
- **Tailwind 4**：使用 utility-first 样式，`index.css` 引导 Tailwind
- **类型集中**：前端类型定义在 `src/types.ts`，不在各组件中内联
- **Vite 代理**：开发时 `/api` 请求代理到 `localhost:8000`，生产时由 FastAPI 直接 serve

## ANTI-PATTERNS

- **不要**绕过 hooks 直接 fetch API — 统一走 `hooks/` 目录
- **不要**在组件中硬编码颜色/字体 — 读 `design-system/theme.ts`
- **不要**直接修改 registry 结构 — 加新 Widget 先在 registry 注册

## COMMANDS

```bash
cd ETF-Allocator/dashboard

npm run dev       # 开发服务器 :5173
npm run start     # 一键启动（API :8000 + UI :5173）
npm run build     # 生产构建 → dist/
npm run preview   # 预览生产构建
npm run lint      # ESLint 检查
npx vitest        # 前端测试
```

## NOTES

- **Widget 拖拽**：使用 react-grid-layout，布局在 `AiriDashboard.tsx` 的 `layout` 状态中
- **动画**：Framer Motion 用于卡片入场和 widget 切换动画
- **图表**：Recharts 用于折线图/柱状图，@nivo/treemap 用于树图
- **通知**：sonner 用于 toast 提示
