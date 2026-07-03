# Capability: File Ingestion

## What It Does

Accepts one uploaded CSV or Excel file, parses it locally into a working dataset, and extracts a compact schema/summary profile — without ever exposing raw row data outside the local process.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Uploaded file | binary (CSV / XLSX / XLS) | Browser file upload | Yes |
| Existing session (if any) | session identifier | Prior upload in the same server sitting | No — a new upload always starts a fresh session |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| `session_id` | string identifier | Returned to the browser; used on every subsequent question |
| Schema profile (columns, dtypes, row count, aggregates) | structured data | Returned to the browser for display; cached server-side for use by later questions |
| Warnings (skipped/malformed content) | list of strings | Returned to the browser for display |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| None | Parsing and profiling are 100% local (no network call, no LLM call) | N/A |

## Business Rules

- Only CSV, XLSX, and XLS files are accepted; any other file type is rejected outright with a clear error (not partially salvageable, unlike a corrupt file of the right type).
- A file that is the right type but has some corrupt/malformed rows is handled best-effort: the readable rows are parsed, and the skipped rows/content are reported back as warnings — never a hard rejection when something is salvageable.
- A file that is completely unreadable (e.g. a password-protected workbook with no accessible sheet) returns a clear failure — "best effort" does not mean fabricating data when literally nothing can be read.
- Exactly one file is active per session at any time. Uploading a new file replaces the previous session's data outright. This agent never joins, compares, or combines two files — permanently, not just in an early phase.
- The extracted schema/summary profile contains only aggregated/derived facts (column names, types, counts, distinct-value lists capped at 20 for low-cardinality columns, and numeric aggregates like min/max/mean) — it never contains an actual data row.
- All session data (the parsed dataset and its profile) lives only for the current server sitting; it is not written anywhere that would survive a restart, and the user is expected to re-upload after a restart.

## Success Criteria

- [ ] Uploading a well-formed CSV of a few MB returns a schema profile with the correct column count and row count.
- [ ] Uploading a CSV containing some malformed rows still succeeds, with a warning listing what was skipped and a schema profile reflecting the salvaged data.
- [ ] Uploading a file of an unsupported type (e.g. `.txt`, `.json`) is rejected with a clear, specific error.
- [ ] Uploading a second file in the same sitting fully replaces the first session's data — no trace of the first file's schema or data remains queryable afterward.
- [ ] The schema profile returned for a large fixture file never contains more than 20 sample values for any single column, and never contains a full data row.
