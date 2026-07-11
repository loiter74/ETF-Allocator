## MODIFIED Requirements

### Requirement: 响应式布局
系统 SHALL 在所有页面使用响应式布局，手机端（<768px）自动切换为单栏堆叠，桌面端（≥768px）保持双栏布局。

#### Scenario: 手机端导航
- **WHEN** 视口宽度 < 768px
- **THEN** NavBar 显示汉堡菜单图标，点击展开本月概览、历史趋势和资金记录三个页面链接

#### Scenario: 手机端分配表
- **WHEN** 视口宽度 < 768px 且用户在 Dashboard 概览
- **THEN** 分配数据以卡片列表形式展示，而非宽表格

#### Scenario: 桌面端保持原样
- **WHEN** 视口宽度 ≥ 768px
- **THEN** 现有概览和趋势页面保持原有布局，资金记录页使用同一 GlassCard 视觉语言

## ADDED Requirements

### Requirement: 浅色主题可读性
系统 SHALL 在所有路由统一使用原有浅色主题，正文、标签、输入框和卡片标题与其背景保持清晰可读。

#### Scenario: 存在旧暗色偏好
- **WHEN** 浏览器保存了历史 `etf-mode=dark` 偏好后重新打开应用
- **THEN** 应用仍以统一浅色主题显示且不存在深色背景上的深色文字

#### Scenario: 页面路由切换
- **WHEN** 用户在三个导航页面之间切换
- **THEN** 页面背景和文字对比度保持一致，不发生主题闪烁

### Requirement: 精简重复页面
系统 SHALL 不再提供与本月概览功能重叠的独立持仓模拟页面或导航入口。

#### Scenario: 打开旧模拟链接
- **WHEN** 用户访问旧的 `/simulator` 地址
- **THEN** 系统跳转到本月概览且导航中不显示“持仓模拟”
