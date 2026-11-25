# AGENTS.md

## Repository Overview

- Dataset-only repository for the BizHack AI Marketing Hackathon (`data/series-1` through `data/series-5`). There is currently no application code, package manifest, linter, or test suite.
- Do not rely solely on `data/series-*/README.md` for CSV parsing: column names, data types, units, and timestamp formats in the actual `data.csv` files differ from the README descriptions.

## CSV Parsing & Data Quirks (`data/series-*/data.csv`)

- **Encodings:** `series-1` and `series-2` are **UTF-16 LE with BOM** (`\xff\xfe`); open with `encoding="utf-16"` (default UTF-8 readers and plain text tools treat them as binary). `series-3`, `series-4`, and `series-5` are **UTF-8**. All five use CRLF line endings.
- **Headers & empty fields:**
  - Headers are capitalized (`"Timestamp","Flow"`), not lowercase as written in the READMEs.
  - `series-1` has an unquoted header with a trailing comma (`Timestamp,Flow,Subflow,`), producing an empty 4th column on every row, plus 2 empty `Subflow` values.
- **Flow values & units:**
  - All series store flow as unit-suffixed strings rather than bare integers (even where READMEs specify `Integer`): `l` (`series-1`), `L` (`series-2`, `series-5`), and mixed `L` / `mL` (`series-3`, `series-4`, with decimals in `series-4`).
  - Values are **already scaled** into liters/milliliters by the flowmeter pulse factor `k` noted in the READMEs (e.g., `series-1` uses `10 l` steps for `k = 10 l/pulse`, `series-5` uses `100 L` steps for `k = 100 l/pulse`). Parse the unit (`l`/`L` vs `mL`) to normalize to liters; do not multiply by `k` again.
- **Timestamps & sampling intervals:**
  - All series use synthetic dates starting `01.01.2000` (`DD.MM.YYYY`).
  - `series-1`: `DD.MM.YYYY H:MM` (no seconds, single-digit unpadded hours like `0:01`), 60 s steps (`01.01`–`04.01.2000`).
  - `series-2`: `DD.MM.YYYY HH:MM:SS` with **irregular intervals** (40–79 s steps, `01.01`–`05.01.2000`).
  - `series-3`: regular 60 s steps (`01.01`–`05.01.2000`).
  - `series-4` (`01.01`–`10.01.2000`) and `series-5` (`01.01`–`07.01.2000`): 60 s nominal steps with occasional 120 s gaps (missing minutes).
