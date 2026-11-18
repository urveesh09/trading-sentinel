# Round 10 tables (development screen on studied sessions; descriptive only)

Columns:
- independent-session net (ordinary, adverse) and parents;
- ordinary net without the best two days;
- continuous ₹30,000 wallet P (ordinary / adverse; H = halted);
- versus the primary comparator: adverse paired sum, the same without the best two days, and changed parents;
- support label;
- adverse net with entry one bar later.

Learned EN118/EN120 rows cover the walk-forward dates 100–196 only.

## REF — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `REF:E032_native` |  | 14,275 | 11,586 | 66 | 652 | -4,123 / -4,036 H | — | — | 3,642 |
| `REF:E03_env` |  | 3,006 | 2,246 | 55 | -1,298 | -3,445 / -4,035 H | — | — | 4,795 |
| `REF:EN55_native` |  | 13,165 | 11,056 | 68 | 1,045 | 3,445 / 11,573 | — | — | -2,480 |
| `REF:EN87` |  | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | — | — | 5,590 |
| `REF:EN87_ONE_LOT` |  | 3,735 | 3,063 | 25 | 1,155 | 3,735 / 3,063 | — | — | 4,022 |

## REF — SENSEX

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `REF:E032_native` |  | 2,449 | 1,921 | 12 | -4,089 | 1,987 / 1,516 | — | — | — |
| `REF:E03_env` |  | 5,167 | 4,746 | 7 | -1,372 | 4,501 / 4,114 | — | — | — |
| `REF:EN55_native` |  | 2,470 | 2,237 | 10 | -3,008 | 2,470 / 2,237 | — | — | — |

## EN111 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN111:0001` | contract=LEGACY_UP_TO_3, target=1, hold=8 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN111:0002` | contract=LEGACY_UP_TO_3, target=1, hold=10 | 6,855 | 6,789 | 25 | 2,679 | 6,508 / 6,095 | EN87: 949 / x2 -481 (12 ch) | SPARSE ECONOMIC SCREEN | 5,519 |
| `EN111:0003` | contract=LEGACY_UP_TO_3, target=1, hold=12 | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN111:0004` | contract=LEGACY_UP_TO_3, target=1.25, hold=8 | 8,097 | 7,642 | 25 | 3,094 | 7,289 / 6,750 | EN87: 1,801 / x2 0 (3 ch) | ACTIVATION-LIMITED | 5,856 |
| `EN111:0005` | contract=LEGACY_UP_TO_3, target=1.25, hold=10 | 7,961 | 7,723 | 25 | 2,967 | 7,614 / 7,029 | EN87: 1,883 / x2 -40 (15 ch) | SPARSE ECONOMIC SCREEN | 5,785 |
| `EN111:0006` | contract=LEGACY_UP_TO_3, target=1.25, hold=12 | 9,067 | 8,700 | 25 | 4,073 | 9,291 / 8,291 | EN87: 2,859 / x2 625 (15 ch) | SPARSE ECONOMIC SCREEN | 6,794 |
| `EN111:0007` | contract=LEGACY_UP_TO_3, target=1.5, hold=8 | 11,174 | 10,690 | 25 | 5,529 | 10,366 / 9,797 | EN87: 4,849 / x2 1,801 (4 ch) | ACTIVATION-LIMITED | 6,646 |
| `EN111:0008` | contract=LEGACY_UP_TO_3, target=1.5, hold=10 | 7,497 | 7,205 | 25 | 2,040 | 7,149 / 5,119 | EN87: 1,364 / x2 -1,185 (16 ch) | SPARSE ECONOMIC SCREEN | 3,746 |
| `EN111:0009` | contract=LEGACY_UP_TO_3, target=1.5, hold=12 | 7,876 | 7,341 | 25 | 2,882 | 8,100 / 6,932 | EN87: 1,500 / x2 -734 (16 ch) | SPARSE ECONOMIC SCREEN | 4,755 |
| `EN111:0010` | contract=NEARER_ONE_LOT, target=1, hold=8 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87: 2,074 / x2 305 (24 ch) | SCREENED | 7,157 |
| `EN111:0011` | contract=NEARER_ONE_LOT, target=1, hold=10 | 8,862 | 7,463 | 25 | 3,776 | 8,690 / 7,354 | EN87: 1,623 / x2 -673 (24 ch) | SCREENED | 5,895 |
| `EN111:0012` | contract=NEARER_ONE_LOT, target=1, hold=12 | 11,775 | 9,604 | 25 | 6,552 | 8,455 / 7,224 | EN87: 3,764 / x2 1,464 (24 ch) | SCREENED | 6,826 |
| `EN111:0013` | contract=NEARER_ONE_LOT, target=1.25, hold=8 | 8,965 | 7,551 | 25 | 4,613 | 9,167 / 7,808 | EN87: 1,710 / x2 -111 (24 ch) | SCREENED | 6,592 |
| `EN111:0014` | contract=NEARER_ONE_LOT, target=1.25, hold=10 | 6,341 | 4,979 | 25 | 1,842 | 6,170 / 4,322 | EN87: -862 / x2 -3,067 (24 ch) | SCREENED | 4,795 |
| `EN111:0015` | contract=NEARER_ONE_LOT, target=1.25, hold=12 | 10,049 | 7,898 | 25 | 4,045 | 6,729 / 5,518 | EN87: 2,057 / x2 -1,017 (24 ch) | SCREENED | 4,756 |
| `EN111:0016` | contract=NEARER_ONE_LOT, target=1.5, hold=8 | 8,965 | 7,551 | 25 | 4,613 | 9,167 / 7,808 | EN87: 1,710 / x2 -111 (24 ch) | SCREENED | 6,592 |
| `EN111:0017` | contract=NEARER_ONE_LOT, target=1.5, hold=10 | 6,341 | 4,979 | 25 | 1,842 | 6,170 / 4,322 | EN87: -862 / x2 -3,067 (24 ch) | SCREENED | 5,570 |
| `EN111:0018` | contract=NEARER_ONE_LOT, target=1.5, hold=12 | 10,049 | 7,898 | 25 | 4,045 | 6,729 / 5,518 | EN87: 2,057 / x2 -1,017 (24 ch) | SCREENED | 5,531 |
| `EN111:ctl:equal_one_lot_t1.0_h10` | legacy contract at one lot: the contract-mechanism companion | 4,601 | 3,990 | 25 | 1,849 | 4,601 / 3,990 | EN87: -1,850 / x2 -2,858 (24 ch) | SCREENED | 4,142 |
| `EN111:ctl:equal_one_lot_t1.0_h12` | legacy contract at one lot: the contract-mechanism companion | 5,162 | 4,506 | 25 | 2,410 | 5,162 / 4,506 | EN87: -1,334 / x2 -2,546 (24 ch) | SCREENED | 4,661 |
| `EN111:ctl:equal_one_lot_t1.0_h8` | legacy contract at one lot: the contract-mechanism companion | 3,735 | 3,063 | 25 | 1,155 | 3,735 / 3,063 | EN87: -2,778 / x2 -3,776 (24 ch) | SCREENED | 4,022 |
| `EN111:ctl:equal_one_lot_t1.25_h10` | legacy contract at one lot: the contract-mechanism companion | 5,299 | 4,519 | 25 | 2,465 | 5,299 / 4,519 | EN87: -1,322 / x2 -2,329 (24 ch) | SCREENED | 4,408 |
| `EN111:ctl:equal_one_lot_t1.25_h12` | legacy contract at one lot: the contract-mechanism companion | 5,860 | 5,035 | 25 | 3,027 | 5,860 / 5,035 | EN87: -806 / x2 -2,018 (24 ch) | SCREENED | 4,927 |
| `EN111:ctl:equal_one_lot_t1.25_h8` | legacy contract at one lot: the contract-mechanism companion | 4,205 | 3,368 | 25 | 1,726 | 4,205 / 3,368 | EN87: -2,473 / x2 -3,471 (24 ch) | SCREENED | 4,288 |
| `EN111:ctl:equal_one_lot_t1.5_h10` | legacy contract at one lot: the contract-mechanism companion | 3,190 | 2,262 | 25 | 357 | 3,190 / 2,262 | EN87: -3,579 / x2 -4,587 (24 ch) | SCREENED | 2,056 |
| `EN111:ctl:equal_one_lot_t1.5_h12` | legacy contract at one lot: the contract-mechanism companion | 3,388 | 2,378 | 25 | 849 | 3,388 / 2,378 | EN87: -3,462 / x2 -4,674 (24 ch) | SCREENED | 2,575 |
| `EN111:ctl:equal_one_lot_t1.5_h8` | legacy contract at one lot: the contract-mechanism companion | 4,533 | 3,692 | 25 | 1,758 | 4,533 / 3,692 | EN87: -2,149 / x2 -3,146 (24 ch) | SCREENED | 3,350 |
| `EN111:ctl:no_partial_t1.0_h12` | target sells every lot (no half-sale, no runner) | 13,271 | 13,179 | 25 | 7,671 | 13,026 / 12,309 | EN87: 7,339 / x2 4,376 (17 ch) | SPARSE ECONOMIC SCREEN | 9,931 |
| `EN111:ctl:no_partial_t1.0_h8` | target sells every lot (no half-sale, no runner) | 10,407 | 10,250 | 25 | 5,153 | 9,131 / 8,896 | EN87: 4,409 / x2 1,916 (5 ch) | SPARSE ECONOMIC SCREEN | 8,993 |
| `EN111:ctl:no_partial_t1.5_h12` | target sells every lot (no half-sale, no runner) | 10,131 | 9,115 | 25 | 3,812 | 9,886 / 8,245 | EN87: 3,274 / x2 39 (17 ch) | SPARSE ECONOMIC SCREEN | 5,759 |
| `EN111:ctl:no_partial_t1.5_h8` | target sells every lot (no half-sale, no runner) | 12,411 | 11,914 | 25 | 6,164 | 11,135 / 10,560 | EN87: 6,074 / x2 2,870 (5 ch) | SPARSE ECONOMIC SCREEN | 7,650 |

## EN112 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN112:0001` | context=EXTENSION_RANK, assignment=FRESH_GETS_ROOM, profile=TARGET_ONLY | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0002` | context=EXTENSION_RANK, assignment=FRESH_GETS_ROOM, profile=HOLD_ONLY | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0003` | context=EXTENSION_RANK, assignment=FRESH_GETS_ROOM, profile=BOTH | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0004` | context=EXTENSION_RANK, assignment=MATURE_GETS_ROOM, profile=TARGET_ONLY | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0005` | context=EXTENSION_RANK, assignment=MATURE_GETS_ROOM, profile=HOLD_ONLY | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0006` | context=EXTENSION_RANK, assignment=MATURE_GETS_ROOM, profile=BOTH | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0007` | context=ACCELERATION, assignment=FRESH_GETS_ROOM, profile=TARGET_ONLY | 7,922 | 7,470 | 25 | 3,262 | 7,114 / 6,578 | EN87: 1,629 / x2 0 (1 ch) | ACTIVATION-LIMITED | 6,078 |
| `EN112:0008` | context=ACCELERATION, assignment=FRESH_GETS_ROOM, profile=HOLD_ONLY | 6,516 | 6,236 | 25 | 3,047 | 5,708 / 5,344 | EN87: 396 / x2 0 (1 ch) | ACTIVATION-LIMITED | 5,934 |
| `EN112:0009` | context=ACCELERATION, assignment=FRESH_GETS_ROOM, profile=BOTH | 5,619 | 5,186 | 25 | 2,150 | 4,810 / 4,294 | EN87: -654 / x2 -1,050 (2 ch) | ACTIVATION-LIMITED | 4,884 |
| `EN112:0010` | context=ACCELERATION, assignment=MATURE_GETS_ROOM, profile=TARGET_ONLY | 9,366 | 9,060 | 25 | 3,953 | 8,558 / 8,168 | EN87: 3,220 / x2 811 (3 ch) | ACTIVATION-LIMITED | 6,159 |
| `EN112:0011` | context=ACCELERATION, assignment=MATURE_GETS_ROOM, profile=HOLD_ONLY | 7,559 | 7,370 | 25 | 3,093 | 7,782 / 6,961 | EN87: 1,529 / x2 -705 (11 ch) | SPARSE ECONOMIC SCREEN | 5,158 |
| `EN112:0012` | context=ACCELERATION, assignment=MATURE_GETS_ROOM, profile=BOTH | 8,372 | 7,995 | 25 | 3,378 | 8,595 / 7,587 | EN87: 2,155 / x2 -79 (14 ch) | SPARSE ECONOMIC SCREEN | 5,461 |
| `EN112:0013` | context=BOTH, assignment=FRESH_GETS_ROOM, profile=TARGET_ONLY | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0014` | context=BOTH, assignment=FRESH_GETS_ROOM, profile=HOLD_ONLY | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0015` | context=BOTH, assignment=FRESH_GETS_ROOM, profile=BOTH | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0016` | context=BOTH, assignment=MATURE_GETS_ROOM, profile=TARGET_ONLY | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0017` | context=BOTH, assignment=MATURE_GETS_ROOM, profile=HOLD_ONLY | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:0018` | context=BOTH, assignment=MATURE_GETS_ROOM, profile=BOTH | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:r1:0001` | context=EXTENSION_RANK, assignment=FRESH_GETS_ROOM, profile=TARGET_ONLY, rank=rank_all | 7,922 | 7,470 | 25 | 3,262 | 7,114 / 6,578 | EN87: 1,629 / x2 0 (1 ch) | ACTIVATION-LIMITED | 6,078 |
| `EN112:r1:0002` | context=EXTENSION_RANK, assignment=FRESH_GETS_ROOM, profile=HOLD_ONLY, rank=rank_all | 5,349 | 5,088 | 25 | 1,879 | 5,319 / 4,491 | EN87: -753 / x2 -1,148 (2 ch) | ACTIVATION-LIMITED | 4,582 |
| `EN112:r1:0003` | context=EXTENSION_RANK, assignment=FRESH_GETS_ROOM, profile=BOTH, rank=rank_all | 4,451 | 4,038 | 25 | 982 | 4,421 / 3,441 | EN87: -1,803 / x2 -2,198 (3 ch) | ACTIVATION-LIMITED | 3,531 |
| `EN112:r1:0004` | context=EXTENSION_RANK, assignment=MATURE_GETS_ROOM, profile=TARGET_ONLY, rank=rank_all | 6,932 | 6,652 | 25 | 2,645 | 6,123 / 5,759 | EN87: 811 / x2 0 (1 ch) | ACTIVATION-LIMITED | 5,590 |
| `EN112:r1:0005` | context=EXTENSION_RANK, assignment=MATURE_GETS_ROOM, profile=HOLD_ONLY, rank=rank_all | 7,729 | 7,533 | 25 | 3,263 | 7,096 / 6,641 | EN87: 1,692 / x2 -542 (6 ch) | SPARSE ECONOMIC SCREEN | 6,112 |
| `EN112:r1:0006` | context=EXTENSION_RANK, assignment=MATURE_GETS_ROOM, profile=BOTH, rank=rank_all | 8,546 | 8,344 | 25 | 3,552 | 7,913 / 7,452 | EN87: 2,503 / x2 269 (7 ch) | SPARSE ECONOMIC SCREEN | 7,138 |
| `EN112:r1:0013` | context=BOTH, assignment=FRESH_GETS_ROOM, profile=TARGET_ONLY, rank=rank_all | 7,922 | 7,470 | 25 | 3,262 | 7,114 / 6,578 | EN87: 1,629 / x2 0 (1 ch) | ACTIVATION-LIMITED | 6,078 |
| `EN112:r1:0014` | context=BOTH, assignment=FRESH_GETS_ROOM, profile=HOLD_ONLY, rank=rank_all | 6,516 | 6,236 | 25 | 3,047 | 5,708 / 5,344 | EN87: 396 / x2 0 (1 ch) | ACTIVATION-LIMITED | 5,934 |
| `EN112:r1:0015` | context=BOTH, assignment=FRESH_GETS_ROOM, profile=BOTH, rank=rank_all | 5,619 | 5,186 | 25 | 2,150 | 4,810 / 4,294 | EN87: -654 / x2 -1,050 (2 ch) | ACTIVATION-LIMITED | 4,884 |
| `EN112:r1:0016` | context=BOTH, assignment=MATURE_GETS_ROOM, profile=TARGET_ONLY, rank=rank_all | 6,932 | 6,652 | 25 | 2,645 | 6,123 / 5,759 | EN87: 811 / x2 0 (1 ch) | ACTIVATION-LIMITED | 5,590 |
| `EN112:r1:0017` | context=BOTH, assignment=MATURE_GETS_ROOM, profile=HOLD_ONLY, rank=rank_all | 6,561 | 6,385 | 25 | 2,095 | 6,706 / 5,898 | EN87: 544 / x2 -1,690 (7 ch) | SPARSE ECONOMIC SCREEN | 4,759 |
| `EN112:r1:0018` | context=BOTH, assignment=MATURE_GETS_ROOM, profile=BOTH, rank=rank_all | 7,378 | 7,196 | 25 | 2,384 | 7,524 / 6,709 | EN87: 1,355 / x2 -879 (8 ch) | SPARSE ECONOMIC SCREEN | 5,785 |
| `EN112:ctl:fixed_both` | profile given to every entry | 7,876 | 7,341 | 25 | 2,882 | 8,100 / 6,932 | EN87: 1,500 / x2 -734 (16 ch) | SPARSE ECONOMIC SCREEN | 4,755 |
| `EN112:ctl:fixed_hold_only` | profile given to every entry | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN112:ctl:fixed_target_only` | profile given to every entry | 11,174 | 10,690 | 25 | 5,529 | 10,366 / 9,797 | EN87: 4,849 / x2 1,801 (4 ch) | ACTIVATION-LIMITED | 6,646 |
| `EN112:dyn:random_0001` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0002` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0003` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0004` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0005` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0006` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0007` | rate=0.222222 | 7,117 | 6,831 | 25 | 2,932 | 6,309 / 5,939 | EN87: 990 / x2 0 (1 ch) | ACTIVATION-LIMITED | 5,590 |
| `EN112:dyn:random_0008` | rate=0.222222 | 7,245 | 7,050 | 25 | 3,345 | 6,612 / 6,157 | EN87: 1,209 / x2 -309 (5 ch) | SPARSE ECONOMIC SCREEN | 6,100 |
| `EN112:dyn:random_0009` | rate=0.222222 | 7,976 | 7,587 | 25 | 3,774 | 7,343 / 6,694 | EN87: 1,746 / x2 -101 (6 ch) | SPARSE ECONOMIC SCREEN | 6,100 |
| `EN112:dyn:random_0010` | rate=0.777778 | 11,174 | 10,690 | 25 | 5,529 | 10,366 / 9,797 | EN87: 4,849 / x2 1,801 (4 ch) | ACTIVATION-LIMITED | 6,646 |
| `EN112:dyn:random_0011` | rate=0.777778 | 7,248 | 7,052 | 25 | 3,071 | 7,471 / 6,643 | EN87: 1,211 / x2 -582 (10 ch) | SPARSE ECONOMIC SCREEN | 4,633 |
| `EN112:dyn:random_0012` | rate=0.777778 | 7,163 | 6,627 | 25 | 2,169 | 7,386 / 6,219 | EN87: 787 / x2 -1,136 (14 ch) | SPARSE ECONOMIC SCREEN | 2,861 |
| `EN112:dyn:random_0013` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0014` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0015` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0016` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0017` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_0018` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_r1_0001` | rate=0.111111 | 6,932 | 6,652 | 25 | 2,645 | 6,123 / 5,759 | EN87: 811 / x2 0 (1 ch) | ACTIVATION-LIMITED | 5,590 |
| `EN112:dyn:random_r1_0002` | rate=0.111111 | 6,795 | 6,522 | 25 | 3,326 | 5,987 / 5,630 | EN87: 681 / x2 0 (1 ch) | ACTIVATION-LIMITED | 6,009 |
| `EN112:dyn:random_r1_0003` | rate=0.111111 | 7,613 | 7,333 | 25 | 3,326 | 6,805 / 6,440 | EN87: 1,492 / x2 0 (2 ch) | ACTIVATION-LIMITED | 6,009 |
| `EN112:dyn:random_r1_0004` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_r1_0005` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_r1_0006` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_r1_0013` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_r1_0014` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_r1_0015` | rate=0.0 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_r1_0016` | rate=0.111111 | 7,546 | 7,259 | 25 | 2,950 | 6,737 / 6,367 | EN87: 1,418 / x2 0 (1 ch) | ACTIVATION-LIMITED | 6,159 |
| `EN112:dyn:random_r1_0017` | rate=0.111111 | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN112:dyn:random_r1_0018` | rate=0.111111 | 5,379 | 5,118 | 25 | 1,909 | 4,570 / 4,149 | EN87: -722 / x2 -722 (1 ch) | ACTIVATION-LIMITED | 4,868 |

