"""Hands-free voice conversation with local Windows spoken controls."""

import asyncio
from collections import deque
from contextlib import ExitStack
from datetime import datetime
import re
import sys
from threading import Lock
import time

from .context import redact
from .settings import get_api_key, voice_settings, load_settings
from .contracts import TaskState


class AudioError(RuntimeError):
    """Local, credential-free audio diagnostic safe for the terminal."""


def safe_text(value):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', str(value))
    return ''.join(c for c in redact(text) if c.isprintable() or c == '\n')[:2000]


def event(kind, detail=''):
    print(f'[{datetime.now():%H:%M:%S}] {safe_text(kind)} {safe_text(detail)}', flush=True)


def list_devices():
    try:
        import sounddevice as sd
        print(sd.query_devices())
        return 0
    except Exception:
        event('AUDIO ERROR', 'Cannot list devices. Check Windows audio settings and microphone permissions.')
        return 1


class AudioBuffer:
    def __init__(self):
        self.inputs = deque()
        self.playback = bytearray()
        self.lock = Lock()
        self.error = None
        self.sent = self.played = 0

    def capture(self, data, status=False):
        with self.lock:
            if status or len(self.inputs) >= 12:
                self.error = 'Microphone overflow; session stopped rather than queueing stale speech.'
            else:
                self.inputs.append(bytes(data))

    def take_input(self):
        with self.lock:
            return self.inputs.popleft() if self.inputs else None

    def add_output(self, data):
        with self.lock:
            # Provider packets can arrive faster than playback; retain at most ten seconds.
            if len(self.playback) + len(data) > 480000:
                self.error = 'Speaker buffer overflow; session stopped. Check your output device/network.'
            else:
                self.playback.extend(data)

    def output(self, size):
        with self.lock:
            data = bytes(self.playback[:size])
            del self.playback[:size]
            self.played += len(data)
            return data + bytes(size - len(data))

    def interrupt(self):
        with self.lock:
            self.playback.clear()


async def receive(session, audio, log=event, tool_handler=None):
    turns = 0
    while True:
        received = False
        async for response in session.receive():
            received = True
            if response.go_away:
                raise ConnectionError('Session expiry')
            if response.tool_call:
                # No desktop adapter is enabled for voice; never dispatch an unsolicited function.
                from google.genai import types
                replies = [types.FunctionResponse(id=fc.id, name=fc.name,
                           response=tool_handler(fc) if tool_handler else {'error': 'Computer actions are not enabled in this session.'})
                           for fc in response.tool_call.function_calls or []]
                log('TOOL RESULT', 'Local policy handled the request; see the receipt.')
                await session.send_tool_response(function_responses=replies)
            content = response.server_content
            if content:
                if content.interrupted:
                    audio.interrupt()
                    log('INTERRUPTED', 'Queued speech discarded; listening.')
                else:
                    for part in (content.model_turn.parts or []) if content.model_turn else []:
                        blob = part.inline_data
                        if blob and blob.data:
                            if not blob.mime_type.startswith('audio/pcm') or len(blob.data) % 2:
                                raise ValueError('Unexpected audio format')
                            audio.add_output(blob.data)
                            if audio.error:
                                raise AudioError(audio.error)
                for label, transcript in (('YOU', content.input_transcription),
                                          ('GEMINI (advice)', content.output_transcription)):
                    if transcript and transcript.text:
                        log(label, transcript.text)
                if content.turn_complete:
                    turns += 1
                    log('TURN COMPLETE', f'{turns}/20; listening for your next sentence.')
                    if turns >= 20:
                        return
            if response.usage_metadata:
                usage = response.usage_metadata
                log('API USAGE', f'input={usage.prompt_token_count}, output={usage.response_token_count}; provider billing may differ.')
        if not received:
            raise ConnectionError('Empty stream')


