## ADDED Requirements

### Requirement: Initial build allocation must enforce group constraints
The `_initial_build_allocation` function SHALL apply factor group constraints after completing the opportunity-score-based allocation.

#### Scenario: VALUE group exceeds 60% cap in initial build
- **WHEN** initial build allocation results in VALUE group (白酒+银行+红利+沪深300) exceeding 60% of total new money
- **THEN** allocations for VALUE group assets SHALL be scaled down proportionally
- **AND** overflow SHALL be redirected to 国债ETF

#### Scenario: GROWTH group within 15% cap is unaffected
- **WHEN** GROWTH group (科创50) is at or below 15% cap
- **THEN** 科创50 allocation SHALL not be modified

#### Scenario: Both groups within caps
- **WHEN** all factor groups are within their respective caps after allocation
- **THEN** no scaling SHALL occur