## EN113 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN113:0001` | lag=1, percentile=80, response=DENY_EXTENSION | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:0002` | lag=1, percentile=80, response=EXIT_WITH_GIVEBACK | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,518 |
| `EN113:0003` | lag=1, percentile=90, response=DENY_EXTENSION | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:0004` | lag=1, percentile=90, response=EXIT_WITH_GIVEBACK | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,518 |
| `EN113:0005` | lag=3, percentile=80, response=DENY_EXTENSION | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:0006` | lag=3, percentile=80, response=EXIT_WITH_GIVEBACK | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,651 |
| `EN113:0007` | lag=3, percentile=90, response=DENY_EXTENSION | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:0008` | lag=3, percentile=90, response=EXIT_WITH_GIVEBACK | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:0009` | lag=5, percentile=80, response=DENY_EXTENSION | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:0010` | lag=5, percentile=80, response=EXIT_WITH_GIVEBACK | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:0011` | lag=5, percentile=90, response=DENY_EXTENSION | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:0012` | lag=5, percentile=90, response=EXIT_WITH_GIVEBACK | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:fast_oi_only_L1_p80` | exit on confirmed fast deterioration alone | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,518 |
| `EN113:ctl:fast_oi_only_L1_p90` | exit on confirmed fast deterioration alone | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,518 |
| `EN113:ctl:fast_oi_only_L3_p80` | exit on confirmed fast deterioration alone | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 4,543 |
| `EN113:ctl:fast_oi_only_L3_p90` | exit on confirmed fast deterioration alone | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:fast_oi_only_L5_p80` | exit on confirmed fast deterioration alone | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:fast_oi_only_L5_p90` | exit on confirmed fast deterioration alone | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:fixed12` | fixed 12-minute hold (the family base) | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:price_giveback` | giveback exit without OI | 3,795 | 3,538 | 25 | -1,098 | 3,721 / 3,172 | EN87: -2,303 / x2 -4,019 (20 ch) | SCREENED | 2,490 |
| `EN113:ctl:stale_deny_L1_p80` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:stale_deny_L1_p90` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:stale_deny_L3_p80` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:stale_deny_L3_p90` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:stale_deny_L5_p80` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:stale_deny_L5_p90` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:stale_giveback_L1_p80` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,651 |
| `EN113:ctl:stale_giveback_L1_p90` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,651 |
| `EN113:ctl:stale_giveback_L3_p80` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,735 |
| `EN113:ctl:stale_giveback_L3_p90` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:stale_giveback_L5_p80` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN113:ctl:stale_giveback_L5_p90` | source-lag companion: S_L one bar stale | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |

## EN114 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN114:0001` | activity=4, wall=8, scope=BASE_ONLY | 2,418 | 3,011 | 25 | -1,259 | 2,197 / 1,661 | EN87: -2,830 / x2 -4,138 (17 ch) | SPARSE ECONOMIC SCREEN | 1,603 |
| `EN114:0002` | activity=4, wall=8, scope=BASE_AND_RUNNER | 4,007 | 3,511 | 25 | -253 | 3,786 / 1,983 | EN87: -2,330 / x2 -3,638 (20 ch) | SCREENED | 2,372 |
| `EN114:0003` | activity=4, wall=12, scope=BASE_ONLY | 2,418 | 3,128 | 25 | -1,259 | 2,197 / 1,778 | EN87: -2,713 / x2 -4,021 (17 ch) | SPARSE ECONOMIC SCREEN | 1,603 |
| `EN114:0004` | activity=4, wall=12, scope=BASE_AND_RUNNER | 4,007 | 3,627 | 25 | -253 | 3,786 / 2,099 | EN87: -2,213 / x2 -3,521 (20 ch) | SCREENED | 2,372 |
| `EN114:0005` | activity=4, wall=16, scope=BASE_ONLY | 2,418 | 3,128 | 25 | -1,259 | 2,197 / 1,778 | EN87: -2,713 / x2 -4,021 (17 ch) | SPARSE ECONOMIC SCREEN | 1,603 |
| `EN114:0006` | activity=4, wall=16, scope=BASE_AND_RUNNER | 4,007 | 3,627 | 25 | -253 | 3,786 / 2,099 | EN87: -2,213 / x2 -3,521 (20 ch) | SCREENED | 2,372 |
| `EN114:0007` | activity=8, wall=8, scope=BASE_ONLY | 3,793 | 3,533 | 25 | 117 | 2,881 / 2,540 | EN87: -2,308 / x2 -3,174 (11 ch) | SPARSE ECONOMIC SCREEN | 2,719 |
| `EN114:0008` | activity=8, wall=8, scope=BASE_AND_RUNNER | 5,652 | 5,372 | 25 | 1,123 | 4,558 / 4,201 | EN87: -469 / x2 -2,324 (14 ch) | SPARSE ECONOMIC SCREEN | 3,488 |
| `EN114:0009` | activity=8, wall=12, scope=BASE_ONLY | 4,844 | 4,668 | 25 | 1,168 | 4,049 / 3,753 | EN87: -1,172 / x2 -2,386 (16 ch) | SPARSE ECONOMIC SCREEN | 3,413 |
| `EN114:0010` | activity=8, wall=12, scope=BASE_AND_RUNNER | 5,350 | 5,168 | 25 | 1,168 | 4,373 / 4,074 | EN87: -673 / x2 -1,886 (18 ch) | SPARSE ECONOMIC SCREEN | 3,413 |
| `EN114:0011` | activity=8, wall=16, scope=BASE_ONLY | 4,621 | 4,902 | 25 | 944 | 3,974 / 3,864 | EN87: -939 / x2 -2,152 (16 ch) | SPARSE ECONOMIC SCREEN | 3,676 |
| `EN114:0012` | activity=8, wall=16, scope=BASE_AND_RUNNER | 5,127 | 5,401 | 25 | 944 | 4,299 / 4,185 | EN87: -439 / x2 -1,653 (18 ch) | SPARSE ECONOMIC SCREEN | 3,676 |
| `EN114:0013` | activity=12, wall=8, scope=BASE_ONLY | 6,237 | 5,951 | 25 | 2,561 | 5,325 / 4,958 | EN87: 110 / x2 -470 (5 ch) | SPARSE ECONOMIC SCREEN | 4,829 |
| `EN114:0014` | activity=12, wall=8, scope=BASE_AND_RUNNER | 10,552 | 10,223 | 25 | 5,205 | 9,614 / 9,204 | EN87: 4,382 / x2 1,706 (10 ch) | SPARSE ECONOMIC SCREEN | 7,372 |
| `EN114:0015` | activity=12, wall=12, scope=BASE_ONLY | 6,685 | 6,496 | 25 | 3,008 | 6,448 / 5,987 | EN87: 655 / x2 -480 (13 ch) | SPARSE ECONOMIC SCREEN | 5,208 |
| `EN114:0016` | activity=12, wall=12, scope=BASE_AND_RUNNER | 9,647 | 9,428 | 25 | 4,300 | 9,383 / 8,893 | EN87: 3,588 / x2 1,002 (17 ch) | SPARSE ECONOMIC SCREEN | 6,983 |
| `EN114:0017` | activity=12, wall=16, scope=BASE_ONLY | 6,124 | 6,399 | 25 | 2,447 | 6,036 / 5,734 | EN87: 558 / x2 -577 (13 ch) | SPARSE ECONOMIC SCREEN | 5,471 |
| `EN114:0018` | activity=12, wall=16, scope=BASE_AND_RUNNER | 9,085 | 9,331 | 25 | 3,739 | 8,971 / 8,640 | EN87: 3,490 / x2 905 (17 ch) | SPARSE ECONOMIC SCREEN | 7,246 |
| `EN114:ctl:fixed_12_base_and_runner` | fixed clock also ends runners | 12,104 | 11,859 | 25 | 5,646 | 11,422 / 10,555 | EN87: 6,019 / x2 2,286 (15 ch) | SPARSE ECONOMIC SCREEN | 8,519 |
| `EN114:ctl:fixed_12_base_only` | fixed clock, runners native | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN114:ctl:fixed_16_base_and_runner` | fixed clock also ends runners | 6,404 | 6,692 | 25 | 1,978 | 6,465 / 5,819 | EN87: 851 / x2 -929 (14 ch) | SPARSE ECONOMIC SCREEN | 4,782 |
| `EN114:ctl:fixed_16_base_only` | fixed clock, runners native | 5,415 | 5,716 | 25 | 1,238 | 5,787 / 5,151 | EN87: -125 / x2 -1,772 (12 ch) | SPARSE ECONOMIC SCREEN | 3,948 |
| `EN114:ctl:fixed_4_base_and_runner` | fixed clock also ends runners | 3,363 | 3,177 | 25 | -820 | 3,039 / -296 | EN87: -2,664 / x2 -4,607 (20 ch) | SCREENED | 800 |
| `EN114:ctl:fixed_4_base_only` | fixed clock, runners native | 2,857 | 2,677 | 25 | -820 | 2,533 / -296 | EN87: -3,163 / x2 -5,106 (18 ch) | SPARSE ECONOMIC SCREEN | 800 |
| `EN114:ctl:fixed_8_base_and_runner` | fixed clock also ends runners | 10,613 | 10,294 | 25 | 5,289 | 9,899 / 9,496 | EN87: 4,454 / x2 1,778 (5 ch) | SPARSE ECONOMIC SCREEN | 7,968 |
| `EN114:ctl:fixed_8_base_only` | fixed clock, runners native | 6,114 | 5,841 | 25 | 2,645 | 5,306 / 4,948 | EN87: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 5,590 |
| `EN114:ctl:volratio` | hold = clip(8*sqrt(vref/v0), 4, 16) | 2,204 | 2,093 | 25 | -1,382 | 1,835 / -997 | EN87: -3,748 / x2 -5,710 (17 ch) | SPARSE ECONOMIC SCREEN | 1,720 |
| `EN114:dyn:matched_0001` | hold=6, scope=BASE_ONLY | 1,359 | 2,644 | 25 | -2,110 | 1,508 / 1,291 | EN87: -3,197 / x2 -4,661 (15 ch) | SPARSE ECONOMIC SCREEN | 2,922 |
| `EN114:dyn:matched_0002` | hold=5, scope=BASE_AND_RUNNER | 3,924 | 3,997 | 25 | -435 | 3,787 / 2,667 | EN87: -1,844 / x2 -3,216 (20 ch) | SCREENED | 138 |
| `EN114:dyn:matched_0003` | hold=6, scope=BASE_ONLY | 1,359 | 2,644 | 25 | -2,110 | 1,508 / 1,291 | EN87: -3,197 / x2 -4,661 (15 ch) | SPARSE ECONOMIC SCREEN | 2,922 |
| `EN114:dyn:matched_0004` | hold=5, scope=BASE_AND_RUNNER | 3,924 | 3,997 | 25 | -435 | 3,787 / 2,667 | EN87: -1,844 / x2 -3,216 (20 ch) | SCREENED | 138 |
| `EN114:dyn:matched_0005` | hold=6, scope=BASE_ONLY | 1,359 | 2,644 | 25 | -2,110 | 1,508 / 1,291 | EN87: -3,197 / x2 -4,661 (15 ch) | SPARSE ECONOMIC SCREEN | 2,922 |
| `EN114:dyn:matched_0006` | hold=5, scope=BASE_AND_RUNNER | 3,924 | 3,997 | 25 | -435 | 3,787 / 2,667 | EN87: -1,844 / x2 -3,216 (20 ch) | SCREENED | 138 |
| `EN114:dyn:matched_0007` | hold=7, scope=BASE_ONLY | 4,521 | 4,526 | 25 | 1,052 | 3,492 / 3,446 | EN87: -1,314 / x2 -1,842 (13 ch) | SPARSE ECONOMIC SCREEN | 4,142 |
| `EN114:dyn:matched_0008` | hold=5, scope=BASE_AND_RUNNER | 3,924 | 3,997 | 25 | -435 | 3,787 / 2,667 | EN87: -1,844 / x2 -3,216 (20 ch) | SCREENED | 138 |
| `EN114:dyn:matched_0009` | hold=7, scope=BASE_ONLY | 4,521 | 4,526 | 25 | 1,052 | 3,492 / 3,446 | EN87: -1,314 / x2 -1,842 (13 ch) | SPARSE ECONOMIC SCREEN | 4,142 |
| `EN114:dyn:matched_0010` | hold=5, scope=BASE_AND_RUNNER | 3,924 | 3,997 | 25 | -435 | 3,787 / 2,667 | EN87: -1,844 / x2 -3,216 (20 ch) | SCREENED | 138 |
| `EN114:dyn:matched_0011` | hold=7, scope=BASE_ONLY | 4,521 | 4,526 | 25 | 1,052 | 3,492 / 3,446 | EN87: -1,314 / x2 -1,842 (13 ch) | SPARSE ECONOMIC SCREEN | 4,142 |
| `EN114:dyn:matched_0012` | hold=6, scope=BASE_AND_RUNNER | 4,129 | 4,311 | 25 | -892 | 4,279 / 3,110 | EN87: -1,530 / x2 -3,552 (19 ch) | SPARSE ECONOMIC SCREEN | 5,599 |
| `EN114:dyn:matched_0013` | hold=11, scope=BASE_ONLY | 7,851 | 8,152 | 25 | 3,528 | 7,685 / 7,334 | EN87: 2,311 / x2 220 (12 ch) | SPARSE ECONOMIC SCREEN | 6,911 |
| `EN114:dyn:matched_0014` | hold=6, scope=BASE_AND_RUNNER | 4,129 | 4,311 | 25 | -892 | 4,279 / 3,110 | EN87: -1,530 / x2 -3,552 (19 ch) | SPARSE ECONOMIC SCREEN | 5,599 |
| `EN114:dyn:matched_0015` | hold=12, scope=BASE_ONLY | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN114:dyn:matched_0016` | hold=7, scope=BASE_AND_RUNNER | 9,198 | 9,425 | 25 | 3,670 | 8,202 / 8,377 | EN87: 3,584 / x2 908 (18 ch) | SPARSE ECONOMIC SCREEN | 6,818 |
| `EN114:dyn:matched_0017` | hold=12, scope=BASE_ONLY | 7,961 | 7,766 | 25 | 3,495 | 8,185 / 7,357 | EN87: 1,925 / x2 -309 (12 ch) | SPARSE ECONOMIC SCREEN | 5,502 |
| `EN114:dyn:matched_0018` | hold=7, scope=BASE_AND_RUNNER | 9,198 | 9,425 | 25 | 3,670 | 8,202 / 8,377 | EN87: 3,584 / x2 908 (18 ch) | SPARSE ECONOMIC SCREEN | 6,818 |