async def stream_session(client, model, devices, stopped, *, audio_module=None, log=event, tool_handler=None, declarations=()):
    from google.genai import types
    if stopped.is_set():
        return
    if audio_module is None:
        import sounddevice as audio_module
    sd = audio_module
    audio = AudioBuffer()
    config = types.LiveConnectConfig(response_modalities=['AUDIO'],
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in declarations])] if declarations else None,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=('You are Desktop Pilot, a concise voice assistant. Respond naturally in the user\'s language. '
                            'Use declared tools for supported app opening. Never invent computer actions. '
                            'A launch receipt does not verify window visibility or focus. No shell, deletion, or file changes are available. '
                            'Never request API keys or passwords.'))
    sd.check_input_settings(device=devices[0], channels=1, dtype='int16', samplerate=16000)
    sd.check_output_settings(device=devices[1], channels=1, dtype='int16', samplerate=24000)
    started = time.monotonic()
    log('API CONNECT', f'{model}; waiting for Gemini Live setup (15s limit).')
    connection = client.aio.live.connect(model=model, config=config)
    connecting = asyncio.create_task(connection.__aenter__())
    stop_connect = asyncio.create_task(stopped.wait())
    try:
        done, _ = await asyncio.wait([connecting, stop_connect], timeout=15, return_when=asyncio.FIRST_COMPLETED)
        if connecting not in done:
            if stopped.is_set():
                return
            raise TimeoutError()
        session = connecting.result()
    finally:
        stop_connect.cancel()
        if not connecting.done():
            connecting.cancel()
        await asyncio.gather(stop_connect, connecting, return_exceptions=True)
    try:
        if stopped.is_set():
            return
        log('CONNECTED', f'{time.monotonic() - started:.2f}s. Listening continuously. Say Pilot pause or Pilot exit.')
        with ExitStack() as stack:
            mic = stack.enter_context(sd.RawInputStream(samplerate=16000, channels=1, dtype='int16',
                blocksize=320, device=devices[0], callback=lambda data, frames, timing, status: audio.capture(data, status)))
            def playback(data, frames, timing, status):
                # A timing underrun is recoverable; stream.active detects device loss.
                data[:] = audio.output(len(data))
            speaker = stack.enter_context(sd.RawOutputStream(samplerate=24000, channels=1, dtype='int16',
                blocksize=480, device=devices[1], callback=playback))
            async def send():
                while True:
                    if audio.error:
                        raise AudioError(audio.error)
                    if not mic.active or not speaker.active:
                        raise AudioError('Audio device stopped; check the selected microphone and speaker.')
                    data = audio.take_input()
                    if data is None:
                        await asyncio.sleep(.005)
                        continue
                    await session.send_realtime_input(audio=types.Blob(data=data, mime_type='audio/pcm;rate=16000'))
                    audio.sent += 1
            async def heartbeat():
                while True:
                    await asyncio.sleep(5)
                    log('LIVE', f'{time.monotonic() - started:.0f}s | mic chunks sent={audio.sent} | played bytes={audio.played}')
            tasks = [asyncio.create_task(send()), asyncio.create_task(receive(session, audio, log, tool_handler)),
                     asyncio.create_task(stopped.wait()), asyncio.create_task(heartbeat())]
            try:
                done, _ = await asyncio.wait(tasks, timeout=600, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                if tasks[1] in done and not stopped.is_set():
                    mic.abort()
                    deadline = time.monotonic() + 10.1
                    while audio.playback and not stopped.is_set() and time.monotonic() < deadline:
                        await asyncio.sleep(.01)
                if not done:
                    log('SESSION LIMIT', 'Ten minutes reached. Say Pilot resume for a fresh conversation.')
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                audio.interrupt()
                mic.abort()
    finally:
        try:
            async with asyncio.timeout(5):
                await connection.__aexit__(None, None, None)
        except Exception:
            log('CLOSE WARNING', 'Network close did not complete; local audio handles released.')
        log('STOPPED', 'Microphone and speaker closed. No automatic reconnection.')


async def journaled_session(store, client, model, devices, stopped):
    from .apps import app_registry, installed_apps
    from .approvals import ApprovalManager
    from .executor import Executor
    from .contracts import Action, CancelToken
    registry = app_registry(installed_apps())
    executor = Executor(store, registry, ApprovalManager(store))
    task_id = store.create_task('Voice conversation')
    store.begin_run(task_id)
    calls = 0
    def handle(fc):
        nonlocal calls
        calls += 1
        if stopped.is_set() or calls > 20:
            return {'error': 'Task stopped or tool limit reached'}
        try:
            proposal = executor.prepare(Action(fc.id, task_id, fc.name, fc.args or {}))
            result = executor.execute(proposal, None, CancelToken())
            event('APP RECEIPT', result.summary)
            return {'status': result.status, 'summary': result.summary,
                    'observed_state': result.evidence.get('observed_state')}
        except Exception:
            return {'error': 'App request denied, duplicated, changed, or unavailable; no retry was performed'}
    def log(kind, detail=''):
        if kind == 'API CONNECT':
            store.append_event(task_id, {'kind': 'model_usage', 'transport': 'live',
                               'model': model, 'attempts': 1, 'input_tokens': None, 'output_tokens': None})
        elif kind == 'API USAGE':
            store.append_event(task_id, {'kind': 'voice_usage', 'summary': safe_text(detail)})
        event(kind, detail)
    try:
        await stream_session(client, model, devices, stopped, log=log, tool_handler=handle,
                             declarations=registry.declarations())
    except asyncio.CancelledError:
        store.transition(task_id, TaskState.CANCELLED)
        raise
    except Exception:
        store.transition(task_id, TaskState.FAILED)
        raise
    else:
        store.transition(task_id, TaskState.PAUSED)


def error_message(exc):
    if isinstance(exc, AudioError):
        return str(exc)
    code = getattr(exc, 'code', None)
    if code in (401, 403):
        return 'Authentication/access denied. Check GEMINI_API_KEY and model access locally.'
    if code == 429:
        return 'Quota/rate limit reached. Check provider quota; no automatic retry.'
    if code == 404:
        return 'Configured Live model is unavailable. Set GEMINI_LIVE_MODEL to an accessible audio model.'
    if isinstance(exc, TimeoutError):
        return 'Connection timed out. Check your network; no automatic retry.'
    return f'{type(exc).__name__}: session failed. Check audio devices, network and Live model compatibility. No automatic retry.'


def run(store, data_path):
    import os
    if os.name != 'nt' or not sys.stdin.isatty():
        event('START ERROR', 'Launch in an interactive Windows PowerShell terminal. No microphone opened.')
        return 1
    from PySide6.QtGui import QGuiApplication, QWindow
    from .app import acquire_instance_lock
    from .windows_events import WindowsEvents
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    lock = acquire_instance_lock(data_path)
    if lock is None:
        event('ALREADY RUNNING', 'Close the existing Desktop Pilot instance first, then run again.')
        return 2
    receiver = QWindow()
    receiver.create()  # Native message receiver only; never show a window.
    try:
        return asyncio.run(_terminal(app, receiver, store, data_path, WindowsEvents))
    except KeyboardInterrupt:
        event('EXIT', 'Voice stopped by Ctrl+C.')
        return 0
    except Exception as exc:
        event('START ERROR', error_message(exc))
        return 1
    finally:
        receiver.destroy()
        lock.unlock()


async def _terminal(app, receiver, store, data_path, events_class):
    from google import genai
    from google.genai import types
    from .speech_controls import VoiceControls
    store.interrupt_inflight()
    model, input_device, output_device = voice_settings()
    settings = load_settings(data_path / 'settings.json')
    if settings.budget_usd:
        event('BUDGET', 'Live rates are not configured; voice disabled under the dollar cap. No request made.')
        return 1
    key_value = get_api_key()
    if not key_value:
        event('KEY MISSING', 'Set GEMINI_API_KEY in the ignored project .env before launching.')
        return 1
    stopped = asyncio.Event()
    paused, locked = False, False
    approvals_dirty = False
    store.db.execute("PRAGMA busy_timeout=100")
    active = None
    client = None
    controls = None
    listening = None
    pending_command = None
    def pause():
        nonlocal paused, approvals_dirty
        paused = approvals_dirty = True
        stopped.set()
        event('PAUSED', 'Cloud audio stopping. Local voice controls remain available while unlocked.')
    def session_lock():
        nonlocal locked, pending_command
        locked = True
        pending_command = None
        pause()
    def session_unlock():
        nonlocal locked
        locked = False
        event('UNLOCKED', 'Still paused. Say Pilot resume when local controls are ready.')
    hooks = events_class(int(receiver.winId()), pause, session_lock, session_unlock)
    app.installNativeEventFilter(hooks)
    async def pump_events():
        while True:
            app.processEvents()
            await asyncio.sleep(.02)
    pump = asyncio.create_task(pump_events())
    try:
        hotkey, session_guard = hooks.start()
        event('DESKTOP PILOT', 'HANDS-FREE VOICE | launching starts listening | no visible window')
        event('MODEL', model)
        event('PRIVACY', 'Microphone audio streams to Google while active. Pilot pause disconnects cloud audio; Windows still listens locally for controls. No recording.')
        event('SAY', 'Pilot pause | Pilot resume | Pilot exit. Ctrl+C is an emergency fallback.')
        event('AUDIO', 'Use a headset and the Windows default microphone for spoken controls.')
        event('SAFETY', f'Ctrl+Alt+Pause={"ready" if hotkey else "unavailable; use Ctrl+C"}; lock monitoring={session_guard}')
        if not session_guard:
            event('DISABLED', 'Session monitoring unavailable. No microphone or cloud connection started.')
            return 1
        client = genai.Client(api_key=key_value, vertexai=False, enterprise=False,
            http_options=types.HttpOptions(base_url='https://generativelanguage.googleapis.com', api_version='v1beta'))
        def start():
            nonlocal active, stopped
            if locked or paused:
                return
            stopped = asyncio.Event()
            active = asyncio.create_task(journaled_session(store, client, model, (input_device, output_device), stopped))
        async def finish_active():
            nonlocal active
            stopped.set()
            if active:
                try:
                    await asyncio.wait_for(asyncio.shield(active), timeout=8)
                except TimeoutError:
                    event('STOP WARNING', 'Session shutdown deadline reached; cancelling local work.')
                    active.cancel()
                    await asyncio.gather(active, return_exceptions=True)
                except Exception as exc:
                    event('VOICE ERROR', error_message(exc))
                active = None
        controls = VoiceControls()
        await controls.start()
        listening = asyncio.create_task(controls.read())
        app.processEvents()
        if not locked and not paused:
            await controls.say('listening')
            start()
        was_locked = False
        while True:
            if locked:
                pending_command = None
                stopped.set()
                if controls:
                    if listening:
                        listening.cancel()
                        await asyncio.gather(listening, return_exceptions=True)
                        listening = None
                    await controls.close()
                    controls = None
                was_locked = True
            elif was_locked:
                controls = VoiceControls()
                await controls.start()
                listening = asyncio.create_task(controls.read())
                was_locked = False
            if active and active.done():
                try:
                    active.result()
                except Exception as exc:
                    event('VOICE ERROR', error_message(exc))
                    if controls:
                        await controls.say('failed')
                else:
                    if not paused and controls:
                        await controls.say('limit')
                active = None
                paused = True
                event('STANDBY', 'Say Pilot resume for another conversation; Pilot exit to quit.')
            if paused:
                stopped.set()
            if approvals_dirty and not active:
                try:
                    store.invalidate_approvals()
                except Exception:
                    event('JOURNAL ERROR', 'Approval reset failed. Resume remains blocked until a successful retry.')
                approvals_dirty = False
            if listening and listening.done():
                pending_command = listening.result()
                listening = asyncio.create_task(controls.read())
            if pending_command == 'exit':
                await finish_active()
                if controls:
                    await controls.say('goodbye')
                break
            if pending_command == 'pause':
                pause()
                await finish_active()
                if controls:
                    await controls.say('paused')
                pending_command = None
            if pending_command == 'resume' and not locked and not active:
                try:
                    store.invalidate_approvals()
                except Exception:
                    event('JOURNAL ERROR', 'Resume blocked. Approval reset failed.')
                    if controls:
                        await controls.say('failed')
                else:
                    paused = False
                    await controls.say('resumed')
                    start()
                pending_command = None
            elif pending_command == 'resume':
                pending_command = None
            await asyncio.sleep(.02)
    finally:
        stopped.set()
        try:
            if active:
                active.cancel()
                await asyncio.gather(active, return_exceptions=True)
            if listening:
                listening.cancel()
                await asyncio.gather(listening, return_exceptions=True)
            if controls:
                await controls.close()
            if client:
                await client.aio.aclose()
                client.close()
        finally:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)
            app.removeNativeEventFilter(hooks)
            hooks.close()
    event('EXIT', 'Audio, network and native registrations released.')
    return 0
