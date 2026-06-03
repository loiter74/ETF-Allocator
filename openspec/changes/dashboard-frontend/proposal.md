## Why

当前 ETF 配置系统只有 CLI 输出（`python run.py report`），缺乏可视化界面。需要三个能力的看板前端：月度概览仪表盘、仓位配置模拟器、历史 PE 趋势图。目标是让人一眼看懂"市场冷不冷、钱往哪分、组合健康不健康"。

## What Changes

- 新增 FastAPI 后端服务（`src/api/`），提供 `/api/report` 和 `/api/history` 两个接口
- 新增 React 前端（`dashboard/`），Vite + Tailwind CSS + Recharts，三页面 SPA
- 页面 1 `/dashboard`：温度计 + 组合风险卡片 + 权益分配列表
- 页面 2 `/simulate`：手动输入仓位 → 计算分配 → 展示投后仓位结构
- 页面 3 `/trends`：各指数 PE 分位 5 年历史折线图

## Capabilities

### New Capabilities
- `dashboard-api`: FastAPI 后端，复用现有 src/ 模块提供数据接口
- `dashboard-ui`: React 前端 SPA，三页面可视化看板

### Modified Capabilities
- （无，均为新增）

## Impact

- 新增 `src/api/`（~100 行 Python，FastAPI entry point）
- 新增 `dashboard/` 目录（前端项目，Vite + React + Tailwind）
- 新依赖：`fastapi`, `uvicorn`（后端），`react`, `tailwindcss`, `recharts`（前端）
- 不修改现有 src/ 模块（纯新增 + 复用）