## EN115 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN115:0001` | window=20, ridge=1, residual_penalty=0 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:0002` | window=20, ridge=1, residual_penalty=1 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:0003` | window=20, ridge=10, residual_penalty=0 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:0004` | window=20, ridge=10, residual_penalty=1 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:0005` | window=40, ridge=1, residual_penalty=0 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:0006` | window=40, ridge=1, residual_penalty=1 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:0007` | window=40, ridge=10, residual_penalty=0 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:0008` | window=40, ridge=10, residual_penalty=1 | 8,831 | 7,429 | 25 | 4,202 | 9,032 / 7,686 | EN87_ONE_LOT: 4,367 / x2 1,769 (21 ch) | SCREENED | 6,668 |
| `EN115:0009` | window=60, ridge=1, residual_penalty=0 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:0010` | window=60, ridge=1, residual_penalty=1 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:0011` | window=60, ridge=10, residual_penalty=0 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:0012` | window=60, ridge=10, residual_penalty=1 | 8,831 | 7,429 | 25 | 4,202 | 9,032 / 7,686 | EN87_ONE_LOT: 4,367 / x2 1,769 (21 ch) | SCREENED | 6,668 |
| `EN115:ctl:constbeta_w20_r10_p0` | beta = candidates' median | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |
| `EN115:ctl:constbeta_w20_r10_p1` | beta = candidates' median | 9,764 | 8,528 | 26 | 5,136 | 9,965 / 8,785 | EN87_ONE_LOT: 5,466 / x2 2,868 (21 ch) | SCREENED | 7,442 |
| `EN115:ctl:constbeta_w20_r1_p0` | beta = candidates' median | 10,251 | 8,920 | 25 | 5,623 | 10,452 / 9,176 | EN87_ONE_LOT: 5,857 / x2 3,259 (20 ch) | SCREENED | 7,837 |
| `EN115:ctl:constbeta_w20_r1_p1` | beta = candidates' median | 10,042 | 8,514 | 26 | 5,414 | 10,244 / 8,771 | EN87_ONE_LOT: 5,452 / x2 2,854 (23 ch) | SCREENED | 7,509 |
| `EN115:ctl:constbeta_w40_r10_p0` | beta = candidates' median | 10,251 | 8,920 | 25 | 5,623 | 10,452 / 9,176 | EN87_ONE_LOT: 5,857 / x2 3,259 (20 ch) | SCREENED | 7,837 |
| `EN115:ctl:constbeta_w40_r10_p1` | beta = candidates' median | 10,145 | 8,896 | 26 | 5,516 | 10,346 / 9,153 | EN87_ONE_LOT: 5,833 / x2 3,235 (21 ch) | SCREENED | 7,820 |
| `EN115:ctl:constbeta_w40_r1_p0` | beta = candidates' median | 10,251 | 8,920 | 25 | 5,623 | 10,452 / 9,176 | EN87_ONE_LOT: 5,857 / x2 3,259 (20 ch) | SCREENED | 7,837 |
| `EN115:ctl:constbeta_w40_r1_p1` | beta = candidates' median | 10,122 | 8,874 | 26 | 5,494 | 10,324 / 9,131 | EN87_ONE_LOT: 5,811 / x2 3,213 (21 ch) | SCREENED | 7,801 |
| `EN115:ctl:constbeta_w60_r10_p0` | beta = candidates' median | 10,251 | 8,920 | 25 | 5,623 | 10,452 / 9,176 | EN87_ONE_LOT: 5,857 / x2 3,259 (20 ch) | SCREENED | 7,837 |
| `EN115:ctl:constbeta_w60_r10_p1` | beta = candidates' median | 8,736 | 7,453 | 24 | 4,108 | 8,938 / 7,710 | EN87_ONE_LOT: 4,390 / x2 1,792 (21 ch) | SCREENED | 5,010 |
| `EN115:ctl:constbeta_w60_r1_p0` | beta = candidates' median | 10,251 | 8,920 | 25 | 5,623 | 10,452 / 9,176 | EN87_ONE_LOT: 5,857 / x2 3,259 (20 ch) | SCREENED | 7,837 |
| `EN115:ctl:constbeta_w60_r1_p1` | beta = candidates' median | 8,787 | 7,493 | 23 | 4,159 | 8,988 / 7,749 | EN87_ONE_LOT: 4,430 / x2 1,832 (20 ch) | SCREENED | 5,063 |
| `EN115:ctl:equal_reserve_w40_r10` | legacy chooser given the response pick's reserve (<= 3 lots) | 5,511 | 4,196 | 25 | 2,347 | 5,497 / 4,164 | EN87: -1,645 / x2 -2,365 (12 ch) | SPARSE ECONOMIC SCREEN | 6,061 |
| `EN115:ctl:min_friction_one_lot` | EN100 min-friction one lot | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87_ONE_LOT: 4,852 / x2 2,254 (20 ch) | SCREENED | 7,157 |

## EN116 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN116:0001` | states=2, refit=1, persistence=IMMEDIATE | 8,549 | 7,316 | 25 | 3,299 | 8,358 / 7,184 | EN87: 1,476 / x2 -1,596 (22 ch) | SCREENED | 5,396 |
| `EN116:0002` | states=2, refit=1, persistence=TWO_BAR_HYSTERESIS | 6,574 | 5,360 | 25 | 3,074 | 6,383 / 5,228 | EN87: -480 / x2 -2,281 (22 ch) | SCREENED | 5,669 |
| `EN116:0003` | states=2, refit=5, persistence=IMMEDIATE | 8,549 | 7,316 | 25 | 3,299 | 8,358 / 7,184 | EN87: 1,476 / x2 -1,596 (22 ch) | SCREENED | 5,396 |
| `EN116:0004` | states=2, refit=5, persistence=TWO_BAR_HYSTERESIS | 6,574 | 5,360 | 25 | 3,074 | 6,383 / 5,228 | EN87: -480 / x2 -2,281 (22 ch) | SCREENED | 5,669 |
| `EN116:0005` | states=3, refit=1, persistence=IMMEDIATE | 8,407 | 7,222 | 25 | 2,863 | 6,912 / 5,802 | EN87: 1,382 / x2 -1,690 (22 ch) | SCREENED | 4,527 |
| `EN116:0006` | states=3, refit=1, persistence=TWO_BAR_HYSTERESIS | 6,483 | 5,266 | 25 | 2,519 | 4,988 / 3,846 | EN87: -574 / x2 -2,375 (22 ch) | SCREENED | 4,527 |
| `EN116:0007` | states=3, refit=5, persistence=IMMEDIATE | 8,407 | 7,222 | 25 | 2,863 | 6,912 / 5,802 | EN87: 1,382 / x2 -1,690 (22 ch) | SCREENED | 4,527 |
| `EN116:0008` | states=3, refit=5, persistence=TWO_BAR_HYSTERESIS | 6,483 | 5,266 | 25 | 2,519 | 4,988 / 3,846 | EN87: -574 / x2 -2,375 (22 ch) | SCREENED | 4,527 |
| `EN116:ctl:er_K2_R1_immediate` | ER10 state matched to the training activation rate | 8,241 | 6,859 | 25 | 2,991 | 8,050 / 6,274 | EN87: 1,018 / x2 -2,053 (22 ch) | SCREENED | 5,782 |
| `EN116:ctl:er_K2_R1_two_bar_hysteresis` | ER10 state matched to the training activation rate | 7,745 | 6,369 | 25 | 2,494 | 7,667 / 6,031 | EN87: 529 / x2 -2,543 (22 ch) | SCREENED | 5,782 |
| `EN116:ctl:er_K2_R5_immediate` | ER10 state matched to the training activation rate | 8,241 | 6,859 | 25 | 2,991 | 8,050 / 6,274 | EN87: 1,018 / x2 -2,053 (22 ch) | SCREENED | 5,782 |
| `EN116:ctl:er_K2_R5_two_bar_hysteresis` | ER10 state matched to the training activation rate | 7,745 | 6,369 | 25 | 2,494 | 7,667 / 6,031 | EN87: 529 / x2 -2,543 (22 ch) | SCREENED | 5,782 |
| `EN116:ctl:er_K3_R1_immediate` | ER10 state matched to the training activation rate | 8,248 | 7,063 | 25 | 2,704 | 6,753 / 5,643 | EN87: 1,223 / x2 -1,849 (22 ch) | SCREENED | 4,255 |
| `EN116:ctl:er_K3_R1_two_bar_hysteresis` | ER10 state matched to the training activation rate | 8,458 | 7,063 | 25 | 2,915 | 6,963 / 5,643 | EN87: 1,223 / x2 -1,849 (22 ch) | SCREENED | 4,255 |
| `EN116:ctl:er_K3_R5_immediate` | ER10 state matched to the training activation rate | 6,986 | 5,818 | 25 | 1,735 | 6,795 / 5,685 | EN87: -23 / x2 -3,094 (22 ch) | SCREENED | 4,255 |
| `EN116:ctl:er_K3_R5_two_bar_hysteresis` | ER10 state matched to the training activation rate | 7,197 | 5,818 | 25 | 1,946 | 7,006 / 5,685 | EN87: -23 / x2 -3,094 (22 ch) | SCREENED | 4,255 |
| `EN116:ctl:rnd_K2_R1_immediate` | seeded random state mapping | 7,114 | 7,458 | 25 | 3,644 | 5,304 / 6,516 | EN87: 1,618 / x2 220 (11 ch) | SPARSE ECONOMIC SCREEN | 4,624 |
| `EN116:ctl:rnd_K2_R1_two_bar_hysteresis` | seeded random state mapping | 7,114 | 7,458 | 25 | 3,644 | 5,304 / 6,516 | EN87: 1,618 / x2 220 (11 ch) | SPARSE ECONOMIC SCREEN | 4,897 |
| `EN116:ctl:rnd_K2_R5_immediate` | seeded random state mapping | 8,793 | 7,135 | 25 | 3,572 | 7,774 / 6,243 | EN87: 1,294 / x2 -1,777 (13 ch) | SPARSE ECONOMIC SCREEN | 4,934 |
| `EN116:ctl:rnd_K2_R5_two_bar_hysteresis` | seeded random state mapping | 6,818 | 5,179 | 25 | 3,348 | 5,799 / 4,287 | EN87: -662 / x2 -2,033 (13 ch) | SPARSE ECONOMIC SCREEN | 5,206 |
| `EN116:ctl:rnd_K3_R1_immediate` | seeded random state mapping | 8,309 | 7,059 | 25 | 3,059 | 7,229 / 5,943 | EN87: 1,219 / x2 -1,797 (18 ch) | SPARSE ECONOMIC SCREEN | 5,285 |
| `EN116:ctl:rnd_K3_R1_two_bar_hysteresis` | seeded random state mapping | 6,293 | 5,049 | 25 | 2,794 | 5,212 / 3,933 | EN87: -791 / x2 -2,133 (17 ch) | SPARSE ECONOMIC SCREEN | 5,875 |
| `EN116:ctl:rnd_K3_R5_immediate` | seeded random state mapping | 7,304 | 5,361 | 25 | 1,761 | 5,809 / 3,940 | EN87: -480 / x2 -3,552 (13 ch) | SPARSE ECONOMIC SCREEN | 4,582 |
| `EN116:ctl:rnd_K3_R5_two_bar_hysteresis` | seeded random state mapping | 5,087 | 3,143 | 25 | 1,720 | 3,793 / 1,930 | EN87: -2,697 / x2 -3,896 (11 ch) | SPARSE ECONOMIC SCREEN | 4,573 |

