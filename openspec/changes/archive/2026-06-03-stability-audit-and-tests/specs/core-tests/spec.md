## ADDED Requirements

### Requirement: Factor scoring unit tests
The system SHALL have unit tests covering all factor computation logic.

#### Scenario: 银行ETF composite z-score with equal weights
- **WHEN** PB z-score is -0.5 and dividend z-score is 0.5
- **THEN** composite z-score SHALL equal 0.0 ((-0.5 + 0.5) / 2)

#### Scenario: Sigmoid maps zero to 0.5
- **WHEN** composite z-score is 0.0
- **THEN** sigmoid output SHALL equal 0.5

#### Scenario: 科创50 trend OFF halves momentum score
- **WHEN** price is below MA200 and momentum_percentile is 0.8
- **THEN** kechuang opportunity score SHALL equal 0.4 (0.8 × 0.5)

### Requirement: Thermometer unit tests
The system SHALL have unit tests covering temperature logic.

#### Scenario: Both indicators > 90% triggers 30% equity
- **WHEN** PE percentile is 0.95 and PB percentile is 0.92
- **THEN** equity_ratio SHALL return (0.30, 0.70)

#### Scenario: Both indicators < 60% triggers 100% equity
- **WHEN** PE percentile is 0.40 and PB percentile is 0.50
- **THEN** equity_ratio SHALL return (1.00, 0.00)

#### Scenario: Inconsistent indicators freeze previous ratio
- **GIVEN** previous state is (0.70, 0.30)
- **WHEN** PE percentile is 0.95 and PB percentile is 0.50 (tiers disagree)
- **THEN** equity_ratio SHALL return (0.70, 0.30)

### Requirement: Constraint unit tests
The system SHALL have unit tests covering constraint logic.

#### Scenario: VALUE group over limit prevents buying
- **WHEN** VALUE group weight (白酒+银行+红利+沪深300) is 65% (> 60% cap)
- **THEN** buy_coefficient for all VALUE assets SHALL be 0

#### Scenario: Asset near upper limit gets reduced coefficient
- **WHEN** 红利 current weight is 24% and upper limit is 25%
- **THEN** buy_coefficient SHALL equal 0.2 ((25-24) / 5)

### Requirement: Allocation unit tests
The system SHALL have unit tests covering allocation logic.

#### Scenario: All gaps zero uses pure opportunity score
- **WHEN** all gap_scores are 0 and opportunity scores are [0.9 for 红利, 0.5 for 科创]
- **THEN** priority SHALL use opportunity scores only (all_gaps_zero path)
- **AND** 红利 SHALL receive allocation before 科创50

#### Scenario: Mixed priority combines gap and opportunity
- **WHEN** gap scores are [A=0.1, B=0] and opportunity scores are [A=0.2, B=0.9]
- **THEN** priority for A SHALL be 0.5×0.1+0.5×0.2=0.15
- **AND** priority for B SHALL be 0.5×0+0.5×0.9=0.45

### Requirement: Integration tests
The system SHALL have end-to-end integration tests covering key scenarios.

#### Scenario: Overheat market limits equity allocation
- **GIVEN** PE percentile > 90% and PB percentile > 90%
- **WHEN** new_money is 10000 and VALUE group is at 65%
- **THEN** equity allocation SHALL be approximately 3000 (30% of 10000)
- **AND** 国债ETF SHALL receive approximately 7000

#### Scenario: Undervalued market with large gap fills deficit first
- **GIVEN** PE percentile < 60%, PB percentile < 60%, 白酒 at 5% (below 12% lower)
- **WHEN** new_money is 10000
- **THEN** equity allocation SHALL prioritize 白酒 to reach lower bound
- **AND** remaining equity SHALL be distributed by opportunity score

### Requirement: Regression tests
The system SHALL have regression tests for stability.

#### Scenario: Parameter boundary test does not crash
- **WHEN** temperature thresholds are set to extreme values (0% and 100%)
- **THEN** system SHALL not crash and SHALL return valid allocation

#### Scenario: Missing data handled gracefully
- **WHEN** dividend data is missing for 红利ETF
- **THEN** system SHALL skip 红利ETF in scoring and SHALL log a warning
- **AND** remaining assets SHALL be allocated normally
