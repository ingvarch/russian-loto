"""Russian Loto card generation logic."""

import random

# Column ranges: col 0 -> 1-9, col 1 -> 10-19, ..., col 8 -> 80-90
COLUMN_RANGES = []
for _col in range(9):
    lo = _col * 10 + 1 if _col > 0 else 1
    hi = _col * 10 + 9 if _col < 8 else 90
    COLUMN_RANGES.append((lo, hi))


def generate_card() -> list[list[int | None]]:
    """Generate a single valid Russian Loto card.

    Returns a 3x9 grid where each row has exactly 5 numbers and 4 Nones.
    Numbers are sorted top-to-bottom within each column.
    """
    while True:
        card = _try_generate()
        if card is not None:
            return card


def _try_generate() -> list[list[int | None]] | None:
    """Attempt to generate a valid card. Returns None if constraints can't be met."""
    # Step 1: For each column, pick 1-3 random numbers from its range
    col_numbers: list[list[int]] = []
    for lo, hi in COLUMN_RANGES:
        pool = list(range(lo, hi + 1))
        count = random.randint(1, 3)
        col_numbers.append(sorted(random.sample(pool, count)))

    # Step 2: Distribute numbers across 3 rows, each row must have exactly 5
    # Build a list of (col_index, number, position_in_col) assignments
    total = sum(len(nums) for nums in col_numbers)
    if total != 15:
        # Adjust: we need exactly 15 numbers total
        # Randomly add or remove numbers from columns
        col_numbers = _adjust_to_fifteen(col_numbers)
        if col_numbers is None:
            return None

    # Step 3: Assign row positions for numbers in each column
    # Each column with k numbers needs k distinct rows from {0,1,2}
    # Constraint: each row must have exactly 5 numbers

    row_counts = [0, 0, 0]  # how many numbers assigned to each row
    col_row_assignments: list[list[int]] = [[] for _ in range(9)]

    # Sort columns by size (descending) for better constraint satisfaction
    col_order = sorted(range(9), key=lambda c: -len(col_numbers[c]))

    if not _assign_rows(col_order, 0, col_numbers, col_row_assignments, row_counts):
        return None

    # Step 4: Build the card grid
    card: list[list[int | None]] = [[None] * 9 for _ in range(3)]
    for col in range(9):
        rows = sorted(col_row_assignments[col])
        nums = sorted(col_numbers[col])
        for row, num in zip(rows, nums):
            card[row][col] = num

    return card


def _adjust_to_fifteen(
    col_numbers: list[list[int]],
) -> list[list[int]] | None:
    """Adjust column numbers so the total count is exactly 15."""
    total = sum(len(nums) for nums in col_numbers)

    while total < 15:
        # Find columns that can accept more numbers (max 3)
        expandable = [i for i in range(9) if len(col_numbers[i]) < 3]
        if not expandable:
            return None
        col = random.choice(expandable)
        lo, hi = COLUMN_RANGES[col]
        available = [n for n in range(lo, hi + 1) if n not in col_numbers[col]]
        if not available:
            return None
        col_numbers[col].append(random.choice(available))
        col_numbers[col].sort()
        total += 1

    while total > 15:
        # Find columns that can lose numbers (min 1)
        shrinkable = [i for i in range(9) if len(col_numbers[i]) > 1]
        if not shrinkable:
            return None
        col = random.choice(shrinkable)
        col_numbers[col].pop(random.randrange(len(col_numbers[col])))
        total -= 1

    return col_numbers


def _assign_rows(
    col_order: list[int],
    idx: int,
    col_numbers: list[list[int]],
    assignments: list[list[int]],
    row_counts: list[int],
) -> bool:
    """Recursively assign rows to columns using backtracking."""
    if idx == len(col_order):
        return all(c == 5 for c in row_counts)

    col = col_order[idx]
    k = len(col_numbers[col])

    # Generate all combinations of k rows from {0,1,2}
    if k == 1:
        combos = [[0], [1], [2]]
    elif k == 2:
        combos = [[0, 1], [0, 2], [1, 2]]
    else:
        combos = [[0, 1, 2]]

    random.shuffle(combos)

    for combo in combos:
        # Check if adding these rows would exceed 5 per row
        valid = True
        for r in combo:
            if row_counts[r] + 1 > 5:
                valid = False
                break
        # Check remaining capacity
        if valid:
            remaining_cols = len(col_order) - idx - 1
            for r in range(3):
                needed = 5 - row_counts[r] - combo.count(r)
                if needed < 0:
                    valid = False
                    break

        if not valid:
            continue

        # Apply
        for r in combo:
            row_counts[r] += 1
        assignments[col] = list(combo)

        if _assign_rows(col_order, idx + 1, col_numbers, assignments, row_counts):
            return True

        # Undo
        for r in combo:
            row_counts[r] -= 1
        assignments[col] = []

    return False


def generate_unique_cards(count: int) -> list[list[list[int | None]]]:
    """Generate the specified number of unique cards."""
    cards: list[list[list[int | None]]] = []
    seen: set[frozenset[int]] = set()

    while len(cards) < count:
        card = generate_card()
        numbers = frozenset(
            cell for row in card for cell in row if cell is not None
        )
        if numbers not in seen:
            seen.add(numbers)
            cards.append(card)

    return cards
