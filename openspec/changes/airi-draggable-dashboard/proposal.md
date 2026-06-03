## Why

当前 `dashboard/` 使用基础 React + Vite 模板，功能上能展示数据但视觉上缺乏辨识度和专业感。用户需要一个具备 AIRI Stage UI 画风的监看面板 — 深色科幻风、Chromatic 220° 蓝紫色系、玻璃态面板、弹性动画、可拖拽布局 — 用于日常监控 ETF 配置状态。

## What Changes

- **新增** AIRI 风格设计系统：Chromatic 220.44° 色系（CSS 变量）、DM Sans 字体、玻璃态 + glow 光晕面板、弹性动画预设
- **新增** 可拖拽仪表盘布局：react-grid-layout 实现拖拽/缩放/持久化布局
- **新增** 7 个核心监看 Widget：市场温度计、因子雷达、分配卡片、权益比例环、组合风险条、估值分位图、活动日志
- **新增** 主题系统：深色/亮色/系统，至少 3 套预置主题色（蓝紫/琥珀金/薄荷绿）
- **修改** `dashboard/` 的 Vite 配置、Tailwind 配置，接入新设计系统

## Capabilities

### New Capabilities
- `airi-draggable-dashboard`: AIRI 风格可拖拽监看面板整体（布局引擎 + 设计系统 + Widget 注册机制）

### Modified Capabilities
<!-- No existing specs to modify -->

## Impact

- **新增文件**: `dashboard/src/design-system/`（主题 tokens、动画预设）、`dashboard/src/widgets/`（7 个 Widget）、`dashboard/src/components/layout/`（Grid 布局组件、玻璃面板基类）
- **修改文件**: `dashboard/tailwind.config.js`、`dashboard/src/App.tsx`、`dashboard/src/index.css`、`dashboard/package.json`（新增 react-grid-layout + framer-motion）
- **不涉及**: API 后端 (`src/api/server.py`) 零修改，所有数据通过现有 `/api/report` 和 `/api/history` 获取
- **风险**: react-grid-layout 的响应式断点需要移动端适配，但这是增量功能，不影响现有 API 页面
