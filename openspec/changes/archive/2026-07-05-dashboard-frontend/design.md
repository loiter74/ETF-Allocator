## Context

现有 ETF-Allocator 是纯 CLI 系统（`python run.py report`），输出终端文本。需要一个可视化看板来展示月度配置结果、支持 What-If 模拟、查看历史趋势。

前端风格：明亮底色 + 毛玻璃卡片（glassmorphism），配色参考 airi VTuber（浅紫白底 `#F8F6FF`，主色紫 `#7C3AED`，辅色粉 `#EC4899`）。

## Goals / Non-Goals

**Goals:**
- 三页面 React SPA，自适应桌面端
- FastAPI 后端复用现有 `src/` 模块，零重复代码
- 按需加载（不轮询、不 WebSocket）
- 模拟器支持手动输入仓位，实时计算分配结果
- 趋势图展示 5 年 PE 分位走势

**Non-Goals:**
- 不做移动端适配（桌面优先）
- 不实现 Live2D 角色动画
- 不实现用户认证 / 多用户
- 不修改现有 `run.py` 或 `validate.py`

## Decisions

### D1: FastAPI 后端，直接复用现有模块

**决策**：新增 `src/api/server.py`，import 现有的 `run.py` 中的 `calculate_factors`、`score_all`、`equity_ratio`、`allocate` 等函数。不包装、不重写。

**理由**：现有函数已经返回结构化数据（dict），FastAPI 直接用 `JSONResponse` 返回即可。唯一需要新增的是历史数据查询接口（从 SQLite 读）。

### D2: Vite + React + Tailwind CSS

**决策**：前端用 Vite 创建 React + TypeScript 项目，Tailwind CSS v4 做样式。

**理由**：Vite 零配置热更新，Tailwind 配合毛玻璃效果（`bg-white/70 backdrop-blur-xl`）最简洁。Recharts 是 React 生态最轻量的图表库。

### D3: 明亮配色方案

**决策**：背景 `#F8F6FF`（极浅紫），卡片 `bg-white/70 backdrop-blur-lg`，主色 `#7C3AED`（airi紫），辅色 `#EC4899`（airi粉）。

**三个语义色**：低估/安全=翠绿 `#10B981`，接近上限=琥珀 `#F59E0B`，超限/过热=红 `#EF4444`。

### D4: 模拟器数据流独立

**决策**：模拟器的分配计算在前端做（调用同一个 `/api/report` 接口但传入用户自定义的 `current_weights` 参数），不单独开接口。

**接口扩展**：`POST /api/report` 接受 `{"date": "...", "new_money": 10000, "total_assets": 500000, "current_weights": {...}}`。

## API 设计

### `GET /api/report?date=2026-05-29`
返回当前月报的完整数据（温度计、各资产因子值、机会分、分配结果、约束状态）。

### `POST /api/report`
同上，但接受自定义参数用于模拟器：
```json
{
  "date": "2026-05-29",
  "new_money": 10000,
  "total_assets": 500000,
  "current_weights": {"白酒ETF": 0.12, ...}
}
```

### `GET /api/history?index=000300&field=pe&years=5`
返回指定指数的 PE/PB 历史序列：
```json
{
  "index": "000300",
  "data": [{"date": "...", "value": 16.2, "percentile": 0.45}, ...]
}
```

## Risks / Trade-offs

- **[前端复杂度]** 三页面 + 模拟器实时计算比纯静态页面复杂 → 用 React 状态管理，每个页面独立加载数据
- **[跨域问题]** FastAPI 和 Vite dev server 不同端口 → 开发环境配 Vite proxy，生产环境 FastAPI serve 静态文件或 nginx 反代
- **[图表性能]** 5 年 2500 个数据点时 Recharts 可能卡 → 按周/月降采样，保留关键极值点
