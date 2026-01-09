# XLS Report Enhancement Plan

## Executive Summary

This document outlines the necessary updates to the admin XLS report to incorporate new data types and functionality that have been added to the casino management system. The XLS report currently lags behind the JSON summary in several key areas.

## Current XLS Report Structure

The XLS report ([`backend/app/api/report.py`](../backend/app/api/report.py)) currently contains 4 sheets:

1. **Состояние столов** (Table States) - Per-seat totals per table/session
2. **Хронология покупок** (Chip Purchase Chronology) - All chip purchases
3. **Зарплаты персонала** (Staff Salaries) - Staff hours and salary calculations
4. **Итоги дня** (Summary) - Profit/expense overview

## New Data Types Identified

### 1. Payment Type (`payment_type`)
- **Added to:** [`chip_purchases`](../backend/app/models/db.py:104-133) table
- **Values:** "cash" or "credit"
- **Current Status:**
  - ✅ Included in JSON summary (separates buyin_cash vs buyin_credit)
  - ❌ NOT shown in XLS "Хронология покупок" sheet
- **Impact:** Critical for understanding cash vs credit revenue

### 2. Casino Balance Adjustments
- **Added to:** New [`casino_balance_adjustments`](../backend/app/models/db.py:136-153) table
- **Fields:** id, created_at, amount, comment, created_by_user_id
- **Current Status:**
  - ✅ Included in JSON summary with profit/expense separation
  - ❌ NOT shown in XLS report at all
- **Impact:** Major - adjustments affect daily profit/loss calculations

### 3. Rake In/Out (`rake_in`, `rake_out`)
- **Added to:** [`sessions`](../backend/app/models/db.py:48-74) table
- **Current Status:**
  - ❌ Migrations exist in [`main.py`](../backend/app/main.py:72-83) but NOT used in codebase
  - ❌ NOT shown in XLS report
  - ❌ NOT shown in JSON summary
- **Impact:** Unknown - appears to be prepared for future functionality

### 4. Chips In Play (`chips_in_play`)
- **Added to:** [`sessions`](../backend/app/models/db.py:63) table
- **Current Status:**
  - ✅ Shown in XLS "Состояние столов" sheet (line 502)
  - ✅ Shown in JSON summary as informational data
- **Impact:** Informational - no changes needed

### 5. Credit Tracking
- **Derived from:** `payment_type = "credit"` in chip purchases
- **Current Status:**
  - ✅ Credit purchases tracked separately
  - ✅ Credit closing functionality exists ([`close-credit`](../backend/app/api/admin.py:541-644) endpoint)
  - ❌ NOT shown in XLS report
  - ✅ Shown in JSON summary (buyin_credit as expense)
- **Impact:** Critical - credit represents casino expenses that need to be collected

## Detailed Discrepancies Analysis

### JSON Summary vs XLS Report Comparison

| Data Element | JSON Summary | XLS Report | Gap |
|-------------|--------------|------------|-----|
| Cash buyins | ✅ Shown as income | ❌ Combined with credit | **High** |
| Credit buyins | ✅ Shown as expense | ❌ Combined with cash | **High** |
| Balance adjustments (profit) | ✅ Shown as income | ❌ Missing | **Critical** |
| Balance adjustments (expense) | ✅ Shown as expense | ❌ Missing | **Critical** |
| Payment type per purchase | ❌ Not in summary | ❌ Missing | **Medium** |
| Credit by player | ✅ In closed sessions | ❌ Missing | **Medium** |
| Chips in play | ✅ Shown | ✅ Shown | None |
| Staff salaries | ✅ Shown | ✅ Shown | None |

### Formula Discrepancy

**JSON Summary Formula** ([`report.py:239`](../backend/app/api/report.py:239)):
```python
casino_result = total_chip_income_cash - total_player_balance - total_salary 
                - total_chip_income_credit + total_balance_adjustments_profit 
                - total_balance_adjustments_expense
```

**XLS Summary Formula** ([`report.py:727`](../backend/app/api/report.py:727)):
```python
casino_result = total_chip_income_cash - total_player_balance - total_salary 
                - total_chip_income_credit
```

**Missing in XLS:** `+ total_balance_adjustments_profit - total_balance_adjustments_expense`

## Proposed Changes

### Priority 1: Critical Changes (Must Implement)

#### 1.1 Add Payment Type Column to "Хронология покупок" Sheet

**Location:** [`_create_purchases_sheet()`](../backend/app/api/report.py:546-591)

**Current headers:**
```python
headers = ["Время", "Стол", "Место", "Сумма", "Выдал"]
```

**Proposed headers:**
```python
headers = ["Время", "Стол", "Место", "Сумма", "Тип оплаты", "Выдал"]
```

**Implementation:**
- Add "Тип оплаты" column after "Сумма"
- Display "наличные" for "cash", "кредит" for "credit"
- Apply color coding: **dark green** for cash, **dark red** for credit

#### 1.2 Add Balance Adjustments Sheet

**New sheet:** "Корректировки баланса"

**Purpose:** Show all balance adjustments for the working day with profit/expense separation

**Structure:**
```python
headers = ["Время", "Тип", "Сумма", "Комментарий", "Создал"]
```

