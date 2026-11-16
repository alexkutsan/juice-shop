#!/usr/bin/env python3
"""Run Bright Agent and stop its whole process group on harness fallback."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import sys
import time

FALLBACK_EXIT_CODE = 86
TERMINATE_GRACE_SECONDS = 0.25
FALLBACK_MARKERS = (
    b"falling back to function harness mode",
    b"falling back to function harness",
    b"starting function harness mode",
    b"starting function harness",
    b"starting the function harness",
    b"running in function harness mode",
    b"running function harness",
    b"switching to function harness",
)
MAX_MARKER_LENGTH = max(map(len, FALLBACK_MARKERS))


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass

    # The parent may exit before a child harness. Kill the group either way.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run(command: list[str]) -> int:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        start_new_session=True,
    )
    assert process.stdout is not None
    assert process.stderr is not None

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, sys.stdout.buffer)
    selector.register(process.stderr, selectors.EVENT_READ, sys.stderr.buffer)
    tails: dict[int, bytes] = {}
    fallback_seen = False

    while selector.get_map():
        for key, _ in selector.select():
            chunk = os.read(key.fd, 65536)
            if not chunk:
                selector.unregister(key.fileobj)
                key.fileobj.close()
                continue

            output = key.data
            output.write(chunk)
            output.flush()

            window = (tails.get(key.fd, b"") + chunk).lower()
            tails[key.fd] = window[-(MAX_MARKER_LENGTH - 1) :]
            if fallback_seen:
                continue

            marker = next((item for item in FALLBACK_MARKERS if item in window), None)
            if marker is None:
                continue

            fallback_seen = True
            message = marker.decode("ascii")
            print(
                f"::error title=Function harness blocked::Detected '{message}'. "
                "Terminating the Bright Agent process group.",
                file=sys.stderr,
                flush=True,
            )
            terminate_process_group(process)

    return_code = process.wait()
    if fallback_seen:
        return FALLBACK_EXIT_CODE
    if return_code < 0:
        return 128 - return_code
    return return_code


def main() -> int:
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} COMMAND [ARG ...]", file=sys.stderr)
        return 64
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
