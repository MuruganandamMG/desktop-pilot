import argparse
import json
from pathlib import Path

from .settings import data_dir
from .store import Store
from .policy import runtime_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Desktop Pilot — read-only cloud preview")
    parser.add_argument("--data-dir", type=Path, default=data_dir())
    parser.add_argument("--status", action="store_true", help="Print offline local status and exit")
    parser.add_argument("--gui", action="store_true", help="Open the legacy native preview instead of voice")
    parser.add_argument("--list-audio-devices", action="store_true", help="List local audio devices without connecting")
    args = parser.parse_args(argv)
    if args.list_audio_devices:
        from .voice import list_devices
        return list_devices()
    with Store(args.data_dir / "tasks.sqlite") as store:
        if args.status:
            print(json.dumps({"cloud_requests": store.model_request_count(), "registered_tools": [tool["name"] for tool in runtime_registry().declarations()], "tasks": store.list_tasks()}))
            return 0
        if args.gui:
            from .app import run
        else:
            from .voice import run
        return run(store, args.data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
