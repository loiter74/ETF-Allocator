## 1. FastAPI 后端

- [x] 1.1 创建 `src/api/__init__.py` 和 `src/api/server.py`，FastAPI app + CORS
- [x] 1.2 实现 `GET /api/report`
- [x] 1.3 实现 `POST /api/report`
- [x] 1.4 实现 `GET /api/history`
- [x] 1.5 添加 `fastapi`、`uvicorn` 到 pyproject.toml

## 2. React 前端

- [x] 2.1 Vite React+TS 项目在 `dashboard/`
- [x] 2.2 deps: tailwindcss recharts react-router-dom
- [x] 2.3 Tailwind 主题 + 毛玻璃
- [x] 2.4 Vite proxy `/api` → localhost:8000
- [x] 2.5 NavBar + GlassCard 组件

## 3. 本月概览页

- [x] 3.1 useReport hook
- [x] 3.2 温度计卡片
- [x] 3.3 组合风险卡片
- [x] 3.4 分配列表

## 4. 模拟器页

- [x] 4.1 仓位滑块面板
- [x] 4.2 滑块联动归一化
- [x] 4.3 useSimulate hook (POST /api/report)
- [x] 4.4 结果面板

## 5. 趋势页

- [x] 5.1 useHistory hook
- [x] 5.2 PE 分位折线图 (Recharts)
- [x] 5.3 指数切换按钮
- [x] 5.4 数据降采样

## 6. 集成验证

- [x] 6.1 后端 API 3 路由就绪，FastAPI app loaded
- [x] 6.2 前端 tsc 零错误，vite build 成功
- [x] 6.3 端到端：API 返回真实数据，前端可 fetch
- [x] 6.4 明亮配色 + 毛玻璃：bg-white/70 backdrop-blur-lg rounded-2xl
