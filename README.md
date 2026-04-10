# Russian Loto

Generator for Russian Loto cards. Outputs to PDF (for paper printing) or STL (for 3D printing). Includes a small local web server for running a live game from your phone, so you can verify on the spot whether a player's claimed line or bingo is real.

Each generated card is registered locally so you never get duplicates across print runs. The exact row layout of every card is stored alongside its numbers, which means reprints, STL re-renders, and the live game UI all match the physical card you originally printed.

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
loto gen -t pdf -n 6
loto gen -t pdf -n 4 -o my_cards.pdf
```

Generates cards as a PDF file (A4 landscape, 2 cards per page with cut line).

### Generate STL cards for 3D printing

```bash
loto gen -t stl -n 6                # inlay mode (default)
loto gen -t stl -n 6 --raised       # raised mode
loto gen -t stl -n 2 --no-seq       # without card number on sides
loto gen -t stl -n 2 -d my_stl_dir
```

Two STL styles are available:

**Inlay (default)** -- numbers, grid, and frame are engraved into the base plate. Print face-down on a textured build plate for a smooth, professional finish. Each card produces:

- `card_001_a3f1b7c2_base.stl` -- plate with engraved grooves (white/light color)
- `card_001_a3f1b7c2_inlay.stl` -- insert that fills the grooves (black/dark color)

**Raised** (`--raised`) -- numbers, grid, and frame protrude above the base plate. Each card produces:

- `card_001_a3f1b7c2_base.stl` -- flat plate (white/light color)
- `card_001_a3f1b7c2_overlay.stl` -- grid lines + numbers (black/dark color)

Load both files into your slicer (PrusaSlicer, Bambu Studio, Cura), align them, and assign different materials.

By default, the card's sequential number is printed on both sides of the outer frame. Use `--no-seq` to disable this.

Card dimensions: 230 x 90 x 1.5 mm base.

### List printed cards

```bash
loto ls
```

```
Printed cards (6):
  #001  stl,pdf  b4238332  [3,9,15,22,31,38,47,55,62,68,71,76,80,85,90]
  #002  stl      b64c4fd4  [1,12,24,33,40,49,53,61,70,74,82,86,...]
  ...