**Columns:**
- Время: Timestamp of adjustment
- Тип: "Доход" (positive) or "Расход" (negative)
- Сумма: Amount with color coding (green for positive, red for negative)
- Комментарий: Adjustment comment
- Создал: Username of user who created adjustment

**Implementation:**
- Create new function `_create_balance_adjustments_sheet()`
- Fetch balance adjustments for the working day
- Calculate totals: profit and expense
- Call from [`export_report()`](../backend/app/api/report.py:360-449)

#### 1.3 Update "Итоги дня" Sheet Formula

**Location:** [`_create_summary_sheet()`](../backend/app/api/report.py:649-756)

**Changes needed:**

1. **Add Balance Adjustments to Income Section:**
```python
ws.cell(row=row, column=1, value="Корректировки баланса (доход):")
ws.cell(row=row, column=2, value=total_balance_adjustments_profit)
ws.cell(row=row, column=2).fill = MONEY_POSITIVE_FILL
row += 1
```

2. **Add Balance Adjustments to Expense Section:**
```python
ws.cell(row=row, column=1, value="Корректировки баланса (расход):")
ws.cell(row=row, column=2, value=total_balance_adjustments_expense)
ws.cell(row=row, column=2).fill = MONEY_NEGATIVE_FILL
row += 1
```

3. **Update Casino Result Formula:**
```python
casino_result = total_chip_income_cash - total_player_balance - total_salary 
                - total_chip_income_credit + total_balance_adjustments_profit 
                - total_balance_adjustments_expense
```

### Priority 2: Important Changes (Should Implement)

#### 2.1 Separate Cash and Credit in "Хронология покупок" Sheet

**Option A: Add color coding only**
- Keep single list but apply different colors based on payment_type
- Green for cash, red for credit

**Option B: Split into two sections**
- Section 1: "Покупки за наличные"
- Section 2: "Покупки в кредит"

**Recommendation:** Option A for simplicity, Option B for clarity

#### 2.2 Add Credit Summary to "Итоги дня" Sheet

**Add to Reference Section:**
```python
ws.cell(row=row, column=1, value="Выдано в кредит:")
ws.cell(row=row, column=2, value=total_chip_income_credit)
row += 1
```

### Priority 3: Nice to Have (Future Enhancements)

#### 3.1 Add Credit by Player Sheet

**New sheet:** "Кредит по игрокам"

**Purpose:** Show outstanding credit per player from closed sessions

**Structure:**
```python
headers = ["Стол", "Дата", "Место", "Игрок", "Сумма кредита"]
```

**Implementation:**
- Query closed sessions with credit purchases
- Group by seat_no and player_name
- Sum credit amounts
- Display in new sheet

#### 3.2 Prepare for Rake In/Out (When Implemented)

**Note:** Rake columns exist in database but are not used yet

**Future implementation:**
- Add rake_in and rake_out to session calculations
- Include in "Итоги дня" sheet
- Possibly add separate "Рейк" sheet

## Implementation Order

### Phase 1: Critical Fixes (Immediate)
1. Add payment_type column to "Хронология покупок"
2. Create "Корректировки баланса" sheet
3. Update "Итоги дня" formula to include balance adjustments
4. Test that XLS result matches JSON summary

### Phase 2: Important Enhancements (Short-term)
1. Add color coding for payment types
2. Add credit summary to reference section
3. Verify all calculations are correct

### Phase 3: Future Enhancements (When Needed)
1. Add credit by player sheet
2. Implement rake tracking when functionality is activated
3. Add any other new data types that emerge

## Testing Checklist

After implementation, verify:

- [ ] XLS report downloads successfully
- [ ] All 4 (or 5) sheets are present
- [ ] Payment type column shows correct values
- [ ] Balance adjustments sheet shows all adjustments for the day
- [ ] Balance adjustments are properly categorized as income/expense
- [ ] "Итоги дня" result matches JSON summary result
- [ ] Cash and credit totals are separated correctly
- [ ] Color coding is applied correctly
- [ ] All formulas calculate correctly
- [ ] File can be opened in Excel without errors

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing XLS format | High | Keep existing sheets, add new ones |
| Formula errors | High | Thorough testing with sample data |
| Performance issues | Medium | Optimize queries if needed |
| User confusion | Low | Keep layout consistent with current design |

## Dependencies

- No external dependencies required
- Uses existing openpyxl library
- Uses existing database queries
- No API changes required

## Success Criteria

The XLS report enhancement will be considered successful when:

1. XLS report result matches JSON summary result exactly
2. All balance adjustments for the day are visible
3. Payment types are clearly distinguished
4. Report can be generated for any working day
5. No existing functionality is broken

## Files to Modify

1. [`backend/app/api/report.py`](../backend/app/api/report.py) - Main implementation
   - Modify `_create_purchases_sheet()` function
   - Add `_create_balance_adjustments_sheet()` function
   - Modify `_create_summary_sheet()` function
   - Update `export_report()` function to call new sheet

## Estimated Complexity

- **Priority 1 changes:** Medium complexity
- **Priority 2 changes:** Low complexity
- **Priority 3 changes:** Medium complexity

Total implementation time will depend on testing and validation requirements.
