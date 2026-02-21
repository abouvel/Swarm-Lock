"""Tests for swarm/locks.py."""

from swarm.locks import delete_lock, lock_file_path, read_all_locks, read_lock, write_lock


class TestLockFilePath:
    def test_correct_path(self, tmp_path):
        p = lock_file_path(tmp_path, "auth")
        assert p == tmp_path / "current_tasks" / "claimed" / "auth.lock.json"


class TestWriteAndRead:
    def test_round_trip(self, tmp_repo, sample_lock):
        path = write_lock(tmp_repo, sample_lock)
        assert path.exists()
        loaded = read_lock(path)
        assert loaded.keyword == "auth"
        assert loaded.claimed_by == "agent-1"


class TestReadAllLocks:
    def test_reads_locks(self, tmp_repo, sample_lock):
        write_lock(tmp_repo, sample_lock)
        locks = read_all_locks(tmp_repo)
        assert len(locks) == 1
        assert locks[0].keyword == "auth"

    def test_empty(self, tmp_repo):
        assert read_all_locks(tmp_repo) == []


class TestDeleteLock:
    def test_delete_existing(self, tmp_repo, sample_lock):
        write_lock(tmp_repo, sample_lock)
        assert delete_lock(tmp_repo, "auth") is True
        assert not lock_file_path(tmp_repo, "auth").exists()

    def test_delete_missing(self, tmp_repo):
        assert delete_lock(tmp_repo, "nope") is False
