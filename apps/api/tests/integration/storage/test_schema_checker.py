"""Tests for schema version checker."""

from apps.api.src.storage.schema.version_checker import check_schema_versions


class TestSchemaChecker:
    def test_no_documents_passes(self, db):
        result = check_schema_versions(db, "t1")
        assert result.passed is True

    def test_matching_version_passes(self, db):
        db.collection("tenants/t1/resolutions").add({"_schema_version": 1}, "r1")
        result = check_schema_versions(db, "t1")
        assert result.passed is True

    def test_mismatched_version_fails(self, db):
        db.collection("tenants/t1/resolutions").add({"_schema_version": 99}, "r1")
        result = check_schema_versions(db, "t1")
        assert result.passed is False
        assert len(result.mismatches) == 1
        assert result.mismatches[0]["expected"] == 1
        assert result.mismatches[0]["actual"] == 99

    def test_missing_version_fails(self, db):
        db.collection("tenants/t1/resolutions").add({"some_field": "value"}, "r1")
        result = check_schema_versions(db, "t1")
        assert result.passed is False

    def test_mixed_versions(self, db):
        db.collection("tenants/t1/resolutions").add({"_schema_version": 1}, "r1")
        db.collection("tenants/t1/resolutions").add({"_schema_version": 2}, "r2")
        result = check_schema_versions(db, "t1")
        assert result.passed is False
        assert len(result.mismatches) == 1