```

Shows all registered cards with sequential number, formats, hash ID, and the numbers on the card.

### Show a card in the terminal

```bash
loto show --seq 1                # by sequential number
loto show --id b4238332          # by hash ID
```

Prints the card's stored layout as a box-drawing grid, with single-digit numbers padded so columns align and empty cells left blank. Useful for sanity-checking against a physical card or quickly inspecting what will go to print before running `reprint`.

```
#001  b4238332  [stl,pdf]
┌────┬────┬────┬────┬────┬────┬────┬────┬────┐
│    │ 11 │ 24 │ 34 │    │    │ 61 │    │ 82 │
├────┼────┼────┼────┼────┼────┼────┼────┼────┤
│    │    │ 25 │ 39 │ 42 │ 54 │    │ 75 │    │
├────┼────┼────┼────┼────┼────┼────┼────┼────┤
│  3 │ 12 │ 27 │    │ 45 │    │    │    │ 88 │
└────┴────┴────┴────┴────┴────┴────┴────┴────┘
```

If the card is a legacy entry without a stored layout, `show` refuses to render and points you at `loto fix-rows --seq N`.

### Reprint a card in another format

```bash
loto reprint --seq 1 -t pdf              # by sequential number
loto reprint --id aa7c4b83 -t stl        # by hash ID
loto reprint --seq 5 -t stl -d my_dir    # custom output directory
loto reprint --seq 1 -t stl --force      # regenerate even if already printed
```

Renders an existing card in the target format, using the row layout that was stored when the card was first generated. The format is added to the card's registry entry. Useful when you printed PDF cards for a game and later want to 3D-print specific ones -- the STL will match the PDF cell-for-cell because both come from the same stored layout.

If the card was already printed in the requested format, use `--force` to regenerate anyway.

If the card is a legacy entry (registered before row storage was added) and has no stored layout, `reprint` refuses to run and points you at `loto fix-rows --seq N` to assign the layout from the original physical card first. See "Fix legacy card layouts" below.

### Run a live game from your phone

```bash
loto serve                       # default: 0.0.0.0:8000
loto serve --port 9000           # custom port
loto serve --host 127.0.0.1      # loopback only (no LAN access)
```

Starts a small local web server on your laptop, prints both the loopback URL and the LAN URL, and serves a single HTML page with all registered cards baked in. Open the LAN URL on your phone (your phone and laptop must be on the same Wi-Fi) and you get a tap-friendly verification UI:

- A `9 x 11` grid of buttons covering numbers `1..90`, laid out by Russian Loto column structure (column 1 is `1..9`, column 2 is `10..19`, ..., column 9 is `80..90`). Tap a number when the caller announces it. Tap an already-marked number to un-mark it (with confirmation, since this can rewind game state).
- A live event log under the grid. When any registered card crosses a win threshold (first line, two lines, full bingo) the event appears at the top of the log with a timestamp and the card's seq number.
- Tap any log entry to open a bottom sheet showing that card's full `3 x 9` grid with marked cells highlighted, so you can visually confirm whether the player's physical card actually matches the claim.
- Game state lives in the browser's `localStorage`, so accidental refreshes, screen-off, or even server restarts do not lose the game. Use the "Новая игра" button (with confirmation) to start fresh.

The server holds no game state of its own. It is a one-shot HTML delivery mechanism; all logic runs in the browser. Stop it with `Ctrl-C`.

Cards without a stored row layout (legacy entries from before the rows feature) are automatically excluded from the live game UI and listed in the startup banner with a hint to run `loto fix-rows --seq N` for each.

#### Password protection

```bash
loto serve --auth                 # random 6-digit code
loto serve --auth-code 4242       # specific code
```

Adds HTTP Basic auth to the page. When `--auth` is set without a value, a fresh 6-digit code is generated on each start and printed in the banner:

```
Russian Loto game server
  Cards in game: 50
  Auth code: 384715   (enter as password; username can be anything)
  Local:   http://127.0.0.1:8000
  Network: http://192.168.1.42:8000   <- open this on your phone
```

When you open the URL on your phone, the browser shows its native password prompt. Enter the code as the password (any value, including empty, works as username). Browsers remember Basic auth credentials per origin, so you only type the code once per device until the next server restart. Use `--auth-code` if you want a stable code across restarts so you do not have to re-login.

The code is a cryptographically random 6-digit number (10⁶ combinations). It is not bank-grade security -- it is enough to keep casual observers out, especially when you expose the server publicly via a tunnel (see below).

#### Exposing the server over the internet

If you want to reach the game from outside your local network (for example, playing with remote friends, or avoiding flaky Wi-Fi), the simplest path is `cloudflared tunnel --url http://localhost:8000` running alongside `loto serve`. It gives you a temporary `*.trycloudflare.com` URL tunneled to your local server. No code changes, no Cloudflare account, no deploy process. Combine it with `--auth` so the public URL is not viewable by anyone who stumbles across it.

### Generate without registering

```bash
loto gen -t stl -n 2 --no-register
```

Useful for test prints. Cards won't be saved to the registry, so the same combinations may appear again.

### Fix legacy card layouts

```bash
loto fix-rows --seq 1
```

Interactively enter the row layout for a registered card that has no stored layout (a "legacy" entry from before row storage was added). The command shows you the card's stored numbers and prompts for each of the three rows; once saved, the card joins the live game UI and can be reprinted.

Each row is entered as 9 cells separated by spaces. Empty cells are typed as `_` (other accepted markers: `.`, `-`, `0`, `null`). For the example card `#001` with numbers `[3, 11, 12, 24, 25, 27, 34, 39, 42, 45, 54, 61, 75, 82, 88]`:

