## ADDED Requirements

### Requirement: Thermometer first-run default equity ratio
The thermometer SHALL return a default equity ratio of 70% when both indicators (PE and PB) are inconsistent AND no prior state exists.

#### Scenario: First call with inconsistent indicators
- **WHEN** `equity_ratio(p1=0.95, p2=0.50)` is called with no prior state
- **THEN** system SHALL return (0.70, 0.30) representing 70% equity, 30% bonds

#### Scenario: First call with data missing
- **WHEN** `equity_ratio(p1=None, p2=None)` is called with no prior state
- **THEN** system SHALL return (0.70, 0.30)

#### Scenario: Subsequent call with history uses frozen state
- **WHEN** prior state is (0.70, 0.30) and indicators are inconsistent
- **THEN** system SHALL return (0.70, 0.30) — the frozen prior state
