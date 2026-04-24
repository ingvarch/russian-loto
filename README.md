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
loto gen -t pdf -n 4 --no-seq    # without the "№ NNN" label on sides
```

Generates cards as a PDF file. Each card is exactly 230 x 90 mm (same physical footprint as the STL card) and visually identical to it: double frame, 3 x 9 grid with bold numbers, and the card's sequential number printed vertically on both sides of the outer frame. Pages are A4 landscape with two cards stacked flush against each other, and dashed cut marks are drawn around every card so you can cut them out with scissors (5 cuts per page get both cards out cleanly).

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

### Print a card holder

A standalone helper at `scripts/generate_box.py` produces an STL of a corner-bracket holder for the printed card stack. It is a flat base plate with four vertical L-shaped corner posts and a low perimeter rail that ties the corners into a rigid frame. There are no full walls -- only the corners stick up, so the stack is visible and easy to grab. The script is intentionally kept outside the main `loto` CLI and has no dependency on the registry.

```bash
uv run python scripts/generate_box.py                       # 30 cards, stl_output/card_holder.stl
uv run python scripts/generate_box.py --cards 40            # taller posts for ~40 cards
uv run python scripts/generate_box.py --height 70 -o h.stl  # explicit post height
uv run python scripts/generate_box.py --rail-height 0       # corners only, no perimeter rail
uv run python scripts/generate_box.py --tolerance 1.5       # looser fit if your printer runs hot
```

Defaults are tuned for a 230 x 90 mm card with 1 mm clearance per side, 2.5 mm wall thickness, 25 mm corner legs, a 4 mm perimeter rail, and post height sized to fit a 30-card stack plus 5 mm headroom. Every parameter is overridable via CLI flags (`--tolerance`, `--wall`, `--corner-length`, `--base-thickness`, `--rail-height`). The output is a single STL ready to slice -- no multi-material setup needed.

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
loto reprint --seq 1 -t pdf                    # one card by seq
loto reprint --id aa7c4b83 -t stl              # one card by hash ID
loto reprint --seq 51-100 -t pdf -o bulk.pdf   # contiguous range (all into one PDF)
loto reprint --seq 3,7,9 -t pdf                # comma-separated list
loto reprint --seq 3,5-7,10 -t pdf             # mix of list and range
loto reprint --seq 5 -t stl -d my_dir          # custom STL output directory
loto reprint --seq 51-100 -t pdf --force       # regenerate even if already printed
```

Renders existing cards in the target format, using the row layouts that were stored when the cards were first generated. The format is added to each card's registry entry. Useful when you printed PDF cards for a game and later want to 3D-print specific ones -- the STL will match the PDF cell-for-cell because both come from the same stored layout.

`--seq` accepts the same grammar as `loto rm`: a single number, a dash-range, a comma-separated list, or any mix. When multiple cards are selected, PDF runs bundle them into one multi-page file (`-o bulk.pdf`) and STL runs drop all generated files into the same `--output-dir`.

If any requested seq is not in the registry, `reprint` reports the skipped numbers and continues with the rest. If a card was already printed in the requested format it is skipped silently until you pass `--force`. If a card is a legacy entry (registered before row storage was added) and has no stored layout, `reprint` refuses to run the entire batch and points you at `loto fix-rows --seq N` to assign the layout from the original physical card first. See "Fix legacy card layouts" below.

### Run a live game from your phone

```bash
loto serve                       # default: 0.0.0.0:8000
loto serve --port 9000           # custom port
loto serve --host 127.0.0.1      # loopback only (no LAN access)
```

Starts a local web server on your laptop and prints URLs for both the admin page and the read-only display page. Open the admin URL on your phone (same Wi-Fi as your laptop) and the display URL on a TV or projector for players to watch.

**Admin page** (`/`) -- the host's control surface:

- A `9 x 11` grid of buttons covering numbers `1..90`, laid out by Russian Loto column structure (column 1 is `1..9`, column 2 is `10..19`, ..., column 9 is `80..90`). Tap a number when the caller announces it. Tap an already-marked number to un-mark it (with confirmation, since this can rewind game state).
- When any registered card crosses a win threshold (first line, two lines, full bingo) the admin sees a confirmation dialog: "confirm" means the card is present and the player is claiming the win; "not in play" means the card is not physically in the game (the crossing is logged but does not count as a winner). This prevents phantom wins from cards that were printed but not distributed.
- A live event log under the grid. Tap any log entry to open a bottom sheet showing that card's full `3 x 9` grid with marked cells highlighted, so you can visually confirm whether the player's physical card actually matches the claim.
- Game state lives in the browser's `localStorage`, so accidental refreshes, screen-off, or even server restarts do not lose the game. Use the "Новая игра" button (with confirmation) to start fresh.

**Display page** (`/display`) -- read-only screen for players:

