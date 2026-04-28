"""
test_container_non_root.py — Day 7: Container hardening verification.

Inspects Dockerfile for security best practices:
  - Non-root USER directive
  - Minimal base image (python:*-slim)
  - No plaintext secrets
  - No debug tools explicitly installed
"""

import os
import re
import pytest


DOCKERFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "Dockerfile")


def _read_dockerfile():
    with open(DOCKERFILE_PATH, "r") as f:
        return f.read()


class TestDockerfileNonRoot:
    def test_has_user_directive(self):
        """Dockerfile MUST contain a USER directive to avoid running as root."""
        content = _read_dockerfile()
        # Look for USER directive (not in a comment)
        lines = content.strip().split("\n")
        user_lines = [
            l for l in lines
            if l.strip().startswith("USER") and not l.strip().startswith("#")
        ]
        assert len(user_lines) > 0, (
            "HARDENING FAIL: Dockerfile has no USER directive — container runs as root"
        )

    def test_user_is_not_root(self):
        """USER directive must not specify root."""
        content = _read_dockerfile()
        lines = content.strip().split("\n")
        user_lines = [
            l.strip() for l in lines
            if l.strip().startswith("USER") and not l.strip().startswith("#")
        ]
        if not user_lines:
            pytest.skip("No USER directive found (separate test covers this)")
        for line in user_lines:
            assert "root" not in line.lower(), (
                f"HARDENING FAIL: USER directive specifies root: {line}"
            )


class TestDockerfileBaseImage:
    def test_uses_slim_base(self):
        """Base image should be slim variant."""
        content = _read_dockerfile()
        from_lines = [
            l.strip() for l in content.split("\n")
            if l.strip().startswith("FROM")
        ]
        assert len(from_lines) > 0, "No FROM directive found"
        assert "slim" in from_lines[0].lower(), (
            f"Base image should be slim: {from_lines[0]}"
        )


class TestDockerfileNoSecrets:
    def test_no_plaintext_secrets(self):
        """Dockerfile must not contain hardcoded secrets."""
        content = _read_dockerfile()
        secret_patterns = [
            r'(?i)(api[_-]?key|secret|password|token)\s*=\s*["\'][^"\']+["\']',
            r'(?i)ANTHROPIC_API_KEY\s*=',
            r'(?i)BACKEND_API_KEY\s*=',
        ]
        for pattern in secret_patterns:
            match = re.search(pattern, content)
            assert match is None, (
                f"HARDENING FAIL: Possible secret in Dockerfile: {match.group()}"
            )


class TestDockerfileNoDebugTools:
    def test_no_debug_tools_installed(self):
        """Dockerfile should not install debug/dev tools."""
        content = _read_dockerfile()
        debug_tools = ["vim", "nano", "gdb", "strace", "tcpdump", "nmap", "netcat"]
        for tool in debug_tools:
            assert tool not in content.lower(), (
                f"HARDENING FAIL: Debug tool '{tool}' found in Dockerfile"
            )
