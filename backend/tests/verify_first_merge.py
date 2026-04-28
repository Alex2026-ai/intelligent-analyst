#!/usr/bin/env python3
"""
First Merge Verification — proves 3 routing outcomes with actual metadata.

Run:  cd backend && python3 tests/verify_first_merge.py
"""
from __future__ import annotations

import io
import json
import sys
from unittest.mock import patch

import pandas as pd

from app.dataset_router import inspect_dataset


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _print_meta(result: dict, requested_mode: str = "auto") -> dict:
    """Print the routing metadata subset required by the verification spec."""
    out = {
        "requested_mode": requested_mode,
        "effective_mode": result["effective_mode"],
        "routing_decision": result["routing_decision"],
        "routing_reason": result["routing_reason"],
        "dataset_type": result["dataset_type"],
        "classifier_label": result.get("classifier_label"),
        "classifier_confidence": result.get("classifier_confidence"),
        "fallback_used": result["fallback_used"],
    }
    print(json.dumps(out, indent=2))
    return out


# ============================================================================
# CASE 1 — Person dataset (frank-style HR)
# ============================================================================

def verify_case_1() -> bool:
    print("=" * 70)
    print("VERIFICATION CASE 1 — Person dataset (frank-style HR)")
    print("=" * 70)
    print()
    print("Input: 100-row HR spreadsheet with Spanish headers")
    print("  Headers: Nombre, Primer Apellido, Segundo Apellido, Edad, Sexo,")
    print("           Departamento, Posicion")
    print()

    df = pd.DataFrame({
        "Nombre": ["Frank", "Maria", "Jose", "Ana", "Carlos",
                   "Luis", "Rosa", "Pedro", "Sofia", "Diego"] * 10,
        "Primer Apellido": ["Garcia", "Lopez", "Martinez", "Hernandez", "Gonzalez",
                            "Rodriguez", "Perez", "Sanchez", "Ramirez", "Torres"] * 10,
        "Segundo Apellido": ["Escobedo", "Reyes", "Cruz", "Flores", "Rivera",
                             "Gomez", "Diaz", "Morales", "Jimenez", "Ruiz"] * 10,
        "Edad": [35, 28, 42, 31, 45, 38, 29, 50, 33, 27] * 10,
        "Sexo": ["M", "F", "M", "F", "M", "M", "F", "M", "F", "M"] * 10,
        "Departamento": ["Engineering", "Sales", "HR", "Finance", "Ops",
                         "Marketing", "Legal", "IT", "Support", "R&D"] * 10,
        "Posicion": ["Manager", "Analyst", "Director", "Specialist", "Lead",
                     "VP", "Coordinator", "Engineer", "Advisor", "Intern"] * 10,
    })

    result = inspect_dataset(_csv_bytes(df), "frank-1.csv")
    print("Returned metadata:")
    meta = _print_meta(result)
    print()

    ok = True
    if meta["effective_mode"] != "mixed":
        print(f"  FAIL: effective_mode={meta['effective_mode']}, expected mixed")
        ok = False
    if meta["effective_mode"] == "reject":
        print("  FAIL: person dataset must NEVER be rejected")
        ok = False

    status = "PASS" if ok else "FAIL"
    print(f"  Result: {status}")
    print(f"  Path: resolve_mixed_sync() → Sanitize + Attest")
    print()
    return ok


# ============================================================================
# CASE 2 — Organization dataset
# ============================================================================

def verify_case_2() -> bool:
    print("=" * 70)
    print("VERIFICATION CASE 2 — Organization dataset")
    print("=" * 70)
    print()
    print("Input: 100-row company list with Company Name header")
    print("  Headers: Company Name, Industry, Revenue")
    print()

    df = pd.DataFrame({
        "Company Name": [
            "Apple Inc", "Google LLC", "Microsoft Corporation",
            "Amazon.com Inc", "Meta Platforms Inc",
            "Goldman Sachs Group Inc", "JPMorgan Chase & Co",
            "Pfizer Inc", "Tesla Inc", "Boeing Company",
        ] * 10,
        "Industry": ["Tech", "Tech", "Tech", "Retail", "Social",
                      "Finance", "Finance", "Pharma", "Auto", "Aerospace"] * 10,
        "Revenue": [394000, 283000, 198000, 514000, 117000,
                    47000, 128000, 81000, 54000, 66000] * 10,
    })

    result = inspect_dataset(_csv_bytes(df), "companies.csv")
    print("Returned metadata:")
    meta = _print_meta(result)
    print()

    ok = True
    if meta["effective_mode"] != "company":
        print(f"  FAIL: effective_mode={meta['effective_mode']}, expected company")
        ok = False

    status = "PASS" if ok else "FAIL"
    print(f"  Result: {status}")
    print(f"  Path: resolve_entity_sync() → Waterfall (L0-L4)")
    print()
    return ok


# ============================================================================
# CASE 3 — Low-confidence fallback
# ============================================================================

def verify_case_3() -> bool:
    print("=" * 70)
    print("VERIFICATION CASE 3 — Low-confidence fallback")
    print("=" * 70)
    print()
    print("Input: Person dataset with classifier forced to return low confidence")
    print("  Simulates: model returns garbage@0.45 — router must override via heuristics")
    print()

    df = pd.DataFrame({
        "Nombre": ["Frank", "Maria", "Jose", "Ana", "Carlos"] * 20,
        "Primer Apellido": ["Garcia", "Lopez", "Martinez", "Hernandez", "Gonzalez"] * 20,
        "Edad": [35, 28, 42, 31, 45] * 20,
    })

    with patch("app.dataset_router.classify_dataset") as mock_clf:
        mock_clf.return_value = {"label": "garbage", "confidence": 0.45}
        result = inspect_dataset(_csv_bytes(df), "ambiguous.csv")

    print("Returned metadata:")
    meta = _print_meta(result)
    print()

    ok = True
    if meta["fallback_used"] is not True:
        print(f"  FAIL: fallback_used={meta['fallback_used']}, expected True")
        ok = False
    if meta["effective_mode"] != "mixed":
        print(f"  FAIL: effective_mode={meta['effective_mode']}, expected mixed")
        ok = False
    if meta["effective_mode"] == "reject":
        print("  FAIL: low-confidence garbage must NOT reject a person dataset")
        ok = False

    status = "PASS" if ok else "FAIL"
    print(f"  Result: {status}")
    print(f"  Path: classifier confidence 0.45 < 0.70 threshold → heuristic fallback")
    print()
    return ok


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    results = []
    results.append(verify_case_1())
    results.append(verify_case_2())
    results.append(verify_case_3())

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for i, passed in enumerate(results, 1):
        print(f"  Case {i}: {'PASS' if passed else 'FAIL'}")

    all_pass = all(results)
    print()
    print(f"  Overall: {'PASS' if all_pass else 'FAIL'}")
    print()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