```
Row 1: _ 11 24 34 _ _ 61 _ 82
Row 2: _ _ 25 39 42 54 _ 75 _
Row 3: 3 12 27 _ 45 _ _ _ 88
```

Validation is strict: exactly 5 filled cells per row, all 15 stored numbers must appear, every number must be in the column matching its range, no duplicates, and numbers in the same column must appear top-to-bottom in ascending order. If anything is off you get a clear error and nothing is written.

You only need to run this for cards that were registered before the rows feature existed. New cards from `loto gen` always have their layout stored automatically.

### Remove cards from the registry

```bash
loto rm 5             # one card by seq
loto rm 5-50          # contiguous range
loto rm 3,7,9         # comma-separated list
loto rm 3,5-7,10      # mix of range and list
loto rm 5-50 --force  # skip the confirmation prompt
```

Deletes registry entries by sequential number. By default the command shows what it is about to delete and waits for explicit confirmation. It does **not** delete any rendered PDF or STL files on disk -- only the registry records.

A common workflow: regenerate a contiguous range of cards in place. After `loto rm 5-50`, the next `loto gen` calls will assign seq numbers starting from 5 again, because `_next_seq()` returns `max(seq) + 1`.

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

Each entry tracks:

- `seq` -- sequential number assigned at first registration (`#001`, `#002`, ...)
- `numbers` -- the 15 sorted numbers, the canonical identity of the card
- `rows` -- the original `3 x 9` row layout, with `null` for empty cells
- `formats` -- list of formats this card was printed in (e.g. `["stl"]`, `["pdf"]`, or `["stl", "pdf"]`)
- `printed_at` -- ISO date of first registration

The `rows` field is the source of truth for the physical layout of the card. It is populated automatically when `loto gen` registers a new card and never overwritten by later re-registrations (so adding STL to a card that was first printed as PDF keeps the original layout). Storing rows is what makes reprints, STL re-renders, and the live game UI all match the physical card you originally printed -- without it, the layout would have to be re-derived from numbers, which is non-unique and would silently disagree with what is actually on the paper.

The same card can exist in multiple formats without duplication: `is_printed(cid, fmt)` is format-aware, so a card already printed as PDF can still be generated as STL using the same stored layout.

On each generation run the tool:

1. Generates random valid cards
2. Checks each against the registry for the requested format, skipping duplicates
3. Assigns sequential numbers
4. Saves the card with its row layout to the registry

Legacy entries (created before row storage existed) have `rows: null`. They still work for `ls` and remain identified by their `cid`, but `serve` excludes them from the live game UI and `reprint` refuses to render them until you assign a layout via `loto fix-rows`.

### STL model structure

Each card is two STL files for multi-material printing:

- **Inlay mode** (default) -- base has engraved grooves; inlay insert fills them flush. Print face-down for smooth surface from the build plate.
- **Raised mode** -- base is flat; overlay with numbers and grid sits on top.

Both modes include a double border frame (thick outer + thin inner with gap) and grid lines between cells. All geometry is built with [CadQuery](https://cadquery.readthedocs.io/).

## Project structure

```
src/russian_loto/
    card.py             -- card generation logic
    cli.py              -- CLI entry point (gen, ls, show, reprint, serve, fix-rows, rm)
    constants.py        -- shared grid constants and column ranges
    registry.py         -- printed card registry (JSON file with row layouts)
    render.py           -- PDF rendering with Pillow
    render_stl.py       -- STL rendering with CadQuery
    serve.py            -- live game web server (stdlib http.server)
    templates/
        game.html       -- single-page UI for the live game (HTML + inline CSS/JS)
tests/
    conftest.py         -- test isolation (redirects registry to temp file)
    test_card.py        -- card generation tests
    test_registry.py    -- registry tests (rows storage, delete, migration)
    test_render_stl.py  -- STL geometry tests
    test_serve.py       -- web server tests (payload building, handler, skipped legacy)
    test_cli_helpers.py -- pure-function tests for CLI parsers (seq range, row input)
bin/
    loto                -- shell wrapper for uv run loto
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
