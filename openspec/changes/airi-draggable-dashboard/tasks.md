## 1. 设计系统基础设施（—style 阶段）

- [ ] 1.1 扩展 `dashboard/tailwind.config.js`：新增 chromatic 色阶、surface 背景、glow shadow、自定义动画
- [ ] 1.2 重写 `dashboard/src/index.css`：CSS 变量（--chromatic-hue、--chromatic-chroma）、DM Sans 字体引入、涟漪网格背景、暗色/亮色变量
- [ ] 1.3 创建 `dashboard/src/design-system/theme.ts`：主题定义（Nebula/Amber/Mint）、切换函数、localStorage 持久化
- [ ] 1.4 创建 `dashboard/src/design-system/animations.ts`：Framer Motion 预设（fadeSlideUp, scaleOnHover, staggerChildren）
- [ ] 1.5 安装新依赖：`react-grid-layout`, `framer-motion`, `recharts`

## 2. 玻璃态面板基类 + 涟漪网格（—component 阶段）

- [ ] 2.1 创建 `dashboard/src/components/layout/GlassPane.tsx`：backdrop-blur + 半透明 + 边框 + scaleOnHover
- [ ] 2.2 创建 `dashboard/src/components/layout/GridDashboard.tsx`：react-grid-layout Responsive 封装，12列，localStorage 持久化
- [ ] 2.3 创建 `dashboard/src/components/layout/RippleBackground.tsx`：径向渐变圆点网格，色相跟随主题变量
- [ ] 2.4 创建 `dashboard/src/components/layout/ThemeSwitcher.tsx`：3 色块按钮 + 明暗切换，弹入动画

## 3. 7 个监看 Widget（—widget 阶段）

- [ ] 3.1 创建 `dashboard/src/widgets/ThermometerWidget.tsx`：4 色阶径向仪表，中央大字，PE/PB 小字
- [ ] 3.2 创建 `dashboard/src/widgets/AllocationCardsWidget.tsx`：5 张 ETF 卡片横排，渐变标题 + 金额 + 触发原因 + 机会分徽章
- [ ] 3.3 创建 `dashboard/src/widgets/EquityRingWidget.tsx`：环形进度条，三色变，中央百分比
- [ ] 3.4 创建 `dashboard/src/widgets/FactorRadarWidget.tsx`：Recharts RadarChart，5轴，蓝色填充
- [ ] 3.5 创建 `dashboard/src/widgets/RiskBarWidget.tsx`：水平条 VALUE/GROWTH 组权重 + 上限标线
- [ ] 3.6 创建 `dashboard/src/widgets/ValuationChartWidget.tsx`：Recharts AreaChart，PE/PB 分位历史
- [ ] 3.7 创建 `dashboard/src/widgets/ActivityLogWidget.tsx`：历史月份操作时间线列表
- [ ] 3.8 创建 `dashboard/src/widgets/registry.ts`：Widget 注册表，统一导出

## 4. App 组装 + API 数据接入（—integration 阶段）

- [ ] 4.1 重写 `dashboard/src/App.tsx`：RippleBackground 背景 → ThemeSwitcher → GridDashboard 包裹 7 个 Widget
- [ ] 4.2 实现 `dashboard/src/hooks/useReportData.ts`：轮询 `/api/report`（10秒），解析数据给各 Widget
- [ ] 4.3 实现 `dashboard/src/hooks/useHistoryData.ts`：按需拉取 `/api/history`，给 ValuationChartWidget
- [ ] 4.4 更新 `dashboard/src/api/server.py`（如有需要，数据格式不变则跳过）

## 5. 验证

- [ ] 5.1 启动后端 `python run.py report --demo` 确认 API 返回格式
- [ ] 5.2 启动前端 `npm run dev`，验证 7 个 Widget 渲染正确、数据填充
- [ ] 5.3 拖拽重排 3 个 Widget，刷新页面，验证布局恢复
- [ ] 5.4 切换 3 套主题色 + 暗亮模式，验证即时生效
- [ ] 5.5 移动端（375px）验证 4 列网格响应式
