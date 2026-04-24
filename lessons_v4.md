# Lessons Learned - v4

## Trade #1 - FF/USDT (20 Apr 2026)
- Entry: $0.07432 (near 24h high 94%)
- Vol ratio: 0.3x (exhaustion)
- Near support: 3.67% (too far)
- RSI 15m: 59.3

## Fixes Needed
1. Penalty for vol_ratio < 0.8
2. Reject if position in 24h range > 80%
3. Reject if near_support > 2.5%

## Trade #1 - CLOSED (Result)
- Exit: $0.07410 after 8.1 min
- Result: SL hit -0.30% = -$0.50 net
- Confirmation: نتا قلتي "دخل فقمة" وكنتي صحيح

## Applied Fixes (v4.1)
- Volume penalty: vol_ratio < 0.8 = -15 score
- 24h range: REJECT if position > 80%
- Support distance: REJECT if > 2.5%
