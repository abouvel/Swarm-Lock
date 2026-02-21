"""Tests for swarm/hooks.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from swarm.hooks import install_post_checkout_hook, uninstall_post_checkout_hook


@pytest.fixture
def repo_with_git(tmp_path):
    """Tmp dir with .git/hooks structure."""
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    return tmp_path


class TestInstallHook:
    def test_creates_hook(self, repo_with_git):
        path = install_post_checkout_hook(repo_with_git, "/path/to/cli.py")
        assert path.exists()
        content = path.read_text()
        assert "Swarm Lock Manager" in content
        assert "/path/to/cli.py" in content
        # Should be executable
        import stat
        assert path.stat().st_mode & stat.S_IEXEC

    def test_idempotent(self, repo_with_git):
        install_post_checkout_hook(repo_with_git, "/path/to/cli.py")
        install_post_checkout_hook(repo_with_git, "/path/to/cli.py")
        content = (repo_with_git / ".git" / "hooks" / "post-checkout").read_text()
        # Should only have one copy
        assert content.count("Swarm Lock Manager") == 1

    def test_appends_to_existing_hook(self, repo_with_git):
        hook_path = repo_with_git / ".git" / "hooks" / "post-checkout"
        hook_path.write_text("#!/bin/bash\necho 'existing hook'\n")
        install_post_checkout_hook(repo_with_git, "/path/to/cli.py")
        content = hook_path.read_text()
        assert "existing hook" in content
        assert "Swarm Lock Manager" in content


class TestUninstallHook:
    def test_removes_hook(self, repo_with_git):
        install_post_checkout_hook(repo_with_git, "/path/to/cli.py")
        assert uninstall_post_checkout_hook(repo_with_git) is True
        assert not (repo_with_git / ".git" / "hooks" / "post-checkout").exists()

    def test_no_hook(self, repo_with_git):
        assert uninstall_post_checkout_hook(repo_with_git) is False

    def test_non_swarm_hook_left_alone(self, repo_with_git):
        hook_path = repo_with_git / ".git" / "hooks" / "post-checkout"
        hook_path.write_text("#!/bin/bash\necho 'other hook'\n")
        assert uninstall_post_checkout_hook(repo_with_git) is False
        assert hook_path.exists()