## EN117 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN117:0001` | excursion=0, target=MIDPOINT, stop_buffer=0.25, cost_coverage=1 | -5,151 | -13,414 | 212 | -8,168 | -4,074 / -4,043 H | CASH: -13,414 / x2 — (212 ch) | SCREENED | -13,295 |
| `EN117:0002` | excursion=0, target=MIDPOINT, stop_buffer=0.25, cost_coverage=2 | -4,737 | -9,952 | 138 | -7,754 | -3,324 / -3,465 | CASH: -9,952 / x2 — (138 ch) | SCREENED | -10,598 |
| `EN117:0003` | excursion=0, target=MIDPOINT, stop_buffer=0.5, cost_coverage=1 | -5,332 | -13,270 | 212 | -8,349 | -4,156 / -4,039 H | CASH: -13,270 / x2 — (212 ch) | SCREENED | -11,943 |
| `EN117:0004` | excursion=0, target=MIDPOINT, stop_buffer=0.5, cost_coverage=2 | -4,572 | -9,462 | 138 | -7,589 | -3,375 / -3,491 | CASH: -9,462 / x2 — (138 ch) | SCREENED | -8,759 |
| `EN117:0005` | excursion=0, target=OPPOSITE_QUARTILE, stop_buffer=0.25, cost_coverage=1 | -11,177 | -22,761 | 278 | -14,576 | -3,692 / -3,956 H | CASH: -22,761 / x2 — (278 ch) | SCREENED | -20,392 |
| `EN117:0006` | excursion=0, target=OPPOSITE_QUARTILE, stop_buffer=0.25, cost_coverage=2 | -7,123 | -17,193 | 229 | -10,522 | -3,549 / -3,959 H | CASH: -17,193 / x2 — (229 ch) | SCREENED | -14,646 |
| `EN117:0007` | excursion=0, target=OPPOSITE_QUARTILE, stop_buffer=0.5, cost_coverage=1 | -10,785 | -21,904 | 276 | -14,183 | -3,476 / -3,855 H | CASH: -21,904 / x2 — (276 ch) | SCREENED | -19,235 |
| `EN117:0008` | excursion=0, target=OPPOSITE_QUARTILE, stop_buffer=0.5, cost_coverage=2 | -6,740 | -16,280 | 229 | -10,139 | -3,395 / -3,891 H | CASH: -16,280 / x2 — (229 ch) | SCREENED | -13,099 |
| `EN117:0009` | excursion=0.25, target=MIDPOINT, stop_buffer=0.25, cost_coverage=1 | -2,799 | -10,292 | 177 | -5,816 | -4,000 / -4,084 H | CASH: -10,292 / x2 — (177 ch) | SCREENED | -6,267 |
| `EN117:0010` | excursion=0.25, target=MIDPOINT, stop_buffer=0.25, cost_coverage=2 | -1,374 | -6,328 | 113 | -4,391 | -2,596 / -3,079 | CASH: -6,328 / x2 — (113 ch) | SCREENED | -4,408 |
| `EN117:0011` | excursion=0.25, target=MIDPOINT, stop_buffer=0.5, cost_coverage=1 | -136 | -7,268 | 177 | -3,153 | -3,600 / -4,087 H | CASH: -7,268 / x2 — (177 ch) | SCREENED | -3,634 |
| `EN117:0012` | excursion=0.25, target=MIDPOINT, stop_buffer=0.5, cost_coverage=2 | -488 | -5,056 | 113 | -3,505 | -2,785 / -3,175 | CASH: -5,056 / x2 — (113 ch) | SCREENED | -2,969 |
| `EN117:0013` | excursion=0.25, target=OPPOSITE_QUARTILE, stop_buffer=0.25, cost_coverage=1 | -7,169 | -16,572 | 235 | -10,186 | -4,094 / -4,131 H | CASH: -16,572 / x2 — (235 ch) | SCREENED | -11,565 |
| `EN117:0014` | excursion=0.25, target=OPPOSITE_QUARTILE, stop_buffer=0.25, cost_coverage=2 | -4,189 | -12,329 | 193 | -7,206 | -4,103 / -4,206 H | CASH: -12,329 / x2 — (193 ch) | SCREENED | -8,549 |
| `EN117:0015` | excursion=0.25, target=OPPOSITE_QUARTILE, stop_buffer=0.5, cost_coverage=1 | -4,786 | -13,721 | 232 | -7,803 | -3,379 / -4,064 H | CASH: -13,721 / x2 — (232 ch) | SCREENED | -9,431 |
| `EN117:0016` | excursion=0.25, target=OPPOSITE_QUARTILE, stop_buffer=0.5, cost_coverage=2 | -2,030 | -9,763 | 192 | -5,047 | -3,653 / -4,201 H | CASH: -9,763 / x2 — (192 ch) | SCREENED | -6,234 |
| `EN117:ctl:gate_off_b0.0_midpoint_s0.25` | cost gate off | -13,401 | -26,744 | 337 | -16,457 | -4,087 / -4,057 H | CASH: -26,744 / x2 — (337 ch) | SCREENED | -24,827 |
| `EN117:ctl:gate_off_b0.0_midpoint_s0.5` | cost gate off | -13,040 | -25,891 | 334 | -16,096 | -4,032 / -4,107 H | CASH: -25,891 / x2 — (334 ch) | SCREENED | -23,539 |
| `EN117:ctl:gate_off_b0.0_opposite_quartile_s0.25` | cost gate off | -13,783 | -27,019 | 329 | -17,181 | -3,868 / -4,105 H | CASH: -27,020 / x2 — (329 ch) | SCREENED | -25,365 |
| `EN117:ctl:gate_off_b0.0_opposite_quartile_s0.5` | cost gate off | -13,312 | -26,052 | 326 | -16,711 | -3,837 / -4,005 H | CASH: -26,052 / x2 — (326 ch) | SCREENED | -24,203 |
| `EN117:ctl:gate_off_b0.25_midpoint_s0.25` | cost gate off | -9,848 | -21,160 | 287 | -12,865 | -4,119 / -4,078 H | CASH: -21,160 / x2 — (287 ch) | SCREENED | -15,473 |
| `EN117:ctl:gate_off_b0.25_midpoint_s0.5` | cost gate off | -6,826 | -17,667 | 284 | -9,843 | -3,743 / -4,046 H | CASH: -17,667 / x2 — (284 ch) | SCREENED | -12,883 |
| `EN117:ctl:gate_off_b0.25_opposite_quartile_s0.25` | cost gate off | -10,217 | -21,371 | 287 | -13,234 | -4,017 / -4,125 H | CASH: -21,371 / x2 — (287 ch) | SCREENED | -16,793 |
| `EN117:ctl:gate_off_b0.25_opposite_quartile_s0.5` | cost gate off | -7,774 | -18,417 | 283 | -10,791 | -3,664 / -4,046 H | CASH: -18,417 / x2 — (283 ch) | SCREENED | -14,878 |
| `EN117:ctl:opposite_dir_b0.0` | same clocks, opposite direction, native exits, gate off | -30,226 | -40,878 | 314 | -34,058 | -1,243 / -1,634 H | CASH: -40,878 / x2 — (314 ch) | SCREENED | -34,367 |
| `EN117:ctl:opposite_dir_b0.25` | same clocks, opposite direction, native exits, gate off | -30,490 | -40,234 | 274 | -34,987 | -790 / -1,095 H | CASH: -40,234 / x2 — (274 ch) | SCREENED | -24,078 |
| `EN117:ctl:random_dir_b0.0` | same clocks, random direction, native exits, gate off | -19,882 | -31,523 | 313 | -32,496 | -2,291 / -2,430 H | CASH: -31,523 / x2 — (313 ch) | SCREENED | -28,588 |
| `EN117:ctl:random_dir_b0.25` | same clocks, random direction, native exits, gate off | -28,635 | -38,265 | 272 | -32,230 | -1,813 / -2,303 H | CASH: -38,265 / x2 — (272 ch) | SCREENED | -22,922 |

