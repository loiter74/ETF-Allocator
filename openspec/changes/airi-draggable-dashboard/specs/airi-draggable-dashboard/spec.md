# airi-draggable-dashboard

AIRI Stage UI 画风的可拖拽 ETF 监看面板。

## ADDED Requirements

### Requirement: Chromatic 色彩系统
系统 SHALL 提供基于 CSS 变量的 Chromatic 色彩系统，支持 baseHue 220° 蓝紫色系、oklch 色彩空间、50-950 色阶。

#### Scenario: 默认蓝紫色系正确渲染
- **WHEN** 页面加载且无主题偏好设置
- **THEN** 所有 chromatic-500 元素 SHALL 渲染为 oklch(0.55 0.16 220) 颜色，surface 背景为深色 oklch(0.10 0.01 220)

#### Scenario: 主题切换即时生效
- **WHEN** 用户选择 Amber 主题
- **THEN** document root 的 `--chromatic-hue` CSS 变量 SHALL 更新为 45，所有 chromatic 色阶即时重新计算，无页面刷新

### Requirement: 可拖拽仪表盘网格
系统 SHALL 提供 12 列响应式可拖拽网格布局，支持卡片拖拽重排、缩放、布局持久化。

#### Scenario: 拖拽卡片到新位置
- **WHEN** 用户拖拽 ThermometerWidget 从 (0,0) 到 (3,0)
- **THEN** 该 Widget SHALL 移至目标位置，其他 Widget SHALL 自动压缩重排，布局 SHALL 持久化到 localStorage

#### Scenario: 响应式列数切换
- **WHEN** 视口宽度 < 768px
- **THEN** 网格列数 SHALL 切换为 4 列，所有 Widget 宽度自动适配

### Requirement: ThermometerWidget 市场温度计
系统 SHALL 提供径向仪表盘展示市场温度，4 色阶（绿<60%/黄60-80%/橙80-90%/红>90%），中央显示权益比例百分比大字，下方显示沪深300 PE 和全A PB 分位数值。

#### Scenario: 温度计显示过热状态
- **WHEN** 温度计输出权益比例 30%（双 >90%）
- **THEN** 径向环 SHALL 渲染为红色，填充 30%，中央 SHALL 显示 "30%" 大字，标签为 "过热"

### Requirement: AllocationCardsWidget 分配卡片
系统 SHALL 用 5 张横排卡片展示各 ETF 本月分配金额，每张卡片包含：ETF 名称（渐变标题）、金额（大字）、触发原因（小字灰色）、机会分（圆形徽章，颜色随分值变化）。

#### Scenario: 白酒 ETF 卡片正确渲染
- **WHEN** 白酒 ETF 分配 2500 元、机会分 0.85、触发原因为 "PE分位 15%"
- **THEN** 卡片标题 SHALL 为 "白酒ETF"，金额 SHALL 渲染为 "2,500"，触发原因 SHALL 为 "PE分位 15%"，机会分徽章 SHALL 为绿色（高分值）

### Requirement: EquityRingWidget 权益比例环
系统 SHALL 用环形进度条展示当前权益投资比例，颜色随比例变化：>=70% 绿色、40-70% 蓝色、<40% 橙色。

#### Scenario: 权益比例 70% 时环为绿色
- **WHEN** 温度计输出 equity_ratio = 0.70
- **THEN** 环形进度条 SHALL 填充 70%，颜色 SHALL 为绿色，中央 SHALL 显示 "70%"

### Requirement: 玻璃态面板基类
系统 SHALL 提供 GlassPane 组件，所有 Widget SHALL 包裹其中。特性：backdrop-blur 12px、半透明深色背景、1px 细边框、hover 微放大。

#### Scenario: GlassPane 正常渲染
- **WHEN** 组件挂载
- **THEN** 面板 SHALL 有 backdrop-filter: blur(12px)，边框 oklch(1 0 0 / 0.08)，背景 oklch(0.12 0.01 220 / 0.7)

### Requirement: RippleGrid 涟漪网格背景
系统 SHALL 在整个仪表盘背景渲染涟漪网格（CSS radial-gradient 1px 圆点，40px 间距），营造科技网格质感。

#### Scenario: 涟漪网格可见
- **WHEN** 页面加载
- **THEN** 背景 SHALL 显示 40px 间距的圆点网格，圆点颜色 SHALL 为当前主题 primary 色的 15% 透明度

### Requirement: 主题系统
系统 SHALL 提供至少 3 套预置主题（Nebula 蓝紫/Amber 琥珀金/Mint 薄荷绿），支持暗色/亮色模式，偏好持久化到 localStorage。

#### Scenario: 主题切换持久化
- **WHEN** 用户切换到 Amber 主题后刷新页面
- **THEN** 仪表盘 SHALL 恢复 Amber 主题色系，亮暗模式 SHALL 恢复之前的设置
