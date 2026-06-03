## ADDED Requirements

### Requirement: 三页面导航
系统 SHALL 提供顶部导航栏，包含三个页面的切换入口和当前日期显示。

#### Scenario: 页面切换
- **WHEN** 用户点击导航栏中的"本月概览"/"模拟器"/"趋势"
- **THEN** 页面切换至对应视图，导航项高亮当前页

### Requirement: 本月概览页面
系统 SHALL 在 `/dashboard` 展示市场温度计卡片、组合风险卡片和权益分配列表。

#### Scenario: 温度计卡片
- **WHEN** 页面加载成功获取数据
- **THEN** 显示沪深300 PE 分位进度条、全A PB 分位进度条、权益/国债比例和状态标签（正常/过热）

#### Scenario: 分配列表
- **WHEN** 页面加载成功获取数据
- **THEN** 每个资产一行，显示名称、金额、机会分、进度条（仓位/上限）、触发原因

#### Scenario: 数据加载中
- **WHEN** API 请求未完成
- **THEN** 各卡片显示骨架屏（skeleton），不展示空白区域

### Requirement: 模拟器页面
系统 SHALL 在 `/simulate` 提供仓位输入和分配计算功能。

#### Scenario: 仓位输入
- **WHEN** 用户进入模拟器页面
- **THEN** 显示 6 个资产的滑块/输入框，总资产和新增资金输入框，默认值为当前月份配置

#### Scenario: 计算分配
- **WHEN** 用户点击"计算分配"按钮
- **THEN** 调用 POST /api/report 传入用户输入的仓位，右侧显示各资产分配金额和投后仓位

#### Scenario: 投后结构展示
- **WHEN** 分配计算完成
- **THEN** 显示投入前→投入后的仓位对比表，标注是否接近/超过上限

### Requirement: 趋势页面
系统 SHALL 在 `/trends` 以折线图展示各指数 PE 分位的 5 年历史走势。

#### Scenario: 指数选择
- **WHEN** 用户进入趋势页
- **THEN** 默认显示沪深300 PE 分位折线图，底部提供指数切换按钮（白酒/银行/红利/科创50/全A）

#### Scenario: 分位线标记
- **WHEN** 折线图渲染完成
- **THEN** 在 90% 分位处显示红色虚线，标注"过热阈值"

### Requirement: 明亮配色与毛玻璃
系统 SHALL 使用明亮底色（`#F8F6FF`）和毛玻璃效果（`bg-white/70 backdrop-blur-lg`）作为全局视觉风格。

#### Scenario: 卡片悬停
- **WHEN** 用户鼠标悬停在任意卡片上
- **THEN** 卡片轻微上浮（`translateY(-2px)`）并增强阴影，过渡动画 200ms
