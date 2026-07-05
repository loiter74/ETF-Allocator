## Context

现有 dashboard 前端三页面均为桌面端布局（双栏 grid、固定宽度表格）。手机端需要单栏堆叠、汉堡导航、触控友好。

## Decisions

### D1: 响应式策略：双断点

| 断点 | 宽度 | 布局 |
|------|------|------|
| 手机 | <768px | 单栏堆叠，汉堡菜单，卡片全宽 |
| 桌面 | ≥768px | 现有双栏布局保持不变 |

**理由**：不需要平板专属布局。768px 是 natural break——更窄则卡片文案放不下。

### D2: 手机端 NavBar → 汉堡菜单

NavBar 三链接 + 标题在手机端过长。改用标题 + 汉堡图标，点击展开下拉菜单。

### D3: 分配表手机端 → 卡片列表

桌面端表格在手机端横向溢出。改为每个资产一张小卡片：顶部名称+金额，下方进度条+机会分。

### D4: 模拟器手机端 → 上下堆叠

桌面端左右分栏（输入 | 结果）在手机端改为上下堆叠。结果面板在输入面板下方。

### D5: 一键启动脚本

`start.bat` 同时启动 FastAPI（后台）和 Vite（前台），浏览器自动打开。

```bat
@echo off
start "ETF-API" cmd /c "cd /d %~dp0 && uvicorn src.api.server:app --host 0.0.0.0 --port 8000"
timeout /t 2 >nul
start "ETF-UI" cmd /c "cd /d %~dp0dashboard && npm run dev"
timeout /t 2 >nul
start http://localhost:5173
```
