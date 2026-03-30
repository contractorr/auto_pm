from pathlib import Path

from pm_agent.orchestration.locks import FileRunLock, RunLockError


def test_file_run_lock_blocks_second_acquire_until_release(tmp_path: Path):
    lock = FileRunLock()
    lock_path = tmp_path / ".pm-agent-run.lock"

    lease = lock.acquire(
        lock_path=lock_path,
        run_id="run-1",
        repo="contractorr/stewardme",
        trigger="schedule",
    )

    try:
        try:
            lock.acquire(
                lock_path=lock_path,
                run_id="run-2",
                repo="contractorr/stewardme",
                trigger="push",
            )
        except RunLockError as exc:
            assert "another pm-agent run is already active" in str(exc)
        else:
            raise AssertionError("second acquire should fail while the lease is active")
    finally:
        lease.release()

    second = lock.acquire(
        lock_path=lock_path,
        run_id="run-3",
        repo="contractorr/stewardme",
        trigger="push",
    )
    second.release()
