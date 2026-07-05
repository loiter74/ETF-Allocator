## MODIFIED Requirements

### Requirement: 响应式布局
系统 SHALL 在所有页面使用响应式布局，手机端（<768px）自动切换为单栏堆叠，桌面端（≥768px）保持双栏布局。

#### Scenario: 手机端导航
- **WHEN** 视口宽度 < 768px
- **THEN** NavBar 显示汉堡菜单图标，点击展开三个页面链接

#### Scenario: 手机端分配表
- **WHEN** 视口宽度 < 768px 且用户在 /dashboard
- **THEN** 分配数据以卡片列表形式展示（每个资产一张 GlassCard），而非表格

#### Scenario: 桌面端保持原样
- **WHEN** 视口宽度 ≥ 768px
- **THEN** 所有页面保持原有双栏布局

## ADDED Requirements

### Requirement: 一键启动脚本
系统 SHALL 提供 `start.bat` 脚本，一键启动后端 API 和前端开发服务器。

#### Scenario: 一键启动
- **WHEN** 用户双击 `start.bat`
- **THEN** 后端 FastAPI 在 8000 端口启动，前端 Vite 在 5173 端口启动，浏览器自动打开 http://localhost:5173
