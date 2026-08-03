## MODIFIED Requirements

### Requirement: Dashboard API 必须保持预览与导入边界

Dashboard API SHALL 在保留现有报告和交易计划接口的同时，提供只读 OCR 配置与文字解析接口；导入接口 SHALL NOT 调用交易计划预览或确认逻辑。

#### Scenario: 导入后尚未扫描

- **WHEN** 用户把 OCR 草稿应用到表单
- **THEN** 只有前端表单状态改变，服务端交易状态和历史保持不变，直到用户另行点击扫描或确认

