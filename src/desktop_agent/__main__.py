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
    args = parser.parse_args(argv)
    with Store(args.data_dir / "tasks.sqlite") as store:
        if args.status:
            print(json.dumps({"cloud_requests": store.model_request_count(), "registered_tools": [tool["name"] for tool in runtime_registry().declarations()], "tasks": store.list_tasks()}))
            return 0
        from .app import run
        return run(store, args.data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
