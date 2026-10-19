import json

from desktop_agent.__main__ import main


def test_status_is_offline_and_does_not_create_a_task(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path), "--status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["cloud_requests"] == 0
    assert status["registered_tools"] == []
    assert status["tasks"] == []
