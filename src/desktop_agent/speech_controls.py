"""Fixed local Windows speech controls; never a model-accessible shell tool."""

import asyncio
from pathlib import Path
import os
import subprocess


def control_message(line):
    value = line.decode('ascii').strip()
    if value not in {'ready', 'pause', 'resume', 'exit'}:
        raise ValueError('Windows speech controls failed or sent an invalid event')
    return value


class VoiceControls:
    def __init__(self):
        self.process = None

    async def start(self):
        executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        script = Path(__file__).with_suffix('.ps1')
        self.process = await asyncio.create_subprocess_exec(str(executable), '-NoLogo', '-NoProfile',
            '-NonInteractive', '-File', str(script), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, limit=128)
        try:
            async with asyncio.timeout(20):
                if await self.read() != 'ready':
                    raise RuntimeError('Speech controls not ready')
        except BaseException:
            await self.close()
            raise

    async def read(self):
        if not self.process:
            raise RuntimeError('Speech control process not started')
        line = await self.process.stdout.readline()
        if not line:
            raise RuntimeError('Windows speech controls disconnected')
        return control_message(line)

    async def say(self, message):
        if message not in {'listening', 'paused', 'resumed', 'goodbye', 'failed', 'limit'}:
            raise ValueError('Unknown local voice notification')
        self.process.stdin.write((message + '\n').encode('ascii'))
        await self.process.stdin.drain()

    async def close(self):
        process, self.process = self.process, None
        if process is None or process.returncode is not None:
            return
        try:
            process.stdin.write(b'shutdown\n')
            await process.stdin.drain()
            async with asyncio.timeout(3):
                await process.wait()
        except (TimeoutError, BrokenPipeError, ConnectionResetError):
            if process.returncode is None:
                process.kill()
                await process.wait()
