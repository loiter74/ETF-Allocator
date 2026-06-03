## Why

当前前端仅支持桌面端（min-width 1024px），无法在手机上使用。同时启动需要开两个终端分别启动前后端，不方便。需要：响应式适配手机 + 一键启动脚本。

## What Changes

- 现有三页面 React 前端增加移动端响应式布局（Tailwind 断点）
- 桌面端保持双栏布局，手机端自动切换为单栏堆叠
- 新增 `start.bat`（Windows）一键启动脚本，同时拉起 FastAPI 和 Vite
- 可选：PWA manifest + 图标，手机可"添加到主屏幕"

## Capabilities

### Modified Capabilities
- `dashboard-ui`: 布局从桌面专属改为响应式（sm/md/lg 断点适配）

## Impact

- `dashboard/src/pages/Dashboard.tsx` — 分配表手机端改为卡片列表
- `dashboard/src/pages/Simulator.tsx` — 双栏改上下堆叠
- `dashboard/src/components/NavBar.tsx` — 手机端汉堡菜单
- `dashboard/src/components/GlassCard.tsx` — 手机端更小圆角
- 新增 `start.bat`（项目根目录）
