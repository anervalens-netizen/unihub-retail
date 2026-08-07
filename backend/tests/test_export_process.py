from __future__ import annotations

import multiprocessing
import time

from services.export_process import _terminate_process


def test_export_process_terminate_has_hard_kill_fallback() -> None:
    process = multiprocessing.get_context("spawn").Process(target=time.sleep, args=(30,))
    process.start()
    try:
        _terminate_process(process, grace_seconds=0.05)
        assert not process.is_alive()
        assert process.exitcode is not None
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
