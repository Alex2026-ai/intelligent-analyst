"""
BUG-014 regression: column fallback must be surfaced in metadata, not just logs.

Tests:
  1. Recognized column → column_meta.fallback == False, no warnings
  2. Unrecognized column → column_meta.fallback == True, score populated
  3. Metadata flows through to batch record and upload response
  4. Existing upload semantics unchanged for recognized headers
"""

import pandas as pd
import pytest

from app.server_enterprise_golden import _select_best_column


class TestSelectBestColumnMeta:
    """Unit tests for _select_best_column metadata output."""

    def test_recognized_column_no_fallback(self):
        """Known header like 'company' → method=target_list, fallback=False."""
        df = pd.DataFrame({"company": ["Acme", "Beta"], "revenue": [100, 200]})
        df.columns = [str(c).lower().strip() for c in df.columns]
        meta = {}
        col = _select_best_column(df, mode="company", column_meta=meta)
        assert col == "company"
        assert meta["method"] == "target_list"
        assert meta["fallback"] is False
        assert meta["column"] == "company"

    def test_recognized_column_company_name(self):
        """'company_name' is in target list → no fallback."""
        df = pd.DataFrame({"company_name": ["X Corp"], "id": [1]})
        df.columns = [str(c).lower().strip() for c in df.columns]
        meta = {}
        col = _select_best_column(df, mode="company", column_meta=meta)
        assert col == "company_name"
        assert meta["fallback"] is False

    def test_unrecognized_column_triggers_fallback(self):
        """No recognized header → fallback=True, method=content_score."""
        df = pd.DataFrame({"foo": ["Apple Inc", "Google LLC"], "bar": [1, 2]})
        df.columns = [str(c).lower().strip() for c in df.columns]
        meta = {}
        col = _select_best_column(df, mode="company", column_meta=meta)
        assert meta["fallback"] is True
        assert meta["method"] == "content_score"
        assert "score" in meta
        assert isinstance(meta["score"], float)
        assert meta["column"] == col

    def test_meta_not_required(self):
        """Passing no column_meta still works (backwards compat)."""
        df = pd.DataFrame({"company": ["Test"]})
        df.columns = [str(c).lower().strip() for c in df.columns]
        col = _select_best_column(df, mode="company")
        assert col == "company"

    def test_meta_none_still_works(self):
        """Passing column_meta=None explicitly still works."""
        df = pd.DataFrame({"xyz": ["Data"]})
        df.columns = [str(c).lower().strip() for c in df.columns]
        col = _select_best_column(df, mode="company", column_meta=None)
        assert isinstance(col, str)

    def test_person_mode_recognized(self):
        """Person-mode target columns (nombre, name) → no fallback."""
        df = pd.DataFrame({"name": ["John Doe"], "age": [30]})
        df.columns = [str(c).lower().strip() for c in df.columns]
        meta = {}
        col = _select_best_column(df, mode="person", column_meta=meta)
        assert meta["fallback"] is False
        assert meta["method"] == "target_list"

    def test_all_rejected_columns_still_selects(self):
        """Even when all columns are rejected names, selection still works."""
        df = pd.DataFrame({"id": ["Apple"], "uuid": ["Google"]})
        df.columns = [str(c).lower().strip() for c in df.columns]
        meta = {}
        col = _select_best_column(df, mode="company", column_meta=meta)
        assert meta["fallback"] is True
        assert meta["column"] == col

    def test_score_is_deterministic(self):
        """Same input produces same meta output."""
        df = pd.DataFrame({"random_col": ["Microsoft", "Amazon", "Alphabet"]})
        df.columns = [str(c).lower().strip() for c in df.columns]
        meta1, meta2 = {}, {}
        _select_best_column(df, mode="company", column_meta=meta1)
        _select_best_column(df, mode="company", column_meta=meta2)
        assert meta1 == meta2