## EN117 — SENSEX

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN117:0001` | excursion=0, target=MIDPOINT, stop_buffer=0.25, cost_coverage=1 | -2,053 | -3,802 | 37 | -3,256 | -2,248 / -3,337 | CASH: -3,802 / x2 — (37 ch) | SCREENED | — |
| `EN117:0002` | excursion=0, target=MIDPOINT, stop_buffer=0.25, cost_coverage=2 | -1,662 | -2,858 | 25 | -2,839 | -1,753 / -2,124 | CASH: -2,858 / x2 — (25 ch) | SCREENED | — |
| `EN117:0003` | excursion=0, target=MIDPOINT, stop_buffer=0.5, cost_coverage=1 | -2,168 | -3,917 | 37 | -3,371 | -3,067 / -3,482 | CASH: -3,917 / x2 — (37 ch) | SCREENED | — |
| `EN117:0004` | excursion=0, target=MIDPOINT, stop_buffer=0.5, cost_coverage=2 | -2,034 | -3,219 | 25 | -3,210 | -1,931 / -2,411 | CASH: -3,219 / x2 — (25 ch) | SCREENED | — |
| `EN117:0005` | excursion=0, target=OPPOSITE_QUARTILE, stop_buffer=0.25, cost_coverage=1 | -3,686 | -5,997 | 51 | -5,839 | -3,257 / -3,459 | CASH: -5,997 / x2 — (51 ch) | SCREENED | — |
| `EN117:0006` | excursion=0, target=OPPOSITE_QUARTILE, stop_buffer=0.25, cost_coverage=2 | -3,010 | -4,866 | 41 | -4,993 | -2,224 / -3,293 | CASH: -4,866 / x2 — (41 ch) | SCREENED | — |
| `EN117:0007` | excursion=0, target=OPPOSITE_QUARTILE, stop_buffer=0.5, cost_coverage=1 | -3,919 | -6,222 | 51 | -5,769 | -3,516 / -3,711 | CASH: -6,222 / x2 — (51 ch) | SCREENED | — |
| `EN117:0008` | excursion=0, target=OPPOSITE_QUARTILE, stop_buffer=0.5, cost_coverage=2 | -3,243 | -5,091 | 41 | -4,923 | -3,029 / -3,444 | CASH: -5,091 / x2 — (41 ch) | SCREENED | — |
| `EN117:0009` | excursion=0.25, target=MIDPOINT, stop_buffer=0.25, cost_coverage=1 | -1,781 | -2,832 | 25 | -2,545 | -1,829 / -1,894 | CASH: -2,832 / x2 — (25 ch) | SCREENED | — |
| `EN117:0010` | excursion=0.25, target=MIDPOINT, stop_buffer=0.25, cost_coverage=2 | -748 | -1,425 | 17 | -1,418 | -748 / -1,398 | CASH: -1,425 / x2 — (17 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN117:0011` | excursion=0.25, target=MIDPOINT, stop_buffer=0.5, cost_coverage=1 | -1,918 | -2,975 | 25 | -2,604 | -2,284 / -2,843 | CASH: -2,975 / x2 — (25 ch) | SCREENED | — |
| `EN117:0012` | excursion=0.25, target=MIDPOINT, stop_buffer=0.5, cost_coverage=2 | -1,141 | -1,814 | 17 | -1,582 | -1,141 / -1,786 | CASH: -1,814 / x2 — (17 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN117:0013` | excursion=0.25, target=OPPOSITE_QUARTILE, stop_buffer=0.25, cost_coverage=1 | -1,575 | -3,329 | 40 | -3,708 | -2,178 / -2,548 | CASH: -3,329 / x2 — (40 ch) | SCREENED | — |
| `EN117:0014` | excursion=0.25, target=OPPOSITE_QUARTILE, stop_buffer=0.25, cost_coverage=2 | -1,327 | -2,841 | 35 | -3,460 | -2,274 / -3,034 | CASH: -2,841 / x2 — (35 ch) | SCREENED | — |
| `EN117:0015` | excursion=0.25, target=OPPOSITE_QUARTILE, stop_buffer=0.5, cost_coverage=1 | -2,116 | -3,871 | 40 | -3,944 | -2,357 / -3,838 | CASH: -3,871 / x2 — (40 ch) | SCREENED | — |
| `EN117:0016` | excursion=0.25, target=OPPOSITE_QUARTILE, stop_buffer=0.5, cost_coverage=2 | -1,868 | -3,383 | 35 | -3,697 | -3,219 / -3,773 | CASH: -3,383 / x2 — (35 ch) | SCREENED | — |
| `EN117:ctl:gate_off_b0.0_midpoint_s0.25` | cost gate off | -5,691 | -8,555 | 65 | -7,460 | -4,095 / -4,053 H | CASH: -8,555 / x2 — (65 ch) | SCREENED | — |
| `EN117:ctl:gate_off_b0.0_midpoint_s0.5` | cost gate off | -4,920 | -7,800 | 65 | -6,688 | -3,925 / -4,047 H | CASH: -7,800 / x2 — (65 ch) | SCREENED | — |
| `EN117:ctl:gate_off_b0.0_opposite_quartile_s0.25` | cost gate off | -6,377 | -9,226 | 65 | -8,531 | -3,891 / -4,099 H | CASH: -9,226 / x2 — (65 ch) | SCREENED | — |
| `EN117:ctl:gate_off_b0.0_opposite_quartile_s0.5` | cost gate off | -5,717 | -8,574 | 65 | -7,566 | -3,960 / -4,093 H | CASH: -8,574 / x2 — (65 ch) | SCREENED | — |
| `EN117:ctl:gate_off_b0.25_midpoint_s0.25` | cost gate off | -4,105 | -6,280 | 51 | -5,471 | -4,119 / -4,023 H | CASH: -6,280 / x2 — (51 ch) | SCREENED | — |
| `EN117:ctl:gate_off_b0.25_midpoint_s0.5` | cost gate off | -3,752 | -5,946 | 51 | -5,119 | -4,015 / -4,055 H | CASH: -5,946 / x2 — (51 ch) | SCREENED | — |
| `EN117:ctl:gate_off_b0.25_opposite_quartile_s0.25` | cost gate off | -3,664 | -5,829 | 51 | -5,798 | -3,351 / -3,772 | CASH: -5,829 / x2 — (51 ch) | SCREENED | — |
| `EN117:ctl:gate_off_b0.25_opposite_quartile_s0.5` | cost gate off | -3,312 | -5,495 | 51 | -5,141 | -3,436 / -4,017 H | CASH: -5,495 / x2 — (51 ch) | SCREENED | — |
| `EN117:ctl:opposite_dir_b0.0` | same clocks, opposite direction, native exits, gate off | 2,854 | 1,605 | 65 | -2,622 | 1,020 / -584 | CASH: 1,605 / x2 — (65 ch) | SCREENED | — |
| `EN117:ctl:opposite_dir_b0.25` | same clocks, opposite direction, native exits, gate off | 1,712 | 250 | 51 | -2,892 | 547 / -435 H | CASH: 250 / x2 — (51 ch) | SCREENED | — |
| `EN117:ctl:random_dir_b0.0` | same clocks, random direction, native exits, gate off | -452 | -2,523 | 64 | -5,913 | 339 / -1,187 H | CASH: -2,523 / x2 — (64 ch) | SCREENED | — |
| `EN117:ctl:random_dir_b0.25` | same clocks, random direction, native exits, gate off | -5,253 | -7,663 | 50 | -9,080 | -4,074 / -4,026 H | CASH: -7,664 / x2 — (50 ch) | SCREENED | — |

## EN118 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN118:0001` | learner=RIDGE, regularization=LIGHT, k=0 | 3,032 | 1,610 | 18 | 537 | 3,032 / 1,610 | EN87: -2,160 / x2 -3,417 (18 ch) | SPARSE ECONOMIC SCREEN | 7,450 |
| `EN118:0001:no_oi` | learner=RIDGE, regularization=LIGHT, k=0, features=NO_OI | 4,037 | 2,978 | 10 | 1,215 | 4,008 / 3,274 | EN87: -791 / x2 -2,329 (12 ch) | SPARSE ECONOMIC SCREEN | 7,352 |
| `EN118:0002` | learner=RIDGE, regularization=LIGHT, k=1 | 1,979 | 1,203 | 6 | -129 | 1,979 / 1,203 | EN87: -2,566 / x2 -4,488 (14 ch) | SPARSE ECONOMIC SCREEN | 5,682 |
| `EN118:0002:no_oi` | learner=RIDGE, regularization=LIGHT, k=1, features=NO_OI | 2,183 | 1,495 | 4 | 74 | 2,183 / 1,495 | EN87: -2,275 / x2 -4,197 (12 ch) | SPARSE ECONOMIC SCREEN | 5,723 |
| `EN118:0003` | learner=RIDGE, regularization=LIGHT, k=2 | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |
| `EN118:0003:no_oi` | learner=RIDGE, regularization=LIGHT, k=2, features=NO_OI | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |
| `EN118:0004` | learner=RIDGE, regularization=HEAVY, k=0 | 3,967 | 2,603 | 17 | 1,472 | 3,967 / 2,603 | EN87: -1,166 / x2 -2,873 (19 ch) | SPARSE ECONOMIC SCREEN | 8,353 |
| `EN118:0004:no_oi` | learner=RIDGE, regularization=HEAVY, k=0, features=NO_OI | 4,037 | 2,978 | 10 | 1,215 | 4,008 / 3,274 | EN87: -791 / x2 -2,329 (12 ch) | SPARSE ECONOMIC SCREEN | 7,352 |
| `EN118:0005` | learner=RIDGE, regularization=HEAVY, k=1 | 410 | -288 | 5 | -301 | 410 / -288 | EN87: -4,058 / x2 -5,980 (15 ch) | SPARSE ECONOMIC SCREEN | 4,164 |
| `EN118:0005:no_oi` | learner=RIDGE, regularization=HEAVY, k=1, features=NO_OI | 613 | 3 | 3 | -3 | 613 / 3 | EN87: -3,767 / x2 -5,689 (13 ch) | SPARSE ECONOMIC SCREEN | 4,205 |
| `EN118:0006` | learner=RIDGE, regularization=HEAVY, k=2 | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |
| `EN118:0006:no_oi` | learner=RIDGE, regularization=HEAVY, k=2, features=NO_OI | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |
| `EN118:0007` | learner=STUMP, regularization=LIGHT, k=0 | 4,224 | 3,729 | 32 | 777 | 2,890 / 3,729 | EN87: -41 / x2 -1,735 (34 ch) | SCREENED | 4,881 |
| `EN118:0007:no_oi` | learner=STUMP, regularization=LIGHT, k=0, features=NO_OI | 3,992 | 3,532 | 31 | 545 | 2,658 / 3,532 | EN87: -238 / x2 -1,932 (34 ch) | SCREENED | 4,881 |
| `EN118:0008` | learner=STUMP, regularization=LIGHT, k=1 | 233 | 168 | 1 | 0 | 233 / 168 | EN87: -3,601 / x2 -5,511 (15 ch) | SPARSE ECONOMIC SCREEN | -584 |
| `EN118:0008:no_oi` | learner=STUMP, regularization=LIGHT, k=1, features=NO_OI | -442 | -565 | 2 | -675 | -442 / -565 | EN87: -4,335 / x2 -6,244 (16 ch) | SPARSE ECONOMIC SCREEN | -584 |
| `EN118:0009` | learner=STUMP, regularization=LIGHT, k=2 | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |
| `EN118:0009:no_oi` | learner=STUMP, regularization=LIGHT, k=2, features=NO_OI | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |
| `EN118:0010` | learner=STUMP, regularization=HEAVY, k=0 | 908 | 964 | 6 | -316 | 908 / 964 | EN87: -2,805 / x2 -4,715 (20 ch) | SCREENED | 7 |
| `EN118:0010:no_oi` | learner=STUMP, regularization=HEAVY, k=0, features=NO_OI | 908 | 964 | 6 | -316 | 908 / 964 | EN87: -2,805 / x2 -4,715 (20 ch) | SCREENED | 7 |
| `EN118:0011` | learner=STUMP, regularization=HEAVY, k=1 | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |
| `EN118:0011:no_oi` | learner=STUMP, regularization=HEAVY, k=1, features=NO_OI | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |
| `EN118:0012` | learner=STUMP, regularization=HEAVY, k=2 | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |
| `EN118:0012:no_oi` | learner=STUMP, regularization=HEAVY, k=2, features=NO_OI | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |
| `EN118:ctl:direction_only` | ridge direction forecast acting LEGACY_100_8 | 1,032 | 1,414 | 14 | -1,585 | 1,263 / 1,710 | EN87: -2,355 / x2 -2,893 (4 ch) | ACTIVATION-LIMITED | 3,183 |
| `EN118:ctl:fixed_nearer_100_8_at_e03` | fixed action at every E03 event | 5,969 | 3,256 | 57 | 809 | -3,381 / -3,553 | EN87: -2,585 / x2 -4,900 (56 ch) | SCREENED | 5,311 |
| `EN118:ctl:fixed_nearer_150_12_at_e03` | fixed action at every E03 event | 8,072 | 4,742 | 57 | 627 | -4,108 / -4,116 H | EN87: -1,099 / x2 -5,545 (56 ch) | SCREENED | 3,841 |
| `EN118:ctl:mean_actions` | unconditional action means | 0 | 0 | 0 | 0 | 0 / 0 | EN87: -3,769 / x2 -5,679 (14 ch) | SPARSE ECONOMIC SCREEN | 0 |

## EN118 — SENSEX

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN118:ctl:fixed_nearer_100_8_at_e03` | fixed action at every E03 event | 1,939 | 1,558 | 7 | -1,480 | 1,606 / 1,253 | E03_env: -3,188 / x2 -3,339 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN118:ctl:fixed_nearer_150_12_at_e03` | fixed action at every E03 event | 948 | 817 | 7 | -1,992 | 715 / 574 | E03_env: -3,929 / x2 -4,633 (7 ch) | SPARSE ECONOMIC SCREEN | — |

## EN120 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN120:0001` | depth=1, refit=5, switch_margin=0 | 4,702 | 5,155 | 20 | 1,326 | 4,387 / 5,155 | EN87: 1,386 / x2 -33 (12 ch) | SPARSE ECONOMIC SCREEN | 4,421 |
| `EN120:0002` | depth=1, refit=5, switch_margin=0.1 | 4,702 | 5,155 | 20 | 1,326 | 4,387 / 5,155 | EN87: 1,386 / x2 -33 (12 ch) | SPARSE ECONOMIC SCREEN | 4,421 |
| `EN120:0003` | depth=1, refit=5, switch_margin=0.25 | 4,702 | 5,155 | 20 | 1,326 | 4,387 / 5,155 | EN87: 1,386 / x2 -33 (12 ch) | SPARSE ECONOMIC SCREEN | 4,421 |
| `EN120:0004` | depth=1, refit=20, switch_margin=0 | 5,536 | 5,646 | 26 | 2,161 | 4,928 / 5,646 | EN87: 1,876 / x2 293 (16 ch) | SPARSE ECONOMIC SCREEN | 5,370 |
| `EN120:0005` | depth=1, refit=20, switch_margin=0.1 | 5,536 | 5,646 | 26 | 2,161 | 4,928 / 5,646 | EN87: 1,876 / x2 293 (16 ch) | SPARSE ECONOMIC SCREEN | 5,370 |
| `EN120:0006` | depth=1, refit=20, switch_margin=0.25 | 5,536 | 5,646 | 26 | 2,161 | 4,928 / 5,646 | EN87: 1,876 / x2 293 (16 ch) | SPARSE ECONOMIC SCREEN | 5,370 |
| `EN120:0007` | depth=2, refit=5, switch_margin=0 | 5,215 | 5,769 | 18 | 1,840 | 4,762 / 5,769 | EN87: 2,000 / x2 581 (10 ch) | SPARSE ECONOMIC SCREEN | 4,641 |
| `EN120:0008` | depth=2, refit=5, switch_margin=0.1 | 5,215 | 5,769 | 18 | 1,840 | 4,762 / 5,769 | EN87: 2,000 / x2 581 (10 ch) | SPARSE ECONOMIC SCREEN | 4,641 |
| `EN120:0009` | depth=2, refit=5, switch_margin=0.25 | 5,215 | 5,769 | 18 | 1,840 | 4,762 / 5,769 | EN87: 2,000 / x2 581 (10 ch) | SPARSE ECONOMIC SCREEN | 4,641 |
| `EN120:0010` | depth=2, refit=20, switch_margin=0 | 5,732 | 5,945 | 24 | 2,357 | 5,171 / 5,945 | EN87: 2,176 / x2 592 (14 ch) | SPARSE ECONOMIC SCREEN | 5,244 |
| `EN120:0011` | depth=2, refit=20, switch_margin=0.1 | 5,732 | 5,945 | 24 | 2,357 | 5,171 / 5,945 | EN87: 2,176 / x2 592 (14 ch) | SPARSE ECONOMIC SCREEN | 5,244 |
| `EN120:0012` | depth=2, refit=20, switch_margin=0.25 | 5,732 | 5,945 | 24 | 2,357 | 5,171 / 5,945 | EN87: 2,176 / x2 592 (14 ch) | SPARSE ECONOMIC SCREEN | 5,244 |
| `EN120:ctl:fixed_priority_union` | EN87 minute -> EN111 profile; else range -> EN117 | 10,163 | 3,558 | 136 | 4,159 | 7,965 / -2,400 | EN87: -2,282 / x2 -6,214 (137 ch) | SCREENED | 3,021 |
| `EN120:ctl:past_pnl_chooser` | EN79-style: profile with the best prior cumulative adverse P | 9,959 | 7,818 | 25 | 3,955 | 6,639 / 5,438 | EN87: 1,977 / x2 -1,097 (23 ch) | SCREENED | 5,768 |

## EN121 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN121:0001` | book=E03_env, contract=LEGACY, target=1.0, hold=8 | 3,006 | 2,246 | 55 | -1,298 | -3,445 / -4,035 H | E03_env: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 4,795 |
| `EN121:0002` | book=E03_env, contract=LEGACY, target=1.0, hold=12 | 6,093 | 5,842 | 55 | 83 | 6,740 / 4,780 | E03_env: 3,596 / x2 291 (34 ch) | SCREENED | 4,255 |
| `EN121:0003` | book=E03_env, contract=LEGACY, target=1.5, hold=8 | 7,613 | 6,589 | 56 | 1,968 | -3,103 / -4,035 H | E03_env: 4,343 / x2 1,296 (5 ch) | SPARSE ECONOMIC SCREEN | 3,609 |
| `EN121:0004` | book=E03_env, contract=LEGACY, target=1.5, hold=12 | 5,600 | 4,957 | 56 | -1,010 | -4,002 / -4,081 H | E03_env: 2,711 / x2 -594 (39 ch) | SCREENED | 4,408 |
| `EN121:0005` | book=E03_env, contract=NEAREST_ONE_LOT, target=1.0, hold=8 | 5,969 | 3,256 | 57 | 809 | -3,381 / -3,553 | E03_env: 1,010 / x2 -759 (53 ch) | SCREENED | 5,311 |
| `EN121:0006` | book=E03_env, contract=NEAREST_ONE_LOT, target=1.0, hold=12 | 9,797 | 6,448 | 57 | 3,135 | 5,530 / -4,106 H | E03_env: 4,202 / x2 1,028 (55 ch) | SCREENED | 4,954 |
| `EN121:0007` | book=E03_env, contract=NEAREST_ONE_LOT, target=1.5, hold=8 | 5,599 | 2,892 | 57 | 634 | -2,931 / -3,265 | E03_env: 647 / x2 -1,175 (53 ch) | SCREENED | 4,747 |
| `EN121:0008` | book=E03_env, contract=NEAREST_ONE_LOT, target=1.5, hold=12 | 8,072 | 4,742 | 57 | 627 | -4,108 / -4,116 H | E03_env: 2,496 / x2 -1,454 (55 ch) | SCREENED | 3,841 |
| `EN121:0009` | book=E03_env, contract=NEAREST_SAME_ROOM, target=1.0, hold=8 | 6,407 | 3,242 | 57 | 1,247 | 8,044 / -3,559 | E03_env: 996 / x2 -772 (40 ch) | SCREENED | 8,143 |
| `EN121:0010` | book=E03_env, contract=NEAREST_SAME_ROOM, target=1.0, hold=12 | 10,579 | 6,863 | 57 | 3,916 | 6,206 / -4,050 H | E03_env: 4,617 / x2 1,442 (52 ch) | SCREENED | 7,794 |
| `EN121:0011` | book=E03_env, contract=NEAREST_SAME_ROOM, target=1.5, hold=8 | 6,037 | 2,879 | 57 | 1,072 | 7,645 / -3,272 | E03_env: 633 / x2 -1,188 (40 ch) | SCREENED | 4,958 |
| `EN121:0012` | book=E03_env, contract=NEAREST_SAME_ROOM, target=1.5, hold=12 | 8,853 | 5,157 | 57 | 1,409 | -4,024 / -4,136 H | E03_env: 2,911 / x2 -1,039 (52 ch) | SCREENED | 6,984 |
| `EN121:0013` | book=E032_native, contract=LEGACY, target=1.0, hold=8 | 14,275 | 11,586 | 66 | 652 | -4,123 / -4,036 H | E032_native: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 3,642 |
| `EN121:0014` | book=E032_native, contract=LEGACY, target=1.0, hold=12 | 15,462 | 13,149 | 66 | 635 | 14,931 / -4,065 H | E032_native: 1,563 / x2 -870 (34 ch) | SCREENED | 4,247 |
| `EN121:0015` | book=E032_native, contract=LEGACY, target=1.5, hold=8 | 19,003 | 16,078 | 67 | 3,262 | -4,123 / -4,036 H | E032_native: 4,491 / x2 1,759 (8 ch) | SPARSE ECONOMIC SCREEN | 1,061 |
| `EN121:0016` | book=E032_native, contract=LEGACY, target=1.5, hold=12 | 15,457 | 12,993 | 67 | -485 | 8,448 / -4,279 H | E032_native: 1,407 / x2 -1,026 (42 ch) | SCREENED | 4,203 |
| `EN121:0017` | book=E032_native, contract=NEAREST_ONE_LOT, target=1.0, hold=8 | 10,117 | 7,479 | 69 | 2,204 | 10,286 / 7,652 | E032_native: -4,107 / x2 -5,876 (33 ch) | SCREENED | 6,077 |
| `EN121:0018` | book=E032_native, contract=NEAREST_ONE_LOT, target=1.0, hold=12 | 10,970 | 7,645 | 69 | 2,240 | 10,970 / 6,948 H | E032_native: -3,941 / x2 -6,259 (51 ch) | SCREENED | 6,536 |
| `EN121:0019` | book=E032_native, contract=NEAREST_ONE_LOT, target=1.5, hold=8 | 11,632 | 8,985 | 69 | 3,162 | 11,802 / 9,158 | E032_native: -2,601 / x2 -4,370 (37 ch) | SCREENED | 2,630 |
| `EN121:0020` | book=E032_native, contract=NEAREST_ONE_LOT, target=1.5, hold=12 | 10,471 | 7,156 | 69 | 1,183 | 10,471 / 6,459 H | E032_native: -4,430 / x2 -6,748 (55 ch) | SCREENED | 5,001 |
| `EN121:0021` | book=E032_native, contract=NEAREST_SAME_ROOM, target=1.0, hold=8 | 17,069 | 14,194 | 68 | 3,236 | 11,317 / 8,951 | E032_native: 2,608 / x2 839 (19 ch) | SPARSE ECONOMIC SCREEN | 5,851 |
| `EN121:0022` | book=E032_native, contract=NEAREST_SAME_ROOM, target=1.0, hold=12 | 17,451 | 13,909 | 68 | 2,801 | 17,451 / 8,255 | E032_native: 2,323 / x2 5 (43 ch) | SCREENED | 6,320 |
| `EN121:0023` | book=E032_native, contract=NEAREST_SAME_ROOM, target=1.5, hold=8 | 19,142 | 16,252 | 68 | 4,193 | 19,312 / 10,457 | E032_native: 4,666 / x2 2,634 (24 ch) | SCREENED | 2,404 |
| `EN121:0024` | book=E032_native, contract=NEAREST_SAME_ROOM, target=1.5, hold=12 | 17,511 | 13,971 | 68 | 1,744 | 11,032 / -4,058 H | E032_native: 2,385 / x2 -17 (48 ch) | SCREENED | 5,342 |
| `EN121:0025` | book=EN55_native, contract=LEGACY, target=1.0, hold=8 | 13,165 | 11,056 | 68 | 1,045 | 3,445 / 11,573 | EN55_native: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | -2,480 |
| `EN121:0026` | book=EN55_native, contract=LEGACY, target=1.0, hold=12 | 15,325 | 13,930 | 68 | 2,002 | 15,069 / 13,736 | EN55_native: 2,874 / x2 441 (34 ch) | SCREENED | -187 |
| `EN121:0027` | book=EN55_native, contract=LEGACY, target=1.5, hold=8 | 13,584 | 11,473 | 68 | 1,464 | 13,677 / 11,989 | EN55_native: 416 / x2 -255 (5 ch) | SPARSE ECONOMIC SCREEN | -4,053 |
| `EN121:0028` | book=EN55_native, contract=LEGACY, target=1.5, hold=12 | 12,478 | 11,116 | 68 | -845 | 2,313 / -4,074 H | EN55_native: 59 / x2 -2,374 (39 ch) | SCREENED | -3,174 |
| `EN121:0029` | book=EN55_native, contract=NEAREST_ONE_LOT, target=1.0, hold=8 | 13,765 | 12,155 | 68 | 2,699 | 13,765 / 12,155 | EN55_native: 1,098 / x2 -786 (24 ch) | SCREENED | -222 |
| `EN121:0030` | book=EN55_native, contract=NEAREST_ONE_LOT, target=1.0, hold=12 | 14,210 | 12,953 | 68 | 2,280 | 14,210 / 12,953 | EN55_native: 1,896 / x2 -602 (44 ch) | SCREENED | -981 |
| `EN121:0031` | book=EN55_native, contract=NEAREST_ONE_LOT, target=1.5, hold=8 | 13,922 | 12,315 | 68 | 2,855 | 13,922 / 12,315 | EN55_native: 1,258 / x2 -626 (27 ch) | SCREENED | -1,490 |
| `EN121:0032` | book=EN55_native, contract=NEAREST_ONE_LOT, target=1.5, hold=12 | 12,352 | 11,118 | 68 | 422 | 12,352 / 11,118 | EN55_native: 61 / x2 -2,437 (47 ch) | SCREENED | -2,894 |
| `EN121:0033` | book=EN55_native, contract=NEAREST_SAME_ROOM, target=1.0, hold=8 | 15,767 | 13,627 | 68 | 3,417 | 15,767 / 13,627 | EN55_native: 2,570 / x2 686 (18 ch) | SPARSE ECONOMIC SCREEN | 408 |
| `EN121:0034` | book=EN55_native, contract=NEAREST_SAME_ROOM, target=1.0, hold=12 | 15,728 | 14,318 | 68 | 2,515 | 15,728 / 14,318 | EN55_native: 3,261 / x2 763 (42 ch) | SCREENED | 77 |
| `EN121:0035` | book=EN55_native, contract=NEAREST_SAME_ROOM, target=1.5, hold=8 | 15,924 | 13,787 | 68 | 3,574 | 15,924 / 13,787 | EN55_native: 2,730 / x2 846 (21 ch) | SCREENED | -859 |
| `EN121:0036` | book=EN55_native, contract=NEAREST_SAME_ROOM, target=1.5, hold=12 | 13,871 | 12,483 | 68 | 657 | 13,871 / 3,617 | EN55_native: 1,426 / x2 -1,072 (45 ch) | SCREENED | -1,835 |

## EN121 — SENSEX

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN121:0001` | book=E03_env, contract=LEGACY, target=1.0, hold=8 | 5,167 | 4,746 | 7 | -1,372 | 4,501 / 4,114 | E03_env: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | — |
| `EN121:0002` | book=E03_env, contract=LEGACY, target=1.0, hold=12 | 3,537 | 3,411 | 7 | -2,135 | 3,342 / 3,132 | E03_env: -1,335 / x2 -1,888 (4 ch) | ACTIVATION-LIMITED | — |
| `EN121:0003` | book=E03_env, contract=LEGACY, target=1.5, hold=8 | 5,167 | 4,746 | 7 | -1,372 | 4,501 / 4,114 | E03_env: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | — |
| `EN121:0004` | book=E03_env, contract=LEGACY, target=1.5, hold=12 | 3,537 | 3,411 | 7 | -2,135 | 3,342 / 3,132 | E03_env: -1,335 / x2 -1,888 (4 ch) | ACTIVATION-LIMITED | — |
| `EN121:0005` | book=E03_env, contract=NEAREST_ONE_LOT, target=1.0, hold=8 | 1,939 | 1,558 | 7 | -1,480 | 1,606 / 1,253 | E03_env: -3,188 / x2 -3,339 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0006` | book=E03_env, contract=NEAREST_ONE_LOT, target=1.0, hold=12 | 948 | 817 | 7 | -1,992 | 715 / 574 | E03_env: -3,929 / x2 -4,633 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0007` | book=E03_env, contract=NEAREST_ONE_LOT, target=1.5, hold=8 | 1,939 | 1,558 | 7 | -1,480 | 1,606 / 1,253 | E03_env: -3,188 / x2 -3,339 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0008` | book=E03_env, contract=NEAREST_ONE_LOT, target=1.5, hold=12 | 948 | 817 | 7 | -1,992 | 715 / 574 | E03_env: -3,929 / x2 -4,633 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0009` | book=E03_env, contract=NEAREST_SAME_ROOM, target=1.0, hold=8 | 2,317 | 1,905 | 7 | -1,102 | 1,984 / 1,599 | E03_env: -2,841 / x2 -3,120 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0010` | book=E03_env, contract=NEAREST_SAME_ROOM, target=1.0, hold=12 | 1,003 | 844 | 7 | -1,936 | 770 / 601 | E03_env: -3,902 / x2 -4,605 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0011` | book=E03_env, contract=NEAREST_SAME_ROOM, target=1.5, hold=8 | 2,317 | 1,905 | 7 | -1,102 | 1,984 / 1,599 | E03_env: -2,841 / x2 -3,120 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0012` | book=E03_env, contract=NEAREST_SAME_ROOM, target=1.5, hold=12 | 1,003 | 844 | 7 | -1,936 | 770 / 601 | E03_env: -3,902 / x2 -4,605 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0013` | book=E032_native, contract=LEGACY, target=1.0, hold=8 | 2,449 | 1,921 | 12 | -4,089 | 1,987 / 1,516 | E032_native: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | — |
| `EN121:0014` | book=E032_native, contract=LEGACY, target=1.0, hold=12 | 319 | 90 | 12 | -5,120 | 560 / 243 | E032_native: -1,831 / x2 -2,107 (4 ch) | ACTIVATION-LIMITED | — |
| `EN121:0015` | book=E032_native, contract=LEGACY, target=1.5, hold=8 | 2,449 | 1,921 | 12 | -4,089 | 1,987 / 1,516 | E032_native: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | — |
| `EN121:0016` | book=E032_native, contract=LEGACY, target=1.5, hold=12 | 319 | 90 | 12 | -5,120 | 560 / 243 | E032_native: -1,831 / x2 -2,107 (4 ch) | ACTIVATION-LIMITED | — |
| `EN121:0017` | book=E032_native, contract=NEAREST_ONE_LOT, target=1.0, hold=8 | 322 | -105 | 11 | -3,097 | 322 / -411 | E032_native: -2,026 / x2 -3,064 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0018` | book=E032_native, contract=NEAREST_ONE_LOT, target=1.0, hold=12 | -1,269 | -1,442 | 11 | -3,922 | -1,320 / -1,560 | E032_native: -3,362 / x2 -4,401 (8 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0019` | book=E032_native, contract=NEAREST_ONE_LOT, target=1.5, hold=8 | 322 | -105 | 11 | -3,097 | 322 / -411 | E032_native: -2,026 / x2 -3,064 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0020` | book=E032_native, contract=NEAREST_ONE_LOT, target=1.5, hold=12 | -1,269 | -1,442 | 11 | -3,922 | -1,320 / -1,560 | E032_native: -3,362 / x2 -4,401 (8 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0021` | book=E032_native, contract=NEAREST_SAME_ROOM, target=1.0, hold=8 | -38 | -479 | 11 | -3,456 | -38 / -785 | E032_native: -2,400 / x2 -3,173 (6 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0022` | book=E032_native, contract=NEAREST_SAME_ROOM, target=1.0, hold=12 | -1,629 | -1,816 | 11 | -4,281 | -1,679 / -1,934 | E032_native: -3,736 / x2 -4,677 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0023` | book=E032_native, contract=NEAREST_SAME_ROOM, target=1.5, hold=8 | -38 | -479 | 11 | -3,456 | -38 / -785 | E032_native: -2,400 / x2 -3,173 (6 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0024` | book=E032_native, contract=NEAREST_SAME_ROOM, target=1.5, hold=12 | -1,629 | -1,816 | 11 | -4,281 | -1,679 / -1,934 | E032_native: -3,736 / x2 -4,677 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0025` | book=EN55_native, contract=LEGACY, target=1.0, hold=8 | 2,470 | 2,237 | 10 | -3,008 | 2,470 / 2,237 | EN55_native: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | — |
| `EN121:0026` | book=EN55_native, contract=LEGACY, target=1.0, hold=12 | 1,108 | 889 | 10 | -3,842 | 1,108 / 889 | EN55_native: -1,347 / x2 -1,347 (3 ch) | ACTIVATION-LIMITED | — |
| `EN121:0027` | book=EN55_native, contract=LEGACY, target=1.5, hold=8 | 2,470 | 2,237 | 10 | -3,008 | 2,470 / 2,237 | EN55_native: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | — |
| `EN121:0028` | book=EN55_native, contract=LEGACY, target=1.5, hold=12 | 1,108 | 889 | 10 | -3,842 | 1,108 / 889 | EN55_native: -1,347 / x2 -1,347 (3 ch) | ACTIVATION-LIMITED | — |
| `EN121:0029` | book=EN55_native, contract=NEAREST_ONE_LOT, target=1.0, hold=8 | 457 | 263 | 10 | -2,872 | 457 / 263 | EN55_native: -1,974 / x2 -2,637 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0030` | book=EN55_native, contract=NEAREST_ONE_LOT, target=1.0, hold=12 | -1,037 | -1,207 | 10 | -3,614 | -1,211 / -1,364 | EN55_native: -3,443 / x2 -3,777 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0031` | book=EN55_native, contract=NEAREST_ONE_LOT, target=1.5, hold=8 | 457 | 263 | 10 | -2,872 | 457 / 263 | EN55_native: -1,974 / x2 -2,637 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0032` | book=EN55_native, contract=NEAREST_ONE_LOT, target=1.5, hold=12 | -1,037 | -1,207 | 10 | -3,614 | -1,211 / -1,364 | EN55_native: -3,443 / x2 -3,777 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0033` | book=EN55_native, contract=NEAREST_SAME_ROOM, target=1.0, hold=8 | 129 | -71 | 10 | -3,200 | 129 / -71 | EN55_native: -2,308 / x2 -2,669 (6 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0034` | book=EN55_native, contract=NEAREST_SAME_ROOM, target=1.0, hold=12 | -1,365 | -1,541 | 10 | -3,942 | -1,539 / -1,698 | EN55_native: -3,777 / x2 -3,777 (6 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0035` | book=EN55_native, contract=NEAREST_SAME_ROOM, target=1.5, hold=8 | 129 | -71 | 10 | -3,200 | 129 / -71 | EN55_native: -2,308 / x2 -2,669 (6 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN121:0036` | book=EN55_native, contract=NEAREST_SAME_ROOM, target=1.5, hold=12 | -1,365 | -1,541 | 10 | -3,942 | -1,539 / -1,698 | EN55_native: -3,777 / x2 -3,777 (6 ch) | SPARSE ECONOMIC SCREEN | — |

## EN122 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN122:0001` | window_end=870, put_mult=1, money=NATIVE, geometry=DEFAULT, gate=NONE | 3,023 | 1,481 | 55 | 508 | 2,124 / -3,293 | E032_native: -10,105 / x2 -12,390 (37 ch) | SCREENED | 3,361 |
| `EN122:0002` | window_end=870, put_mult=1, money=NATIVE, geometry=DEFAULT, gate=CALLS_ONLY | 5,176 | 4,001 | 40 | 2,596 | 5,176 / 4,001 | E032_native: -7,586 / x2 -10,146 (50 ch) | SCREENED | 5,120 |
| `EN122:0003` | window_end=870, put_mult=1, money=NATIVE, geometry=JOINT, gate=NONE | 2,354 | 739 | 55 | -969 | -774 / -4,043 H | E032_native: -10,847 / x2 -13,132 (58 ch) | SCREENED | 1,598 |
| `EN122:0004` | window_end=870, put_mult=1, money=NATIVE, geometry=JOINT, gate=CALLS_ONLY | 4,187 | 2,782 | 40 | 863 | 4,187 / 2,023 | E032_native: -8,804 / x2 -11,364 (61 ch) | SCREENED | 3,021 |
| `EN122:0005` | window_end=870, put_mult=1, money=ENVELOPE, geometry=DEFAULT, gate=NONE | 3,006 | 2,246 | 55 | -1,298 | -3,445 / -4,035 H | E032_native: -9,340 / x2 -11,614 (50 ch) | SCREENED | 4,795 |
| `EN122:0006` | window_end=870, put_mult=1, money=ENVELOPE, geometry=DEFAULT, gate=CALLS_ONLY | 7,615 | 6,516 | 39 | 3,310 | 6,533 / 6,257 | E032_native: -5,070 / x2 -7,630 (47 ch) | SCREENED | 8,476 |
| `EN122:0007` | window_end=870, put_mult=1, money=ENVELOPE, geometry=JOINT, gate=NONE | 8,072 | 4,742 | 57 | 627 | -4,108 / -4,116 H | E032_native: -6,844 / x2 -11,359 (67 ch) | SCREENED | 3,841 |
| `EN122:0008` | window_end=870, put_mult=1, money=ENVELOPE, geometry=JOINT, gate=CALLS_ONLY | 10,757 | 8,041 | 40 | 3,313 | 7,485 / 5,729 | E032_native: -3,545 / x2 -8,060 (65 ch) | SCREENED | 6,345 |
| `EN122:0009` | window_end=870, put_mult=2, money=NATIVE, geometry=DEFAULT, gate=NONE | 6,246 | 4,002 | 53 | 2,838 | 5,671 / 1,431 | E032_native: -7,584 / x2 -9,868 (13 ch) | SPARSE ECONOMIC SCREEN | 7,669 |
| `EN122:0010` | window_end=870, put_mult=2, money=NATIVE, geometry=DEFAULT, gate=CALLS_ONLY | 8,149 | 6,246 | 39 | 4,617 | 8,149 / 6,246 | E032_native: -5,340 / x2 -7,900 (27 ch) | SCREENED | 9,429 |
| `EN122:0011` | window_end=870, put_mult=2, money=NATIVE, geometry=JOINT, gate=NONE | 6,145 | 3,207 | 55 | 1,489 | 4,283 / -4,147 H | E032_native: -8,379 / x2 -10,664 (56 ch) | SCREENED | 6,690 |
| `EN122:0012` | window_end=870, put_mult=2, money=NATIVE, geometry=JOINT, gate=CALLS_ONLY | 7,978 | 5,250 | 40 | 3,263 | 7,978 / 5,250 | E032_native: -6,336 / x2 -8,896 (59 ch) | SCREENED | 8,113 |
| `EN122:0013` | window_end=870, put_mult=2, money=ENVELOPE, geometry=DEFAULT, gate=NONE | 4,361 | 3,484 | 55 | 57 | -3,445 / -4,035 H | E032_native: -8,102 / x2 -10,376 (47 ch) | SCREENED | 6,090 |
| `EN122:0014` | window_end=870, put_mult=2, money=ENVELOPE, geometry=DEFAULT, gate=CALLS_ONLY | 9,257 | 8,029 | 39 | 4,953 | 8,176 / 7,848 | E032_native: -3,557 / x2 -6,117 (43 ch) | SCREENED | 9,771 |
| `EN122:0015` | window_end=870, put_mult=2, money=ENVELOPE, geometry=JOINT, gate=NONE | 8,671 | 5,159 | 57 | 1,226 | -4,135 / -4,041 H | E032_native: -6,427 / x2 -10,942 (66 ch) | SCREENED | 6,814 |
| `EN122:0016` | window_end=870, put_mult=2, money=ENVELOPE, geometry=JOINT, gate=CALLS_ONLY | 11,357 | 8,459 | 40 | 3,912 | 7,018 / 6,039 | E032_native: -3,127 / x2 -7,642 (64 ch) | SCREENED | 9,318 |
| `EN122:0017` | window_end=900, put_mult=1, money=NATIVE, geometry=DEFAULT, gate=NONE | 7,174 | 5,440 | 68 | 11 | -4,245 / -4,199 H | E032_native: -6,146 / x2 -7,241 (31 ch) | SCREENED | 1,466 |
| `EN122:0018` | window_end=900, put_mult=1, money=NATIVE, geometry=DEFAULT, gate=CALLS_ONLY | 9,187 | 7,900 | 50 | 2,024 | 9,187 / 7,900 | E032_native: -3,686 / x2 -5,057 (47 ch) | SCREENED | 4,097 |
| `EN122:0019` | window_end=900, put_mult=1, money=NATIVE, geometry=JOINT, gate=NONE | 2,312 | 557 | 69 | -1,313 | 2,312 / 807 | E032_native: -11,029 / x2 -12,854 (58 ch) | SCREENED | 449 |
| `EN122:0020` | window_end=900, put_mult=1, money=NATIVE, geometry=JOINT, gate=CALLS_ONLY | 3,243 | 1,761 | 51 | -220 | 3,243 / 1,761 | E032_native: -9,826 / x2 -11,926 (61 ch) | SCREENED | 2,354 |
| `EN122:0021` | window_end=900, put_mult=1, money=ENVELOPE, geometry=DEFAULT, gate=NONE | 6,774 | 5,246 | 68 | -2,303 | -4,024 / -4,138 H | E032_native: -6,340 / x2 -8,163 (47 ch) | SCREENED | 6,260 |
| `EN122:0022` | window_end=900, put_mult=1, money=ENVELOPE, geometry=DEFAULT, gate=CALLS_ONLY | 10,933 | 9,203 | 49 | 1,855 | 11,175 / 9,630 | E032_native: -2,383 / x2 -4,221 (44 ch) | SCREENED | 11,200 |
| `EN122:0023` | window_end=900, put_mult=1, money=ENVELOPE, geometry=JOINT, gate=NONE | 7,394 | 3,678 | 71 | -51 | 8,178 / 6,781 | E032_native: -7,908 / x2 -12,423 (67 ch) | SCREENED | 1,994 |
| `EN122:0024` | window_end=900, put_mult=1, money=ENVELOPE, geometry=JOINT, gate=CALLS_ONLY | 9,178 | 6,137 | 51 | 1,733 | 5,631 / 3,396 | E032_native: -5,449 / x2 -9,964 (65 ch) | SCREENED | 4,980 |
| `EN122:0025` | window_end=900, put_mult=2, money=NATIVE, geometry=DEFAULT, gate=NONE | 14,275 | 11,586 | 66 | 652 | -4,123 / -4,036 H | E032_native: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | 3,642 |
| `EN122:0026` | window_end=900, put_mult=2, money=NATIVE, geometry=DEFAULT, gate=CALLS_ONLY | 16,037 | 13,770 | 49 | 2,414 | 16,331 / 14,122 H | E032_native: 2,184 / x2 1,235 (17 ch) | SPARSE ECONOMIC SCREEN | 6,273 |
| `EN122:0027` | window_end=900, put_mult=2, money=NATIVE, geometry=JOINT, gate=NONE | 10,471 | 7,156 | 69 | 1,183 | 10,471 / 6,459 H | E032_native: -4,430 / x2 -6,748 (55 ch) | SCREENED | 5,001 |
| `EN122:0028` | window_end=900, put_mult=2, money=NATIVE, geometry=JOINT, gate=CALLS_ONLY | 11,402 | 8,359 | 51 | 2,114 | 11,402 / 8,359 | E032_native: -3,227 / x2 -5,610 (58 ch) | SCREENED | 6,907 |
| `EN122:0029` | window_end=900, put_mult=2, money=ENVELOPE, geometry=DEFAULT, gate=NONE | 12,180 | 10,399 | 68 | -2,090 | -4,024 / -4,138 H | E032_native: -1,187 / x2 -3,010 (41 ch) | SCREENED | 6,157 |
| `EN122:0030` | window_end=900, put_mult=2, money=ENVELOPE, geometry=DEFAULT, gate=CALLS_ONLY | 16,300 | 14,292 | 49 | 2,031 | 11,788 / 9,694 | E032_native: 2,705 / x2 883 (36 ch) | SCREENED | 11,096 |
| `EN122:0031` | window_end=900, put_mult=2, money=ENVELOPE, geometry=JOINT, gate=NONE | 12,704 | 8,656 | 71 | 1,440 | 13,261 / 7,115 | E032_native: -2,930 / x2 -7,445 (65 ch) | SCREENED | 4,740 |
| `EN122:0032` | window_end=900, put_mult=2, money=ENVELOPE, geometry=JOINT, gate=CALLS_ONLY | 14,487 | 11,115 | 51 | 3,224 | 10,522 / 8,896 | E032_native: -471 / x2 -4,986 (63 ch) | SCREENED | 7,727 |

## EN122 — SENSEX

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN122:0001` | window_end=870, put_mult=1, money=NATIVE, geometry=DEFAULT, gate=NONE | 1,723 | 1,542 | 6 | -593 | 1,723 / 1,542 | E032_native: -379 / x2 -2,381 (10 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0003` | window_end=870, put_mult=1, money=NATIVE, geometry=JOINT, gate=NONE | 974 | 940 | 6 | -908 | 974 / 940 | E032_native: -981 / x2 -2,982 (11 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0005` | window_end=870, put_mult=1, money=ENVELOPE, geometry=DEFAULT, gate=NONE | 5,167 | 4,746 | 7 | -1,372 | 4,501 / 4,114 | E032_native: 2,825 / x2 991 (8 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0007` | window_end=870, put_mult=1, money=ENVELOPE, geometry=JOINT, gate=NONE | 948 | 817 | 7 | -1,992 | 715 / 574 | E032_native: -1,104 / x2 -2,938 (12 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0009` | window_end=870, put_mult=2, money=NATIVE, geometry=DEFAULT, gate=NONE | 5,939 | 5,548 | 7 | -599 | 5,939 / 5,548 | E032_native: 3,628 / x2 1,793 (5 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0011` | window_end=870, put_mult=2, money=NATIVE, geometry=JOINT, gate=NONE | 1,234 | 1,147 | 7 | -1,418 | 1,234 / 1,147 | E032_native: -773 / x2 -2,608 (11 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0013` | window_end=870, put_mult=2, money=ENVELOPE, geometry=DEFAULT, gate=NONE | 5,357 | 4,920 | 7 | -1,181 | 4,692 / 4,288 | E032_native: 3,000 / x2 1,166 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0015` | window_end=870, put_mult=2, money=ENVELOPE, geometry=JOINT, gate=NONE | 1,003 | 844 | 7 | -1,936 | 770 / 601 | E032_native: -1,077 / x2 -2,911 (12 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0017` | window_end=900, put_mult=1, money=NATIVE, geometry=DEFAULT, gate=NONE | -759 | -1,029 | 11 | -3,075 | -759 / -1,477 | E032_native: -2,949 / x2 -4,006 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0019` | window_end=900, put_mult=1, money=NATIVE, geometry=JOINT, gate=NONE | -1,507 | -1,631 | 11 | -3,390 | -1,507 / -1,875 | E032_native: -3,551 / x2 -4,608 (8 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0021` | window_end=900, put_mult=1, money=ENVELOPE, geometry=DEFAULT, gate=NONE | 389 | -217 | 12 | -6,149 | 1,657 / 1,380 | E032_native: -2,138 / x2 -2,138 (6 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0023` | window_end=900, put_mult=1, money=ENVELOPE, geometry=JOINT, gate=NONE | -2,302 | -2,570 | 11 | -5,241 | -1,322 / -1,612 | E032_native: -4,490 / x2 -5,903 (12 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0025` | window_end=900, put_mult=2, money=NATIVE, geometry=DEFAULT, gate=NONE | 2,449 | 1,921 | 12 | -4,089 | 1,987 / 1,516 | E032_native: 0 / x2 0 (0 ch) | ACTIVATION-LIMITED DUP | — |
| `EN122:0027` | window_end=900, put_mult=2, money=NATIVE, geometry=JOINT, gate=NONE | -1,269 | -1,442 | 11 | -3,922 | -1,320 / -1,560 | E032_native: -3,362 / x2 -4,401 (8 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0029` | window_end=900, put_mult=2, money=ENVELOPE, geometry=DEFAULT, gate=NONE | 580 | -43 | 12 | -5,958 | 1,847 / 1,554 | E032_native: -1,963 / x2 -1,963 (5 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN122:0031` | window_end=900, put_mult=2, money=ENVELOPE, geometry=JOINT, gate=NONE | -2,605 | -2,916 | 11 | -5,545 | -1,626 / -1,959 | E032_native: -4,837 / x2 -6,023 (12 ch) | SPARSE ECONOMIC SCREEN | — |

## EN123 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN123:0001` | base=EN87, target=1.0, at_target=SELL_ALL, stop=0.35 | 9,335 | 7,914 | 25 | 4,707 | 9,537 / 8,171 | EN87: 2,074 / x2 305 (24 ch) | SCREENED | 7,157 |
| `EN123:0002` | base=EN87, target=1.0, at_target=SELL_ALL, stop=0.25 | 8,914 | 8,476 | 25 | 4,285 | 8,863 / 8,476 | EN87: 2,635 / x2 866 (25 ch) | SCREENED | 7,659 |
| `EN123:0003` | base=EN87, target=1.0, at_target=RUNNER_KEEP_0.5, stop=0.35 | 2,588 | 1,245 | 25 | -914 | 829 / -1,021 | EN87: -4,596 / x2 -6,364 (24 ch) | SCREENED | 10,183 |
| `EN123:0004` | base=EN87, target=1.0, at_target=RUNNER_KEEP_0.5, stop=0.25 | 2,167 | 1,806 | 25 | -1,336 | 1,858 / 712 | EN87: -4,034 / x2 -5,803 (25 ch) | SCREENED | 10,686 |
| `EN123:0005` | base=EN87, target=1.0, at_target=RUNNER_KEEP_0.7, stop=0.35 | 5,472 | 4,103 | 25 | 1,970 | 4,948 / 3,413 | EN87: -1,738 / x2 -3,507 (24 ch) | SCREENED | 4,120 |
| `EN123:0006` | base=EN87, target=1.0, at_target=RUNNER_KEEP_0.7, stop=0.25 | 5,050 | 4,664 | 25 | 1,548 | 5,000 / 4,465 | EN87: -1,177 / x2 -2,945 (25 ch) | SCREENED | 4,623 |
| `EN123:0007` | base=EN87, target=1.5, at_target=SELL_ALL, stop=0.35 | 8,965 | 7,551 | 25 | 4,613 | 9,167 / 7,808 | EN87: 1,710 / x2 -111 (24 ch) | SCREENED | 6,592 |
| `EN123:0008` | base=EN87, target=1.5, at_target=SELL_ALL, stop=0.25 | 8,544 | 8,112 | 25 | 4,191 | 8,493 / 8,112 | EN87: 2,272 / x2 450 (25 ch) | SCREENED | 7,095 |
| `EN123:0009` | base=EN87, target=1.5, at_target=RUNNER_KEEP_0.5, stop=0.35 | 8,965 | 7,551 | 25 | 4,613 | 8,234 / 6,901 | EN87: 1,710 / x2 -111 (24 ch) | SCREENED | 6,592 |
| `EN123:0010` | base=EN87, target=1.5, at_target=RUNNER_KEEP_0.5, stop=0.25 | 8,544 | 8,112 | 25 | 4,191 | 8,493 / 8,112 | EN87: 2,272 / x2 450 (25 ch) | SCREENED | 7,095 |
| `EN123:0011` | base=EN87, target=1.5, at_target=RUNNER_KEEP_0.7, stop=0.35 | 8,965 | 7,551 | 25 | 4,613 | 8,260 / 6,927 | EN87: 1,710 / x2 -111 (24 ch) | SCREENED | 6,592 |
| `EN123:0012` | base=EN87, target=1.5, at_target=RUNNER_KEEP_0.7, stop=0.25 | 8,544 | 8,112 | 25 | 4,191 | 8,493 / 8,112 | EN87: 2,272 / x2 450 (25 ch) | SCREENED | 7,095 |
| `EN123:0013` | base=E03_env, target=1.0, at_target=SELL_ALL, stop=0.35 | 5,969 | 3,256 | 57 | 809 | -3,381 / -3,553 | E03_env: 1,010 / x2 -759 (53 ch) | SCREENED | 5,311 |
| `EN123:0014` | base=E03_env, target=1.0, at_target=SELL_ALL, stop=0.25 | 4,934 | 3,240 | 57 | -225 | 5,521 / -4,023 H | E03_env: 994 / x2 -775 (54 ch) | SCREENED | 5,853 |
| `EN123:0015` | base=E03_env, target=1.0, at_target=RUNNER_KEEP_0.5, stop=0.35 | -413 | -3,012 | 56 | -5,183 | -3,756 / -4,146 H | E03_env: -5,258 / x2 -7,027 (52 ch) | SCREENED | 10,981 |
| `EN123:0016` | base=E03_env, target=1.0, at_target=RUNNER_KEEP_0.5, stop=0.25 | -1,447 | -3,028 | 56 | -6,218 | -4,236 / -4,023 H | E03_env: -5,274 / x2 -7,043 (53 ch) | SCREENED | 11,523 |
| `EN123:0017` | base=E03_env, target=1.0, at_target=RUNNER_KEEP_0.7, stop=0.35 | 2,106 | -556 | 57 | -2,665 | -3,795 / -4,146 H | E03_env: -2,801 / x2 -4,570 (53 ch) | SCREENED | 1,944 |
| `EN123:0018` | base=E03_env, target=1.0, at_target=RUNNER_KEEP_0.7, stop=0.25 | 1,071 | -572 | 57 | -3,699 | -4,187 / -4,023 H | E03_env: -2,818 / x2 -4,586 (54 ch) | SCREENED | 2,486 |
| `EN123:0019` | base=E03_env, target=1.5, at_target=SELL_ALL, stop=0.35 | 5,599 | 2,892 | 57 | 634 | -2,931 / -3,265 | E03_env: 647 / x2 -1,175 (53 ch) | SCREENED | 4,747 |
| `EN123:0020` | base=E03_env, target=1.5, at_target=SELL_ALL, stop=0.25 | 4,565 | 2,876 | 57 | -401 | 5,122 / -4,023 H | E03_env: 630 / x2 -1,191 (54 ch) | SCREENED | 5,288 |
| `EN123:0021` | base=E03_env, target=1.5, at_target=RUNNER_KEEP_0.5, stop=0.35 | 5,599 | 2,892 | 57 | 634 | -3,707 / -4,146 H | E03_env: 647 / x2 -1,175 (53 ch) | SCREENED | 4,747 |
| `EN123:0022` | base=E03_env, target=1.5, at_target=RUNNER_KEEP_0.5, stop=0.25 | 4,565 | 2,876 | 57 | -401 | 4,416 / -4,023 H | E03_env: 630 / x2 -1,191 (54 ch) | SCREENED | 5,288 |
| `EN123:0023` | base=E03_env, target=1.5, at_target=RUNNER_KEEP_0.7, stop=0.35 | 5,599 | 2,892 | 57 | 634 | -3,707 / -4,146 H | E03_env: 647 / x2 -1,175 (53 ch) | SCREENED | 4,747 |
| `EN123:0024` | base=E03_env, target=1.5, at_target=RUNNER_KEEP_0.7, stop=0.25 | 4,565 | 2,876 | 57 | -401 | 4,442 / -4,023 H | E03_env: 630 / x2 -1,191 (54 ch) | SCREENED | 5,288 |

## EN123 — SENSEX

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN123:0013` | base=E03_env, target=1.0, at_target=SELL_ALL, stop=0.35 | 1,939 | 1,558 | 7 | -1,480 | 1,606 / 1,253 | E03_env: -3,188 / x2 -3,339 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0014` | base=E03_env, target=1.0, at_target=SELL_ALL, stop=0.25 | 1,939 | 1,558 | 7 | -1,480 | 1,606 / 1,253 | E03_env: -3,188 / x2 -3,339 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0015` | base=E03_env, target=1.0, at_target=RUNNER_KEEP_0.5, stop=0.35 | 1,266 | 893 | 7 | -1,480 | 934 / 587 | E03_env: -3,854 / x2 -4,005 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0016` | base=E03_env, target=1.0, at_target=RUNNER_KEEP_0.5, stop=0.25 | 1,266 | 893 | 7 | -1,480 | 934 / 587 | E03_env: -3,854 / x2 -4,005 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0017` | base=E03_env, target=1.0, at_target=RUNNER_KEEP_0.7, stop=0.35 | 2,946 | 2,555 | 7 | -1,480 | 2,613 / 2,250 | E03_env: -2,191 / x2 -2,342 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0018` | base=E03_env, target=1.0, at_target=RUNNER_KEEP_0.7, stop=0.25 | 2,946 | 2,555 | 7 | -1,480 | 2,613 / 2,250 | E03_env: -2,191 / x2 -2,342 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0019` | base=E03_env, target=1.5, at_target=SELL_ALL, stop=0.35 | 1,939 | 1,558 | 7 | -1,480 | 1,606 / 1,253 | E03_env: -3,188 / x2 -3,339 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0020` | base=E03_env, target=1.5, at_target=SELL_ALL, stop=0.25 | 1,939 | 1,558 | 7 | -1,480 | 1,606 / 1,253 | E03_env: -3,188 / x2 -3,339 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0021` | base=E03_env, target=1.5, at_target=RUNNER_KEEP_0.5, stop=0.35 | 1,266 | 893 | 7 | -1,480 | 934 / 587 | E03_env: -3,854 / x2 -4,005 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0022` | base=E03_env, target=1.5, at_target=RUNNER_KEEP_0.5, stop=0.25 | 1,266 | 893 | 7 | -1,480 | 934 / 587 | E03_env: -3,854 / x2 -4,005 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0023` | base=E03_env, target=1.5, at_target=RUNNER_KEEP_0.7, stop=0.35 | 2,946 | 2,555 | 7 | -1,480 | 2,613 / 2,250 | E03_env: -2,191 / x2 -2,342 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN123:0024` | base=E03_env, target=1.5, at_target=RUNNER_KEEP_0.7, stop=0.25 | 2,946 | 2,555 | 7 | -1,480 | 2,613 / 2,250 | E03_env: -2,191 / x2 -2,342 (7 ch) | SPARSE ECONOMIC SCREEN | — |

## EN124 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN124:0001` | base=EN87, stress=ENTRY_PLUS1 | 6,172 | 5,590 | 19 | 1,926 | 5,522 / 4,134 | EN87: -250 / x2 -2,856 (25 ch) | SCREENED | 3,943 |
| `EN124:0002` | base=EN87, stress=SELL_PLUS1 | 10,882 | 10,742 | 25 | 6,004 | 10,361 / 9,902 | EN87: 4,901 / x2 2,073 (25 ch) | SCREENED | 5,065 |
| `EN124:0003` | base=EN87, stress=FEE_PLUS1ORDER | 5,524 | 5,274 | 25 | 2,126 | 4,716 / 4,382 | EN87: -566 / x2 -566 (25 ch) | SCREENED | 5,166 |
| `EN124:0004` | base=EN87, stress=ALL | 5,321 | 4,640 | 19 | 1,006 | 5,034 / 3,914 | EN87: -1,201 / x2 -3,986 (25 ch) | SCREENED | 4,683 |
| `EN124:0005` | base=EN87_JOINT, stress=ENTRY_PLUS1 | 7,512 | 5,531 | 20 | 2,180 | 7,520 / 5,013 | EN124:0001: -59 / x2 -2,241 (20 ch) | SCREENED | 9,225 |
| `EN124:0006` | base=EN87_JOINT, stress=SELL_PLUS1 | 10,354 | 7,940 | 25 | 4,693 | 9,086 / 6,350 | EN124:0002: -2,802 / x2 -4,546 (24 ch) | SCREENED | 6,044 |
| `EN124:0007` | base=EN87_JOINT, stress=FEE_PLUS1ORDER | 9,459 | 7,332 | 25 | 3,525 | 6,139 / 4,563 | EN124:0003: 2,057 / x2 -1,038 (24 ch) | SCREENED | 5,107 |
| `EN124:0008` | base=EN87_JOINT, stress=ALL | 8,681 | 5,619 | 20 | 3,121 | 8,681 / 4,416 | EN124:0004: 979 / x2 -1,025 (20 ch) | SCREENED | 8,129 |
| `EN124:0009` | base=E03_env_JOINT, stress=ENTRY_PLUS1 | 6,692 | 3,841 | 43 | 30 | 3,556 / 1,030 | EN124:0001: -1,749 / x2 -5,323 (43 ch) | SCREENED | 4,760 |
| `EN124:0010` | base=E03_env_JOINT, stress=SELL_PLUS1 | 7,396 | 3,412 | 57 | 309 | -4,115 / -4,104 H | EN124:0002: -7,330 / x2 -10,903 (56 ch) | SCREENED | 3,838 |
| `EN124:0011` | base=E03_env_JOINT, stress=FEE_PLUS1ORDER | 6,726 | 3,444 | 57 | -624 | -4,016 / -4,064 H | EN124:0003: -1,830 / x2 -6,274 (56 ch) | SCREENED | 2,921 |
| `EN124:0012` | base=E03_env_JOINT, stress=ALL | 6,378 | 2,917 | 43 | -120 | 3,035 / -211 | EN124:0004: -1,723 / x2 -5,561 (43 ch) | SCREENED | 2,248 |
| `EN124:0013` | base=E032_JOINT, stress=ENTRY_PLUS1 | 8,400 | 5,001 | 51 | 932 | 8,400 / 3,266 | EN124:0001: -590 / x2 -6,137 (51 ch) | SCREENED | 1,546 |
| `EN124:0014` | base=E032_JOINT, stress=SELL_PLUS1 | 15,197 | 11,350 | 69 | 3,010 | 14,399 / 10,581 | EN124:0002: 608 / x2 -11,002 (68 ch) | SCREENED | 5,624 |
| `EN124:0015` | base=E032_JOINT, stress=FEE_PLUS1ORDER | 8,843 | 5,598 | 69 | -374 | 6,869 / -4,037 H | EN124:0003: 324 / x2 -7,524 (68 ch) | SCREENED | 3,844 |
| `EN124:0016` | base=E032_JOINT, stress=ALL | 7,660 | 4,467 | 51 | 585 | 7,140 / 3,257 | EN124:0004: -173 / x2 -6,154 (51 ch) | SCREENED | 56 |

## EN124 — SENSEX

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN124:0009` | base=E03_env_JOINT, stress=ENTRY_PLUS1 | 879 | 605 | 6 | -1,547 | 879 / 605 | EN121:0008: -212 / x2 -829 (8 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN124:0010` | base=E03_env_JOINT, stress=SELL_PLUS1 | 1,145 | 850 | 7 | -2,038 | 863 / 625 | EN121:0008: 33 / x2 -696 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN124:0011` | base=E03_env_JOINT, stress=FEE_PLUS1ORDER | 783 | 651 | 7 | -2,110 | 549 / 408 | EN121:0008: -165 / x2 -165 (7 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN124:0012` | base=E03_env_JOINT, stress=ALL | 1,523 | 1,242 | 6 | -1,634 | 1,523 / 1,242 | EN121:0008: 425 / x2 -758 (8 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN124:0013` | base=E032_JOINT, stress=ENTRY_PLUS1 | -122 | -436 | 8 | -2,548 | -122 / -436 | EN121:0020: 1,005 / x2 -561 (12 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN124:0014` | base=E032_JOINT, stress=SELL_PLUS1 | -809 | -1,145 | 11 | -3,816 | -809 / -1,345 | EN121:0020: 296 / x2 -587 (11 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN124:0015` | base=E032_JOINT, stress=FEE_PLUS1ORDER | -1,529 | -1,701 | 11 | -4,135 | -1,579 / -1,700 | EN121:0020: -260 / x2 -260 (11 ch) | SPARSE ECONOMIC SCREEN | — |
| `EN124:0016` | base=E032_JOINT, stress=ALL | 1,059 | 735 | 8 | -2,099 | 1,059 / 735 | EN121:0020: 2,177 / x2 211 (12 ch) | SPARSE ECONOMIC SCREEN | — |

## EN125 — NIFTY

| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| `EN125:0001` | contract=LEGACY_UP_TO_3, wall=FROZEN_AT_ENTRY, trigger=AT_WALL, action=EXIT_ALL | 7,944 | 7,647 | 25 | 2,667 | 6,230 / 5,860 | EN87: 1,807 / x2 -425 (5 ch) | SPARSE ECONOMIC SCREEN | 5,264 |
| `EN125:0002` | contract=LEGACY_UP_TO_3, wall=FROZEN_AT_ENTRY, trigger=AT_WALL, action=TIGHTEN_TRAIL_0.8 | 5,864 | 5,588 | 25 | 2,230 | 4,891 / 4,533 | EN87: -253 / x2 -681 (4 ch) | ACTIVATION-LIMITED | 4,832 |
| `EN125:0003` | contract=LEGACY_UP_TO_3, wall=FROZEN_AT_ENTRY, trigger=HALF_STEP_BEFORE, action=EXIT_ALL | 1,798 | 2,119 | 25 | -1,384 | 1,136 / 1,609 | EN87: -3,722 / x2 -5,149 (8 ch) | SPARSE ECONOMIC SCREEN | 577 |
| `EN125:0004` | contract=LEGACY_UP_TO_3, wall=FROZEN_AT_ENTRY, trigger=HALF_STEP_BEFORE, action=TIGHTEN_TRAIL_0.8 | 5,219 | 5,033 | 25 | 1,724 | 4,722 / 4,115 | EN87: -808 / x2 -1,100 (5 ch) | SPARSE ECONOMIC SCREEN | 4,453 |
| `EN125:0005` | contract=LEGACY_UP_TO_3, wall=CURRENT, trigger=AT_WALL, action=EXIT_ALL | 6,594 | 6,311 | 25 | 2,220 | 4,881 / 4,523 | EN87: 470 / x2 -775 (4 ch) | ACTIVATION-LIMITED | 4,634 |
| `EN125:0006` | contract=LEGACY_UP_TO_3, wall=CURRENT, trigger=AT_WALL, action=TIGHTEN_TRAIL_0.8 | 5,598 | 5,322 | 25 | 1,964 | 4,625 / 4,267 | EN87: -519 / x2 -740 (3 ch) | ACTIVATION-LIMITED | 4,566 |
| `EN125:0007` | contract=LEGACY_UP_TO_3, wall=CURRENT, trigger=HALF_STEP_BEFORE, action=EXIT_ALL | 3,119 | 3,423 | 25 | -64 | 2,566 / 2,913 | EN87: -2,418 / x2 -4,218 (8 ch) | SPARSE ECONOMIC SCREEN | 3,503 |
| `EN125:0008` | contract=LEGACY_UP_TO_3, wall=CURRENT, trigger=HALF_STEP_BEFORE, action=TIGHTEN_TRAIL_0.8 | 5,774 | 5,802 | 25 | 2,278 | 5,277 / 4,884 | EN87: -39 / x2 -850 (6 ch) | SPARSE ECONOMIC SCREEN | 4,453 |
| `EN125:0009` | contract=NEAREST_ONE_LOT, wall=FROZEN_AT_ENTRY, trigger=AT_WALL, action=EXIT_ALL | 9,971 | 8,544 | 25 | 5,343 | 9,268 / 7,905 | EN111:0010: 629 / x2 -581 (4 ch) | ACTIVATION-LIMITED | 5,395 |
| `EN125:0010` | contract=NEAREST_ONE_LOT, wall=FROZEN_AT_ENTRY, trigger=AT_WALL, action=TIGHTEN_TRAIL_0.8 | 8,972 | 7,554 | 25 | 4,344 | 8,937 / 7,577 | EN111:0010: -360 / x2 -594 (2 ch) | ACTIVATION-LIMITED | 5,885 |
| `EN125:0011` | contract=NEAREST_ONE_LOT, wall=FROZEN_AT_ENTRY, trigger=HALF_STEP_BEFORE, action=EXIT_ALL | 6,250 | 4,875 | 25 | 1,736 | 5,354 / 4,063 | EN111:0010: -3,039 / x2 -4,045 (8 ch) | SPARSE ECONOMIC SCREEN | 1,049 |
| `EN125:0012` | contract=NEAREST_ONE_LOT, wall=FROZEN_AT_ENTRY, trigger=HALF_STEP_BEFORE, action=TIGHTEN_TRAIL_0.8 | 8,651 | 7,236 | 25 | 4,023 | 8,616 / 7,260 | EN111:0010: -678 / x2 -912 (3 ch) | ACTIVATION-LIMITED | 5,619 |
| `EN125:0013` | contract=NEAREST_ONE_LOT, wall=CURRENT, trigger=AT_WALL, action=EXIT_ALL | 9,423 | 8,544 | 25 | 4,795 | 8,719 / 7,905 | EN111:0010: 629 / x2 -581 (5 ch) | SPARSE ECONOMIC SCREEN | 5,917 |
| `EN125:0014` | contract=NEAREST_ONE_LOT, wall=CURRENT, trigger=AT_WALL, action=TIGHTEN_TRAIL_0.8 | 8,972 | 7,554 | 25 | 4,344 | 8,937 / 7,577 | EN111:0010: -360 / x2 -594 (2 ch) | ACTIVATION-LIMITED | 5,885 |
| `EN125:0015` | contract=NEAREST_ONE_LOT, wall=CURRENT, trigger=HALF_STEP_BEFORE, action=EXIT_ALL | 6,630 | 6,127 | 25 | 2,116 | 5,733 / 5,315 | EN111:0010: -1,787 / x2 -3,348 (9 ch) | SPARSE ECONOMIC SCREEN | 3,391 |
| `EN125:0016` | contract=NEAREST_ONE_LOT, wall=CURRENT, trigger=HALF_STEP_BEFORE, action=TIGHTEN_TRAIL_0.8 | 9,206 | 7,781 | 25 | 4,577 | 9,170 / 7,805 | EN111:0010: -133 / x2 -912 (4 ch) | ACTIVATION-LIMITED | 5,619 |

## Unavailable

- `EN111:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0013|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0014|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0015|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0016|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0017|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:0018|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:equal_one_lot_t1.0_h10|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:equal_one_lot_t1.0_h12|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:equal_one_lot_t1.0_h8|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:equal_one_lot_t1.25_h10|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:equal_one_lot_t1.25_h12|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:equal_one_lot_t1.25_h8|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:equal_one_lot_t1.5_h10|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:equal_one_lot_t1.5_h12|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:equal_one_lot_t1.5_h8|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:no_partial_t1.0_h12|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:no_partial_t1.0_h8|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:no_partial_t1.5_h12|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN111:ctl:no_partial_t1.5_h8|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0013|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0014|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0015|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0016|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0017|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:0018|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:ctl:fixed_both|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:ctl:fixed_hold_only|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:ctl:fixed_target_only|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0013|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0014|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0015|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0016|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0017|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_0018|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0013|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0014|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0015|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0016|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0017|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:dyn:random_r1_0018|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0013|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0014|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0015|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0016|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0017|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN112:r1:0018|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:fast_oi_only_L1_p80|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:fast_oi_only_L1_p90|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:fast_oi_only_L3_p80|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:fast_oi_only_L3_p90|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:fast_oi_only_L5_p80|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:fast_oi_only_L5_p90|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:fixed12|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:price_giveback|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_deny_L1_p80|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_deny_L1_p90|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_deny_L3_p80|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_deny_L3_p90|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_deny_L5_p80|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_deny_L5_p90|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_giveback_L1_p80|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_giveback_L1_p90|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_giveback_L3_p80|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_giveback_L3_p90|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_giveback_L5_p80|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN113:ctl:stale_giveback_L5_p90|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0013|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0014|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0015|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0016|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0017|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:0018|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:ctl:fixed_12_base_and_runner|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:ctl:fixed_12_base_only|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:ctl:fixed_16_base_and_runner|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:ctl:fixed_16_base_only|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:ctl:fixed_4_base_and_runner|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:ctl:fixed_4_base_only|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:ctl:fixed_8_base_and_runner|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:ctl:fixed_8_base_only|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:ctl:volratio|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0013|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0014|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0015|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0016|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0017|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN114:dyn:matched_0018|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w20_r10_p0|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w20_r10_p1|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w20_r1_p0|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w20_r1_p1|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w40_r10_p0|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w40_r10_p1|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w40_r1_p0|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w40_r1_p1|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w60_r10_p0|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w60_r10_p1|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w60_r1_p0|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:constbeta_w60_r1_p1|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:equal_reserve_w40_r10|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN115:ctl:min_friction_one_lot|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:er_K2_R1_immediate|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:er_K2_R1_two_bar_hysteresis|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:er_K2_R5_immediate|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:er_K2_R5_two_bar_hysteresis|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:er_K3_R1_immediate|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:er_K3_R1_two_bar_hysteresis|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:er_K3_R5_immediate|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:er_K3_R5_two_bar_hysteresis|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:rnd_K2_R1_immediate|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:rnd_K2_R1_two_bar_hysteresis|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:rnd_K2_R5_immediate|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:rnd_K2_R5_two_bar_hysteresis|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:rnd_K3_R1_immediate|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:rnd_K3_R1_two_bar_hysteresis|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:rnd_K3_R5_immediate|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN116:ctl:rnd_K3_R5_two_bar_hysteresis|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0001:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0002:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0003:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0004:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0005:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0006:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0007:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0008:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0009:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0010:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0011:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:0012:no_oi|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN118:0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:ctl:direction_only|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN118:ctl:mean_actions|SENSEX`: SENSEX: 63 dates < the 100-date walk-forward start
- `EN120:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:ctl:fixed_priority_union|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN120:ctl:past_pnl_chooser|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0014|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0016|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0018|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0020|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0022|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0024|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0026|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0028|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0030|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN122:0032|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN123:0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN124:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN124:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN124:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN124:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN124:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN124:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN124:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN124:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0001|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0002|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0003|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0004|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0005|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0006|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0007|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0008|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0009|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0010|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0011|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0012|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0013|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0014|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0015|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `EN125:0016|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `REF:EN87_ONE_LOT|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied
- `REF:EN87|SENSEX`: DATA UNAVAILABLE: SENSEX OI not supplied

- EN119: 24 cells × index SOURCE-GATED

