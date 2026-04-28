"""Tests for PII vault — request-scoped lifecycle."""

from apps.api.src.pii.vault import PIIVault


class TestPIIVault:
    def test_store_and_restore(self):
        vault = PIIVault()
        token = vault.store("SSN", "123-45-6789")
        assert token == "[SSN_1]"
        assert vault.restore(token) == "123-45-6789"

    def test_same_value_same_token(self):
        vault = PIIVault()
        t1 = vault.store("EMAIL", "a@b.com")
        t2 = vault.store("EMAIL", "a@b.com")
        assert t1 == t2
        assert vault.token_count == 1

    def test_different_values_different_tokens(self):
        vault = PIIVault()
        t1 = vault.store("EMAIL", "a@b.com")
        t2 = vault.store("EMAIL", "c@d.com")
        assert t1 != t2
        assert vault.token_count == 2

    def test_restore_unknown_returns_none(self):
        vault = PIIVault()
        assert vault.restore("[SSN_99]") is None

    def test_categories_used(self):
        vault = PIIVault()
        vault.store("SSN", "123-45-6789")
        vault.store("EMAIL", "a@b.com")
        assert vault.categories_used == {"SSN", "EMAIL"}

    def test_clear(self):
        vault = PIIVault()
        vault.store("SSN", "123-45-6789")
        vault.clear()
        assert vault.token_count == 0
        assert vault.restore("[SSN_1]") is None
