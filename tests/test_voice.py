import asyncio
from types import SimpleNamespace as N
import pytest

from desktop_agent.voice import AudioBuffer, receive, safe_text
from desktop_agent.settings import voice_settings


def test_default_launch_uses_voice(tmp_path, monkeypatch):
    from desktop_agent.__main__ import main
    calls = []
    monkeypatch.setattr('desktop_agent.voice.run', lambda store, path: calls.append(path) or 0)
    assert main(['--data-dir', str(tmp_path)]) == 0
    assert calls == [tmp_path]


def test_voice_environment_literal_and_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr('desktop_agent.settings.PROJECT_ROOT', tmp_path)
    (tmp_path / 'pyproject.toml').touch()
    (tmp_path / '.env').write_text('GEMINI_LIVE_MODEL="my-live-model"\nVOICE_INPUT_DEVICE=3\n')
    monkeypatch.delenv('GEMINI_LIVE_MODEL', raising=False)
    monkeypatch.delenv('VOICE_INPUT_DEVICE', raising=False)
    monkeypatch.delenv('VOICE_OUTPUT_DEVICE', raising=False)
    assert voice_settings() == ('my-live-model', 3, None)
    monkeypatch.setenv('GEMINI_LIVE_MODEL', 'override')
    assert voice_settings()[0] == 'override'
    monkeypatch.setenv('VOICE_INPUT_DEVICE', 'invalid')
    with pytest.raises(ValueError, match='VOICE_INPUT_DEVICE'):
        voice_settings()


def test_audio_bounds_and_interrupt():
    audio = AudioBuffer()
    audio.add_output(b'\x01\x00' * 480)
    assert audio.output(960) == b'\x01\x00' * 480
    audio.add_output(b'\x01\x00' * 480)
    audio.interrupt()
    assert audio.output(960) == bytes(960)
    audio.add_output(bytes(24002))
    assert audio.error
    audio = AudioBuffer()
    for _ in range(13):
        audio.capture(bytes(640))
    assert audio.error


def test_terminal_output_cannot_inject_escapes():
    assert '\x1b' not in safe_text('\x1b[2JAPI_KEY=secret\rhello\x07')
    assert '\r' not in safe_text('x\ry')


def test_receive_handles_all_audio_parts_and_interrupts():
    class Session:
        def __init__(self):
            self.calls = 0
        async def receive(self):
            self.calls += 1
            if self.calls == 1:
                yield N(server_content=N(interrupted=False,
                    model_turn=N(parts=[N(inline_data=N(data=b'12', mime_type='audio/pcm;rate=24000')),
                                        N(inline_data=N(data=b'34', mime_type='audio/pcm;rate=24000'))]),
                    input_transcription=None, output_transcription=None, turn_complete=True),
                    tool_call=None, usage_metadata=None, go_away=None)
            else:
                raise ConnectionError('private provider error')
    audio = AudioBuffer()
    logs = []
    with pytest.raises(ConnectionError):
        asyncio.run(receive(Session(), audio, lambda *args: logs.append(args)))
    assert audio.output(4) == b'1234'
    assert any('turn' in str(item).lower() for item in logs)


@pytest.mark.parametrize('device_active', [True, False])
def test_session_stop_closes_audio_and_context_without_sending_more(device_active):
    from desktop_agent.voice import stream_session
    calls = []
    class Stream:
        active = device_active
        def __enter__(self):
            calls.append('audio_open')
            return self
        def __exit__(self, *args):
            calls.append('audio_close')
        def abort(self):
            calls.append('abort')
    class Session:
        async def receive(self):
            await asyncio.sleep(60)
            yield
        async def close(self):
            calls.append('session_close')
    class Connection:
        async def __aenter__(self):
            calls.append('connect')
            return Session()
        async def __aexit__(self, *args):
            calls.append('context_close')
    sd = N(check_input_settings=lambda **kw: None, check_output_settings=lambda **kw: None,
           RawInputStream=lambda **kw: Stream(), RawOutputStream=lambda **kw: Stream())
    client = N(aio=N(live=N(connect=lambda **kw: Connection())))
    async def check():
        stopped = asyncio.Event()
        def log(kind, detail):
            if kind == 'CONNECTED':
                asyncio.get_running_loop().call_later(.02, stopped.set)
        await stream_session(client, 'test-live', (None, None), stopped, audio_module=sd, log=log)
    if device_active:
        asyncio.run(check())
    else:
        with pytest.raises(RuntimeError, match='Audio device'):
            asyncio.run(check())
    assert calls.count('audio_close') == 2
    assert 'context_close' in calls


def test_provider_interruption_discards_old_audio():
    class Session:
        async def receive(self):
            yield N(server_content=N(interrupted=True, model_turn=None, input_transcription=None,
                    output_transcription=None, turn_complete=False), tool_call=None,
                    usage_metadata=None, go_away=None)
            raise ConnectionError()
    audio = AudioBuffer()
    audio.add_output(b'1234')
    with pytest.raises(ConnectionError):
        asyncio.run(receive(Session(), audio, lambda *args: None))
    assert audio.output(4) == bytes(4)


def test_stop_during_connect_never_opens_microphone():
    from desktop_agent.voice import stream_session
    calls = []
    class Connection:
        async def __aenter__(self):
            calls.append('connecting')
            await asyncio.sleep(60)
        async def __aexit__(self, *args):
            pass
    sd = N(check_input_settings=lambda **kw: None, check_output_settings=lambda **kw: None,
           RawInputStream=lambda **kw: calls.append('microphone'))
    client = N(aio=N(live=N(connect=lambda **kw: Connection())))
    async def check():
        stopped = asyncio.Event()
        asyncio.get_running_loop().call_later(.02, stopped.set)
        await stream_session(client, 'test', (None, None), stopped, audio_module=sd, log=lambda *a: None)
    asyncio.run(check())
    assert calls == ['connecting']


def test_voice_journal_counts_connection_without_retaining_transcript(tmp_path, monkeypatch):
    from desktop_agent.voice import journaled_session
    from desktop_agent.store import Store
    async def fake(*args, **kwargs):
        kwargs['log']('API CONNECT', 'test')
        kwargs['log']('YOU', 'private spoken words')
    monkeypatch.setattr('desktop_agent.voice.stream_session', fake)
    with Store(tmp_path / 'tasks.sqlite') as store:
        asyncio.run(journaled_session(store, None, 'test', (None, None), asyncio.Event()))
        task = store.list_tasks()[0]
        assert task['state'] == 'PAUSED'
        assert store.model_request_count() == 1
        assert 'private spoken words' not in str(store.events(task['id']))
