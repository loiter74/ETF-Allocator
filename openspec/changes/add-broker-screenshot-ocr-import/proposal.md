## Why

完整持仓快照要求逐项填写份额、现价和平均成本，月度操作负担过高。Tushare 等行情源只能补当前市场价格，不能取得个人账户的真实份额、券商平均成本和可用现金，因此不能替代券商快照。系统需要一个长期可维护的截图导入入口，在不牺牲隐私、可核对性和交易确认边界的前提下降低录入成本。

## What Changes

- 在 Dashboard 的“盈利收获与交易计划”中新增券商截图导入：图片只在浏览器内由 Tesseract.js OCR，服务端不接收原图。
- 新增只读文字结构化 API。服务端可用 DeepSeek JSON Output 将 OCR 文字归一为候选持仓快照；未配置 Key、响应为空或校验失败时自动回退到确定性本地解析器。
- 所有识别字段携带来源、置信度和警告，必须经过页面核对并由用户点击“应用到快照”，不得自动预览、确认或执行交易。
- OCR 缺失的当前价格可从本地 PIT 价格库按快照日补齐；行情数据不得覆盖截图中的券商平均成本、份额或现金。
- 增加图片类型、大小、数量和 OCR 文字长度边界；API Key 只从服务端环境变量读取，不通过接口或日志暴露。

## Capabilities

### New Capabilities

- `broker-screenshot-ocr`: 浏览器本地券商截图 OCR、进度、图片校验和隐私边界。
- `portfolio-text-structuring`: DeepSeek/本地回退解析、资产归一、行情补齐、字段证据与人工核对契约。

### Modified Capabilities

- `dashboard-api`: 新增 OCR 配置查询和只读文字解析接口，不改变现有交易计划预览与确认语义。

## Impact

- 前端新增 OCR 组件、hook、类型及 Tesseract.js 依赖。
- 后端新增 `src/snapshot_import/` 模块和两个只读 API。
- 新增 DeepSeek 环境变量配置与隐私说明；不迁移 SQLite，不持久化原图或 OCR 草稿。
- README 与架构地图补充“截图 → OCR → 核对 → 快照 → 交易计划”的能力边界。

