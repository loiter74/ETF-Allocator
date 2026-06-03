## ADDED Requirements

### Requirement: Allocation cards display stock codes
The frontend AllocationCardsWidget SHALL display each ETF's stock code below or alongside the asset name.

#### Scenario: Card shows stock code
- **WHEN** the allocation card for 白酒ETF renders with code "161725"
- **THEN** the card SHALL display "(代码 161725)" in grey text below the asset name

#### Scenario: Code is available in API response
- **WHEN** the GET /api/report endpoint returns allocations
- **THEN** each allocation entry SHALL include a "code" field with the ETF's tracking code
