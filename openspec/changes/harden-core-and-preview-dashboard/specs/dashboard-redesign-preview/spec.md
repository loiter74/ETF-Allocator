## ADDED Requirements

### Requirement: 独立可查看的 HTML 稿
系统 SHALL 提供一个无需构建、无需后端即可在浏览器直接打开的 Dashboard 优化 HTML 文件。

#### Scenario: 离线打开
- **WHEN** 用户双击或在浏览器打开 HTML 文件
- **THEN** 页面使用内置示例数据完整呈现，不依赖网络资源

### Requirement: 决策优先的信息层级
HTML 稿 SHALL 在首屏优先展示本月建议动作、数据可信度、权益比例和触发约束，因子证据与历史趋势位于第二层。

#### Scenario: 桌面首屏
- **WHEN** 视口宽度至少 1024px
- **THEN** 用户无需滚动即可看到本月新增资金总额、权益/国债建议、主要分配和数据状态

### Requirement: 响应式与可访问交互
HTML 稿 SHALL 支持桌面和移动布局、键盘焦点、减少动态效果偏好以及明暗模式。

#### Scenario: 移动端
- **WHEN** 视口宽度小于 768px
- **THEN** 多栏布局折叠为单栏，表格转为可读的资产条目且不产生水平页面滚动

#### Scenario: 减少动态效果
- **WHEN** 系统启用 `prefers-reduced-motion: reduce`
- **THEN** 页面禁用非必要过渡和入场动画

### Requirement: 设计稿与生产实现隔离
HTML 稿 SHALL 不替换现有 React 路由、组件或 API 调用。

#### Scenario: 用户尚未确认
- **WHEN** HTML 稿已生成但未收到确认
- **THEN** 现有 Dashboard 的生产入口保持不变
