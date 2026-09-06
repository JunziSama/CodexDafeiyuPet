from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path
from queue import Queue

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = PACKAGE_ROOT / "runtime" / "vendor"
if VENDOR_DIR.is_dir() and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from controller.bridge import BridgeService, send_local_message
from controller.config import ConfigStore
from controller.core import ControllerCore
from controller.pet_process import PetProcess
from controller.process_watch import codex_desktop_running
from controller.single_instance import InstanceMutex


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="大肥鱼 Codex 增强桌宠托盘控制器")
    parser.add_argument("--enable", action="store_true", help="手动打开并恢复自动伴随")
    parser.add_argument("--data-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--smoke-seconds", type=float, default=0.0, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    config = ConfigStore(args.data_dir)
    # Hooks need redirected stdin/stdout, so record console python.exe even
    # when the resident tray itself was launched with pythonw.exe.
    hook_python = Path(sys.executable)
    if hook_python.name.lower() == "pythonw.exe":
        console_python = hook_python.with_name("python.exe")
        if console_python.is_file():
            hook_python = console_python
    config.set("python_executable", str(hook_python))
    token = config.bridge_token()
    if args.enable:
        config.update(enhanced_enabled=True, auto_accompany=True, visible=True)

    instance = InstanceMutex.acquire()
    if not instance.acquired:
        if not args.enable:
            return 0
        # The first process may still be creating its loopback bridge.
        for _ in range(15):
            if send_local_message(
                "127.0.0.1",
                int(config.get("bridge_port")),
                token,
                {"kind": "control", "action": "manual-open"},
            ):
                return 0
            time.sleep(0.1)
        return 2

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    from controller.tray import TrayController

    logging.basicConfig(
        filename=str(config.data_dir / "controller.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        instance.close()
        return 3

    # Socket and pet reader threads only enqueue. Controller state and Qt-facing
    # pipe writes are handled by the GUI thread when the timer drains this queue.
    relay = Queue()
    pet = PetProcess(PACKAGE_ROOT, relay, config.data_dir)
    core = ControllerCore(config, pet, codex_desktop_running, inbox=relay)
    try:
        bridge = BridgeService(
            str(config.get("bridge_host")),
            int(config.get("bridge_port")),
            token,
            core.handle_message,
        )
    except OSError:
        # A controller already owns the loopback endpoint. Turn this invocation
        # into a one-shot manual-open signal instead of creating a second tray.
        if args.enable:
            ok = send_local_message(
                "127.0.0.1",
                int(config.get("bridge_port")),
                token,
                {"kind": "control", "action": "manual-open"},
            )
            instance.close()
            return 0 if ok else 2
        instance.close()
        return 0
    bridge.start()

    closing = False
    def close_all() -> None:
        nonlocal closing
        if closing:
            return
        closing = True
        pet.close("controller-exit")
        bridge.close()
        instance.close()
        app.quit()

    tray = TrayController(app, core, config, relay, close_all)
    def request_close(_signum=None, _frame=None) -> None:
        # Schedule native Qt teardown on the GUI thread. This avoids abrupt
        # PySide/Windows tray destruction when a console sends Ctrl+C.
        QTimer.singleShot(0, close_all)

    signal.signal(signal.SIGINT, request_close)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_close)
    # Parent timers to QApplication so PySide cannot collect their wrappers
    # after setup while the native event loop is still running.
    process_timer = QTimer(app)
    process_timer.setInterval(int(config.get("process_poll_ms")))
    process_timer.timeout.connect(core.tick_process)
    process_timer.start()
    event_timer = QTimer(app)
    event_timer.setInterval(100)
    event_timer.timeout.connect(core.drain)
    event_timer.timeout.connect(core.tick_pet)
    event_timer.timeout.connect(tray.refresh)
    event_timer.start()
    core.tick_process()
    if args.smoke_seconds > 0:
        QTimer.singleShot(max(1, int(args.smoke_seconds * 1000)), close_all)
    code = app.exec()
    if not closing:
        close_all()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
