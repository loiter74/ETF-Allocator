## 1. Thermometer Initial State Fix

- [x] 1.1 Modify `src/regime/thermometer.py`: change first-run default from (1.0, 0.0) to (0.70, 0.30) in `equity_ratio()` lines 59 and 76
- [x] 1.2 Add `THERMOMETER_DEFAULT_EQUITY` to config/settings.py (value: 0.70)
- [x] 1.3 Update existing thermometer unit tests to reflect new default

## 2. Initial Build Constraints Fix

- [x] 2.1 Modify `_initial_build_allocation()` in `src/allocation/allocator.py`: call `_apply_group_constraint()` before returning
- [x] 2.2 Pass `current_weights` (all zeros) and `total_assets` (0) to constraint function
- [x] 2.3 Write unit test verifying VALUE group ≤ 60% after initial build allocation

## 3. Constraint Integration

- [x] 3.1 Add optional `buy_coefficients: Optional[Dict[str, float]]` parameter to `allocate()` signature
- [x] 3.2 In allocate(), when buy_coefficients is provided, scale max_buy by coefficient
- [x] 3.3 In `src/api/server.py` GET endpoint line 120: pass `cons["buy_coefficients"]` to allocate()
- [x] 3.4 In `src/api/server.py` POST endpoint: same integration
- [x] 3.5 In `run.py`: same integration for CLI mode
- [x] 3.6 Write unit test verifying coefficient=0 prevents allocation

## 4. Frontend Stock Codes

- [x] 4.1 Add `code` field to AllocationItem type in `dashboard/src/types.ts`
- [x] 4.2 Update `AllocationCardsWidget` to display `(代码 {code})` below asset name
- [x] 4.3 Add `code` to widget props interface
- [x] 4.4 Wire code from `useDashboardData` to widget
- [x] 4.5 Verify with playwright: cards show stock codes

## 5. Unit Tests — Factor Layer

- [x] 5.1 Write `test_factors_bank_composite.py`: bank composite z-score = (PB_z + dividend_z) / 2
- [x] 5.2 Write `test_factors_kechuang_trend.py`: trend OFF halves momentum score
- [x] 5.3 Write `test_scoring_sigmoid.py`: sigmoid(0) = 0.5, sigmoid(±2) ≈ 0.12/0.88
- [x] 5.4 Run `pytest tests/unit/test_factors_bank*.py tests/unit/test_factors_kechuang*.py -v`

## 6. Unit Tests — Thermometer

- [x] 6.1 Write `test_regime_initial.py`: first call with inconsistent indicators returns 0.70
- [x] 6.2 Write `test_regime_overheat.py`: both >90% returns 0.30
- [x] 6.3 Write `test_regime_cool.py`: both <60% returns 1.00
- [x] 6.4 Write `test_regime_freeze.py`: inconsistent with prior state preserves previous
- [x] 6.5 Run `pytest tests/unit/test_regime*.py -v`

## 7. Unit Tests — Constraints

- [x] 7.1 Write `test_constraints_value_over.py`: VALUE 65% → coefficients all 0
- [x] 7.2 Write `test_constraints_near_limit.py`: asset at 24%/25% → coefficient 0.2
- [x] 7.3 Run `pytest tests/unit/test_constraints*.py -v`

## 8. Unit Tests — Allocation

- [x] 8.1 Write `test_allocation_gaps_zero.py`: all gaps=0 uses pure opportunity score order
- [x] 8.2 Write `test_allocation_mixed.py`: mixed gap+opportunity priority computation
- [x] 8.3 Write `test_allocation_coefficient.py`: buy_coefficient scaling works
- [x] 8.4 Run `pytest tests/unit/test_allocation*.py -v`

## 9. Integration Tests

- [x] 9.1 Write `test_integration_overheat.py`: PE>90%, PB>90% → equity 30%, bonds get ~70% of new money
- [x] 9.2 Write `test_integration_undervalue.py`: PE<60%, PB<60% → equity 100%, fill gaps first
- [x] 9.3 Write `test_integration_rebalance.py`: rebalance triggers at 12% deviation from midpoint
- [x] 9.4 Write `test_integration_no_future.py`: verify publish_date filter in backtest
- [x] 9.5 Run `pytest tests/integration/ -v -m integration`

## 10. Regression Tests & Cleanup

- [x] 10.1 Write `test_regression_boundary.py`: extreme temperature thresholds → no crash
- [x] 10.2 Write `test_regression_missing_data.py`: missing dividend → skip asset, warn, continue
- [x] 10.3 Run full test suite: `pytest tests/ -v`
- [x] 10.4 Fix any test conflicts from existing tests that assumed old (1.0,0.0) default
