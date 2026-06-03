## 1. 响应式布局

- [x] 1.1 NavBar：手机端汉堡菜单（<768px），桌面端保持文字链接
- [x] 1.2 Dashboard：温度计+风险卡片从双栏 grid 改为响应式（`md:grid-cols-2 grid-cols-1`）
- [x] 1.3 Dashboard：分配表手机端改为卡片列表（每个资产一张 GlassCard）
- [x] 1.4 Simulator：双栏布局改为响应式（`md:flex-row flex-col`）
- [x] 1.5 Trends：图表容器高度自适应（手机端 250px，桌面端 400px）

## 2. 一键启动

- [x] 2.1 创建 `start.bat`（项目根目录）同时启动后端和前端
- [x] 2.2 启动后自动打开浏览器到 `http://localhost:5173`

## 3. 验证

- [x] 3.1 桌面端布局不变（≥768px 双栏正常）
- [x] 3.2 tsc 零错误
- [x] 3.3 start.bat 已创建
