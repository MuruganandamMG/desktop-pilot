"""Small local launch catalog: fixed executable paths, no model-supplied arguments."""

import os
from pathlib import Path
import subprocess

from .contracts import Effect, Result, Target
from .policy import Registry, ToolSpec


def installed_apps():
    windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    programs = Path(os.environ.get('ProgramFiles', r'C:\Program Files'))
    programs86 = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))
    local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    candidates = {
        'notepad': [windows / 'System32/notepad.exe'],
        'calculator': [windows / 'System32/calc.exe'],
        'chrome': [programs / 'Google/Chrome/Application/chrome.exe', programs86 / 'Google/Chrome/Application/chrome.exe'],
        'edge': [programs86 / 'Microsoft/Edge/Application/msedge.exe', programs / 'Microsoft/Edge/Application/msedge.exe'],
        'vscode': [local / 'Programs/Microsoft VS Code/Code.exe', programs / 'Microsoft VS Code/Code.exe'],
        'obsidian': [local / 'Programs/Obsidian/Obsidian.exe', local / 'Obsidian/Obsidian.exe'],
    }
    return {name: next(path for path in paths if path.is_file())
            for name, paths in candidates.items() if any(path.is_file() for path in paths)}


def app_registry(catalog):
    catalog = dict(catalog)
    def validate(args):
        if set(args) != {'app'} or type(args['app']) is not str or args['app'] not in catalog:
            raise ValueError('Choose an installed app ID; paths and arguments are not accepted')
    def snapshot(action):
        path = catalog[action.arguments['app']]
        for ancestor in (path, *path.parents):
            if ancestor.is_symlink() or getattr(ancestor.stat(), 'st_file_attributes', 0) & 0x400:
                raise PermissionError('Reparse app paths are not supported')
        stat = path.stat()
        return (Target(str(path), action.arguments['app'], f'{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}'),)
    def launch(proposal, cancel):
        if cancel.cancelled:
            raise PermissionError('Cancelled')
        process = subprocess.Popen([str(catalog[proposal.action.arguments['app']])], shell=False,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return Result('partial', 'Launch request dispatched; window visibility and focus are not verified',
                      {'observed_state': 'launch-dispatched', 'pid': process.pid})
    return Registry({'apps.open': ToolSpec(Effect.LAUNCH, validate, snapshot, launch,
        lambda proposal, result: result, 'App may remain open; no automatic closing', cloud_safe=True,
        description='Open one installed app. Available IDs: ' + ', '.join(catalog),
        parameters_json_schema={'type': 'object', 'properties': {'app': {'type': 'string', 'enum': list(catalog)}},
                                'required': ['app'], 'additionalProperties': False})})
