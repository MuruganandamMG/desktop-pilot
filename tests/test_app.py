import json

from desktop_agent.__main__ import main


def test_status_is_offline_and_does_not_create_a_task(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path), "--status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["cloud_requests"] == 0
    assert status["registered_tools"] == ["runtime_status"]
    assert status["tasks"] == []


def test_instance_lock_prevents_a_second_runtime(qapp, tmp_path):
    from desktop_agent.app import acquire_instance_lock
    lock = acquire_instance_lock(tmp_path)
    assert lock is not None
    assert acquire_instance_lock(tmp_path) is None
    lock.unlock()
