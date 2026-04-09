# Russian Loto

Generator for Russian Loto cards. Outputs to PDF (for paper printing) or STL (for 3D printing).

Each generated card is registered locally so you never get duplicates across print runs.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- [direnv](https://direnv.net/) (optional, for `loto` shortcut)

## Setup

```bash
git clone <repo-url> && cd russian-loto
uv sync
```

If you have direnv:

```bash
direnv allow
```

After that `loto` command is available directly in the project directory.
Without direnv, use `uv run loto` instead.

## Usage

### Generate PDF cards

```bash
loto gen -n 6
loto gen -n 4 -o my_cards.pdf
```

Generates cards as a PDF file (A4 landscape, 2 cards per page with cut line).

### Generate STL cards for 3D printing

```bash
loto gen --stl -n 6
loto gen --stl -n 2 -d my_stl_dir
```

Each card produces two files:

- `card_001_a3f1b7c2_base.stl` -- flat plate, print in white/light color
- `card_001_a3f1b7c2_overlay.stl` -- grid lines + numbers, print in black/dark color

Load both into your slicer (PrusaSlicer, Bambu Studio, Cura), align them, and assign different materials.

Card dimensions: 230 x 90 x 2.1 mm (1.5 mm base + 0.6 mm raised numbers).

### List printed cards

```bash
loto ls
```

```
Printed cards (6):
  #001  b4238332  [3,9,15,22,31,38,47,55,62,68,71,76,80,85,90]
  #002  b64c4fd4  [1,12,24,33,40,49,53,61,70,74,82,86,...]
  ...
```

Shows all registered cards with sequential number, hash ID, and the numbers on the card.

### Generate without registering

```bash
loto gen --stl -n 2 --no-register
```

Useful for test prints. Cards won't be saved to the registry, so the same combinations may appear again.

## How it works

### Card generation

Each card is a 3x9 grid following standard Russian Loto rules:

- 3 rows, 9 columns
- Each row has exactly 5 numbers and 4 empty cells
- Column 0: numbers 1-9, column 1: 10-19, ..., column 8: 80-90
- Numbers are sorted top-to-bottom within each column
- All 15 numbers on a card are unique

### Card registry

Every generated card gets a stable ID -- first 8 characters of SHA-256 hash computed from its sorted numbers. The registry is stored at `~/.russian-loto/printed.json`.

On each generation run the tool:

1. Generates random valid cards
2. Checks each against the registry, skipping duplicates
3. Assigns sequential numbers (#001, #002, ...)
4. Saves to registry after successful generation

### STL model structure

The 3D model has two parts for multi-material printing:

- **Base** -- flat rectangular plate
- **Overlay** -- double border frame (thick outer + thin inner with gap), grid lines between cells, and embossed numbers

All geometry is built with [CadQuery](https://cadquery.readthedocs.io/).

## Project structure

```
src/russian_loto/
    card.py         -- card generation logic
    cli.py          -- CLI entry point (subcommands: generate, list)
    registry.py     -- printed card registry (JSON file)
    render.py       -- PDF rendering with Pillow
    render_stl.py   -- STL rendering with CadQuery
tests/
    conftest.py     -- test isolation (redirects registry to temp file)
    test_card.py    -- card generation tests
    test_registry.py -- registry tests
    test_render_stl.py -- STL geometry tests
bin/
    loto            -- shell wrapper for uv run loto
```

## Running tests

```bash
uv run pytest                          # all tests
uv run pytest tests/test_card.py       # fast: card logic only
uv run pytest tests/test_registry.py   # fast: registry only
uv run pytest tests/test_render_stl.py # slow: builds 3D geometry
```

## License

MIT
