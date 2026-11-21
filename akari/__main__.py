"""python -m akari: akarid, the door of Akari OS."""

from __future__ import annotations

import os
import sys

import uvicorn

from . import accounts, auth, config


def _lucent_cli(argv: list[str]) -> None:
    """python -m akari --lucent-join URL CODE [--ui-url URL] [--base-url URL] | --lucent-leave"""
    import asyncio
    from . import lucent
    if argv[0] == "--lucent-leave":
        print("Entkoppelt." if lucent.leave() else "Akari war nicht gekoppelt.")
        return
    if len(argv) < 3:
        sys.exit("python -m akari --lucent-join LUCENT-ADRESSE CODE [--ui-url ADRESSE] [--base-url ADRESSE]")
    opts = dict(zip(argv[3::2], argv[4::2]))
    ui = opts.get("--ui-url") or f"http://127.0.0.1:{config.PORT}"
    try:
        p = asyncio.run(lucent.join(argv[1], argv[2], ui, opts.get("--base-url")))
    except lucent.LucentError as e:
        sys.exit(str(e))
    print(f"Mit Lucent gekoppelt: {p['issuer']} (Client {p['client_id']}).")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("--lucent-join", "--lucent-leave"):
        return _lucent_cli(sys.argv[1:])
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
