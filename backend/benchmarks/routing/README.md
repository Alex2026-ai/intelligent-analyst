# Routing Benchmark Suite v1.0.0

A comprehensive versioned dataset pack for measuring dataset routing accuracy on each release of the Intelligent Analyst backend.

## Overview

The routing benchmark suite validates the `inspect_dataset()` function from `app/dataset_router.py` across 17 diverse datasets covering:

- **Person datasets** (4 files): Spanish names, English names, mixed international, titled individuals
- **Organization datasets** (4 files): US companies, international companies, financial institutions, tech startups
- **Garbage datasets** (3 files): numeric-only data, placeholder values, injection attempts
- **Mixed datasets** (3 files): CRM exports, HR + vendor lists, ambiguous single-column data
- **Edge cases** (3 files): OCR-damaged text, single-column no headers, Unicode/special characters

## Running the Benchmark

```bash
# Basic usage
python3 scripts/run_routing_benchmark.py

# Verbose output (shows pass/fail per file)
python3 scripts/run_routing_benchmark.py --verbose

# Custom output directory
python3 scripts/run_routing_benchmark.py --output-dir=/my/custom/dir
```

## Exit Codes

- **0** — Overall accuracy >= 90% (PASS)
- **1** — Overall accuracy < 90% (FAIL)

## Output

Results are written to `benchmarks/routing/results/run_YYYYMMDD_HHMMSS.json` with:

- Overall accuracy and pass/fail counts
- Accuracy by category (person, org, garbage, mixed, edge_cases)
- Accuracy by metric (effective_mode, dataset_type, routing_decision)
- Per-file results with expected vs. actual routing decisions
- Sample failures (up to 10) for quick investigation

Example output structure:
```json
{
  "timestamp": "2026-03-16T01:14:21.236449Z",
  "version": "1.0.0",
  "total_files": 17,
  "passed": 17,
  "failed": 0,
  "overall_accuracy": 100.0,
  "results_by_category": {
    "person": {"passed": 4, "total": 4, "accuracy": 100.0},
    "org": {"passed": 4, "total": 4, "accuracy": 100.0},
    ...
  },
  "results_by_metric": {
    "effective_mode_match": {"passed": 17, "total": 17, "accuracy": 100.0},
    ...
  },
  "results_by_file": {...},
  "sample_failures": []
}
```

## Dataset Structure

### Files in `datasets/`

| Filename | Rows | Purpose |
|----------|------|---------|
| `person_spanish.csv` | 10 | Spanish person names with titles and departments |
| `person_english.csv` | 10 | English person names with employee metadata |
| `person_mixed_intl.csv` | 7 | International names (French, Japanese, German, Russian, Italian) |
| `person_titled.csv` | 7 | People with academic/professional titles (Dr., Prof.) |
| `org_us_companies.csv` | 10 | US technology and financial companies |
| `org_intl_companies.csv` | 9 | International industrial and tech companies |
| `org_financial_institutions.csv` | 8 | Banks and investment firms |
| `org_tech_startups.csv` | 8 | Venture-funded tech startups |
| `garbage_numeric_only.csv` | 15 | Pure numeric data with no text |
| `garbage_placeholders.csv` | 10 | NULL, N/A, TBD, and other placeholder values |
| `garbage_injection_attempts.csv` | 9 | SQL injection, XSS, and command injection payloads |
| `mixed_crm_export.csv` | 8 | CRM data with contact names and company names mixed |
| `mixed_hr_vendor.csv` | 9 | HR employee records mixed with vendor entities |
| `mixed_ambiguous_single.csv` | 10 | Single column with ambiguous person/company names |
| `edge_ocr_damaged.csv` | 8 | Text with OCR damage (numbers replacing letters) |
| `edge_single_column_no_header.csv` | 10 | Company names without a header row |
| `edge_unicode_special.csv` | 8 | Names and companies with Unicode and special chars |

### Expected Results in `expected_results.json`

Maps each filename to:
- `effective_mode`: "mixed", "company", or "reject"
- `dataset_type`: "PERSON", "COMPANY", "MIXED", or "INVALID"
- `routing_decision`: The heuristic or ML classifier path taken
- `category`: Benchmark category for grouping

## Integration with CI/CD

Add this to your release pipeline:

```bash
# Pre-release validation
python3 backend/scripts/run_routing_benchmark.py

if [ $? -ne 0 ]; then
  echo "Routing benchmark failed. Investigate before release."
  exit 1
fi
```

## Updating Benchmarks

To add new test datasets:

1. Create a new CSV file in `datasets/` with the pattern `{prefix}_{descriptor}.csv`
2. Add expected result to `expected_results.json` with the same filename
3. Run `python3 scripts/run_routing_benchmark.py --verbose` to verify
4. Update `manifest.json` version if making significant changes

## Model Dependency

The benchmark requires the ML classifier model at:
```
backend/models/entity_classifier.pkl
```

If the model is unavailable, the router falls back to heuristic rules. The benchmark will still pass as long as the routing decisions match expected results.

## Maintenance Notes

- Version 1.0.0 (2026-03-15): Baseline benchmark pack with 17 diverse datasets
- Baseline accuracy: 100% (all metrics)
- Typical pass rate: 90-100% depending on classifier model changes
- Future versions should expand edge cases based on production failures
