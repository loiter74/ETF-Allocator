## ADDED Requirements

### Requirement: Apply buy_coefficients from constraints module to allocation
The `allocate()` function SHALL accept an optional `buy_coefficients` parameter that scales each asset's maximum buy amount.

#### Scenario: Asset with 20% coefficient gets reduced allocation
- **WHEN** an asset has buy_coefficient=0.2 and would otherwise receive ¥5000
- **THEN** its max_buy SHALL be scaled to min(original_max, coefficient × total_assets) or the equivalent scaling

#### Scenario: Missing buy_coefficients uses full allocation
- **WHEN** `buy_coefficients` parameter is None (default)
- **THEN** allocation SHALL proceed with unmodified upper limits (backward compatible)

#### Scenario: Zero coefficient prevents any allocation
- **WHEN** an asset has buy_coefficient=0
- **THEN** it SHALL receive no allocation regardless of opportunity score or gap
