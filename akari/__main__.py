"""python -m akari: akarid, the door of Akari OS."""

from __future__ import annotations

import os
import sys

import uvicorn

from . import accounts, auth, config


def main() -> None:
    if os.getuid() != 0:
        sys.exit("akarid braucht root im Container (mit SETUID, SETGID, CHOWN, DAC_OVERRIDE, FOWNER, KILL).")
    os.umask(0o022)
    accounts.init()
    print(f"\n  {config.OS_NAME} {config.VERSION} · akarid auf Port {config.PORT}", file=sys.stderr)
    if accounts.needs_setup():
        print(f"  Einrichten: http://127.0.0.1:{config.PORT}/?token={auth.SETUP_TOKEN}", file=sys.stderr)
    print("", file=sys.stderr, flush=True)
    uvicorn.run("akari.gateway:app", host=config.HOST, port=config.PORT, log_level="warning",
                ws="websockets", proxy_headers=True, server_header=False)


if __name__ == "__main__":
    main()
