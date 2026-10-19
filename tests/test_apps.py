import pytest
from desktop_agent.apps import installed_apps, app_registry
from desktop_agent.contracts import Action


def test_app_launch_rejects_paths_and_extra_arguments(tmp_path):
    app = tmp_path / 'editor.exe'
    app.write_bytes(b'MZfixture')
    registry = app_registry({'editor': app})
    for args in ({'app': '../cmd.exe'}, {'app': 'editor', 'args': '/c del'}, {'app': 'missing'}):
        with pytest.raises((ValueError, PermissionError)):
            registry.prepare(Action('a', 'task', 'apps.open', args))
    assert registry.prepare(Action('a', 'task', 'apps.open', {'app': 'editor'})).targets


def test_app_launch_uses_executor_and_blocks_duplicate(tmp_path, monkeypatch):
    from desktop_agent.approvals import ApprovalManager
    from desktop_agent.executor import Executor
    from desktop_agent.contracts import CancelToken
    from desktop_agent.store import Store
    app = tmp_path / 'editor.exe'
    app.write_bytes(b'MZfixture')
    launches = []
    def launch(argv, **kw):
        launches.append((argv, kw))
        return type('Process', (), {'pid': 42})()
    monkeypatch.setattr('desktop_agent.apps.subprocess.Popen', launch)
    with Store(tmp_path / 'journal.sqlite') as store:
        task = store.create_task('open editor')
        store.begin_run(task)
        executor = Executor(store, app_registry({'editor': app}), ApprovalManager(store))
        proposal = executor.prepare(Action('call1', task, 'apps.open', {'app': 'editor'}))
        assert executor.execute(proposal, None, CancelToken()).status == 'partial'
        with pytest.raises(PermissionError):
            executor.execute(proposal, None, CancelToken())
        token = CancelToken()
        token.cancel()
        with pytest.raises(PermissionError):
            executor.execute(proposal, None, token)
    assert len(launches) == 1
    assert launches[0][0] == [str(app)]
    assert launches[0][1]['shell'] is False
