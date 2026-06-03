## Context

当前 `dashboard/` 是 React + TypeScript + Vite + Tailwind CSS 应用，通过 FastAPI 后端获取 ETF 配置数据。视觉风格为默认模板风格，缺乏品牌辨识度。

目标：模仿 **AIRI Stage UI** 的设计语言，用 React 生态实现一个可拖拽、可自定义的 ETF 监看面板。

AIRI Stage UI 的核心设计要素（来自 `moeru-ai/airi` 源码分析）：
- **Chromatic 色彩系统**：baseHue 220.44°，primary/complementary 180° 分离，chroma 随 lightness 曲线变化
- **深色科幻风**：深色底 (#0a0a10 层级) + 蓝紫 glow 光晕 + 半透明玻璃面板
- **弹性动画**：cubic-bezier(0.16, 1, 0.3, 1) 缓出、fadeIn/slideUp 过渡
- **仪表组件群**：LevelMeter（多档阈值条）、ThresholdMeter（径向仪表）、ProcessingMeter（动态进度）、TimeSeriesChart（时序图）、RippleGrid（涟漪网格背景）
- **流体排版**：DM Sans Variable（可变字重），标题/数字用大字号 + 渐变色

## Goals / Non-Goals

**Goals:**
- 实现 Chromatic 220° 色系（CSS 变量，支持运行时切换色相）
- 实现可拖拽仪表盘网格（react-grid-layout，布局持久化到 localStorage）
- 实现 7 个监看 Widget（温度计、因子雷达、分配卡片、权益环、风险条、估值图、日志）
- 实现玻璃态面板基类（GlassPane）和弹性过渡动画（Framer Motion）
- 至少 3 套主题色（蓝紫 220° / 琥珀金 45° / 薄荷绿 160°）
- 复刻 AIRI 的 RippleGrid 背景

**Non-Goals:**
- 不实现 AIRI 的 Three.js / Live2D 渲染（那是角色渲染，与监看面板无关）
- 不实现物理游标效果（Cursor Floating/Momentum 需要 canvas，过于复杂，不是 MVP）
- 不实现 WebSocket 实时推送（现有 API 轮询足够，增量可做 V2）
- 不修改 FastAPI 后端

## Decisions

### D1: 用 Tailwind CSS 自定义主题模拟 Chromatic，而非引入 UnoCSS

**选择**：保持项目现有 Tailwind CSS，在 `tailwind.config.js` 中扩展 `colors` 段来模拟 Chromatic 色系。

**理由**：项目已用 Tailwind，切换 UnoCSS 成本太高。Tailwind 的 CSS 变量和 `oklch()` 颜色函数完全能模拟 Chromatic 的色相-色度-亮度模型。

**Chromatic 色系映射**：
```js
// 220° 蓝紫主题
colors: {
  chromatic: {
    50:  'oklch(0.97 0.01 220)',
    100: 'oklch(0.93 0.02 220)',
    200: 'oklch(0.85 0.04 220)',
    300: 'oklch(0.75 0.08 220)',
    400: 'oklch(0.65 0.12 220)',
    500: 'oklch(0.55 0.16 220)',
    600: 'oklch(0.45 0.18 220)',
    700: 'oklch(0.35 0.15 220)',
    800: 'oklch(0.25 0.10 220)',
    900: 'oklch(0.15 0.05 220)',
    950: 'oklch(0.08 0.02 220)',
  },
  // 背景色阶
  surface: {
    0:   'oklch(0.10 0.01 220)',
    1:   'oklch(0.12 0.01 220)',
    2:   'oklch(0.15 0.02 220)',
    3:   'oklch(0.18 0.02 220)',
  }
}
```

### D2: react-grid-layout 作为拖拽引擎

**选择**：`react-grid-layout` (v1.4+, 20k stars)。

**理由**：React 生态最成熟的拖拽网格库，支持响应式断点、持久化、压缩布局。比 @dnd-kit（通用拖拽）更适合"仪表盘卡片"场景。

**替代方案**：@dnd-kit → 拒绝了，需要手动实现网格系统和碰撞检测，开发量大。

**布局配置**：
- 12 列宽网格，行高 80px
- 断点：lg(1200px): 12列, md(996px): 8列, sm(768px): 4列
- 布局持久化到 localStorage key: `etf-dashboard-layout`

### D3: 7 个 Widget 定义

每个 Widget 是一个独立的 React 组件，接收标准化 props，通过注册表加入仪表盘。

| # | Widget | 尺寸 | 数据源 | 视觉风格 | AIRI 对应 |
|---|--------|------|--------|----------|-----------|
| 1 | ThermometerWidget | 3×3 | `/api/report` tempResult | 径向仪表，4色阶（绿→黄→橙→红），中央大字百分比 | ThresholdMeter |
| 2 | FactorRadarWidget | 4×4 | `/api/report` factors | 蛛网图/雷达图，5资产5轴，蓝色填充 | DataPane + Chart |
| 3 | AllocationCardsWidget | 6×3 | `/api/report` allocation | 5张 ETF 卡片横排，渐变背景，金额大字 + 触发原因小字 + 机会分徽章 | ProcessingMeter |
| 4 | EquityRingWidget | 3×3 | `/api/report` tempResult | 环形进度条，权益比例，75%+ 绿色 / 40-70% 蓝色 / <40% 橙色 | LevelMeter |
| 5 | RiskBarWidget | 6×2 | `/api/report` constraints | 水平条：VALUE组 60%上限 / GROWTH组 15%上限，颜色超限变红 | LevelMeter |
| 6 | ValuationChartWidget | 6×4 | `/api/history` | Recharts 面积图，PE/PB 分位历史，expanding window 虚线标注 | TimeSeriesChart |
| 7 | ActivityLogWidget | 3×4 | `/api/report` monthlyResults | 时间线列表，历史月份操作摘要 | Poppin'Text |

### D4: 玻璃态面板基类 GlassPane

每个 Widget 外层包裹 `<GlassPane>`：
- `backdrop-filter: blur(12px)` + 半透明深色背景
- 1px `oklch(1 0 0 / 0.08)` 边框
- 圆角 12px
- hover 时边框亮度提升到 0.15
- Framer Motion `whileHover={{ scale: 1.01 }}` 微弹性

### D5: RippleGrid 背景

复刻 AIRI 的涟漪网格背景，用纯 CSS 实现：
```css
background-image:
  radial-gradient(circle at 1px 1px, oklch(0.55 0.16 220 / 0.15) 1px, transparent 0);
background-size: 40px 40px;
```
叠在深色底色上，营造科技网格质感。

### D6: 主题切换机制

3 套预置主题色通过 CSS 变量 `--chromatic-hue` 控制：
- **Nebula** (default): 220° 蓝紫
- **Amber**: 45° 琥珀金
- **Mint**: 160° 薄荷绿

切换时修改 `document.documentElement.style.setProperty('--chromatic-hue', '45')`，所有 `oklch(l c h)` 中的 h 参数引用该变量。

暗色/亮色模式切换 `class="dark"` on `<html>`，亮色模式下 surface 层级反转。

## Risks / Trade-offs

- **[Risk] react-grid-layout 响应式断点与 Tailwind 断点不协同** → Mitigation: 使用 react-grid-layout 的 `Responsive` 模式，cols 参数手动匹配 Tailwind 的 lg/md/sm
- **[Risk] 性能：Framer Motion 动画太多可能导致低配设备卡顿** → Mitigation: 启用 `prefers-reduced-motion` 检测，关闭所有动画；`layoutId` 动画只用于主题切换
- **[Trade-off] 不引入 ECharts 而用 Recharts** → Recharts 足够实现面积图、雷达图、环形图，且已在项目依赖中（test_formulas 验证过），无需新增依赖
- **[Trade-off] 不实现 Cursor Floating/Momentum** → 这是 AIRI 最标志性的交互但需要 canvas 和 requestAnimationFrame 循环，MVP 阶段不做，可以作为 V2 "氛围增强"

## Open Questions

无。所有技术决策已确定。