- A large `9 x 11` grid showing all called numbers, optimized for TV/projector (forced dark theme, large fonts).
- "4 из 5 в линии" sidebar: shows how many cards are one number away from closing each level (one line / two lines / full bingo). Updates in real time as numbers are called.
- Winners sidebar: shows the seq number of the first confirmed winner at each level, or a dash if the level has not been won yet.

The display page receives live state from the admin via Server-Sent Events (SSE). Every time the admin marks or unmarks a number, confirms or rejects a line closure, the state is pushed to the server and broadcast to all connected display clients instantly. The display auto-reconnects on network drops (2-second backoff).

The server holds the latest game snapshot in memory so a display opened mid-game rehydrates immediately, but the admin's browser remains the source of truth. Stop the server with `Ctrl-C`.

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

`trycloudflare.com` is frequently present on phishing blocklists (ad blockers, family DNS, corporate DNS), so you may see `ERR_NAME_NOT_RESOLVED` on the phone. If that happens, switch the phone's DNS to `1.1.1.1` or use a named tunnel on your own domain instead: create a tunnel with `cloudflared tunnel create loto`, route DNS with `cloudflared tunnel route dns loto loto.yourdomain.com`, put a matching `~/.cloudflared/config.yml` in place, and run `cloudflared tunnel run`.

#### One-command combined runner

`bin/loto-game` starts both `loto serve` and `cloudflared tunnel run` in one terminal and takes them both down cleanly on Ctrl+C. It hardcodes `--port 8765` to match the named-tunnel `config.yml` shipped in the author's setup; change both sides if you use a different port. Any extra arguments are forwarded to `loto serve`:

```bash
bin/loto-game --auth-code 4242
```

Under the hood it calls `.venv/bin/loto` directly (skipping `uv run`, which does not forward signals to its child process), so you need `uv sync` to have been run at least once.

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
    card_geometry.py    -- mm-level card dimensions shared by PDF and STL renderers
    cli.py              -- CLI entry point (gen, ls, show, reprint, serve, fix-rows, rm)
    constants.py        -- shared grid constants and column ranges
    registry.py         -- printed card registry (JSON file with row layouts)
    render.py           -- PDF rendering with Pillow (1:1 visual match with STL)
    render_stl.py       -- STL rendering with CadQuery
    web/
        __init__.py     -- re-exports: serve, parse_cards_range, generate_auth_code
        server.py       -- HTTP server, router, auth, static-file handler, SSE endpoint
        payload.py      -- cards payload builder, range parser, template renderer
        state_store.py  -- thread-safe in-memory state with pub/sub for SSE
        templates/
            game.html   -- admin page shell (markup + module script refs)
            display.html -- read-only display page for TV/projector
        static/
            css/
                base.css    -- theme tokens and reset (shared across pages)
                game.css    -- admin page styles
                display.css -- display page styles (forced dark theme)
            js/
                logic.js        -- pure functions (levels, close counts, payouts)
                state.js        -- game state shape, persistence, mutators
                ui.js           -- admin page DOM rendering and event wiring
                main-game.js    -- admin page bootstrap
                display-ui.js   -- display page DOM rendering (9x11 grid, sidebar)
                main-display.js -- display page bootstrap + SSE connection
scripts/
    generate_box.py     -- standalone STL generator for the corner-bracket card holder
tests/
    conftest.py         -- test isolation (redirects registry to temp file)
    test_card.py        -- card generation tests
    test_registry.py    -- registry tests (rows storage, delete, migration)
    test_render_pdf.py  -- PDF geometry + crop-mark tests
    test_render_stl.py  -- STL geometry tests
    test_generate_box.py -- card holder geometry tests (slow, builds CadQuery solids)
    test_serve.py       -- web server tests (payload, handler, static files, auth)
    test_state_store.py -- StateStore unit tests (get/set, pub/sub, thread safety)
    test_state_api.py   -- /api/state GET/POST integration tests
    test_sse_display.py -- SSE /api/events and /display page integration tests
    test_cli_helpers.py -- pure-function tests for CLI parsers (seq range, row input)
    test_cli_reprint.py -- end-to-end tests for `loto reprint` (range support, registry updates)
    js/
        logic.test.mjs  -- JS unit tests for logic.js (Node 20+, zero deps)
bin/
    loto                -- shell wrapper for uv run loto
    loto-game           -- starts loto serve + cloudflared tunnel run together
```

## Running tests

```bash
uv run pytest                          # all tests (includes node --test wrapper)
uv run pytest tests/test_card.py       # fast: card logic only
uv run pytest tests/test_registry.py   # fast: registry only
uv run pytest tests/test_render_stl.py # slow: builds 3D geometry
node --test tests/js/                  # JS unit tests (Node 20+, zero deps)
```

## License

MIT
