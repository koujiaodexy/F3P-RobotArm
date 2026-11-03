#!/usr/bin/env python3
"""Application entry point for the F3P Linux HDMI control panel."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from robot_arm_gui.backend import MemoryMappedBackend, SimulatedBackend, SocketCanBackend
    from robot_arm_gui.controller import MotorController
    from robot_arm_gui.window import MainWindow
else:
    from .backend import MemoryMappedBackend, SimulatedBackend, SocketCanBackend
    from .controller import MotorController
    from .window import MainWindow

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="F3P robot-arm Linux HDMI control panel")
    parser.add_argument(
        "--backend",
        choices=("simulation", "mmio", "socketcan"),
        default="simulation",
        help="transport backend (default: simulation)",
    )
    parser.add_argument("--interface", default="vcan0", help="SocketCAN interface")
    parser.add_argument(
        "--allow-live-control",
        action="store_true",
        help="required before socketcan can be selected",
    )
    parser.add_argument("--windowed", action="store_true", help="do not enter full screen")
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="render one 1280x720 frame to PNG and exit",
    )
    parser.add_argument(
        "--font-file",
        type=Path,
        help="optional CJK TTF/TTC file (the board image is auto-detected)",
    )
    return parser


def configure_cjk_font(app: QApplication, explicit_path: Path | None) -> None:
    candidates = [
        explicit_path,
        Path("/usr/share/fonts-droid-fallback/truetype/DroidSansFallback.ttf"),
        Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
    ]
    for path in candidates:
        if path is None or not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                app.setFont(QFont(families[0], 11))
                return


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.backend != "simulation" and not args.allow_live_control:
        print(
            "ERROR: live backends require --allow-live-control after physical safety checks",
            file=sys.stderr,
        )
        return 2

    if args.backend == "mmio":
        backend = MemoryMappedBackend()
    elif args.backend == "socketcan":
        backend = SocketCanBackend(args.interface)
    else:
        backend = SimulatedBackend()
    app = QApplication(sys.argv[:1])
    configure_cjk_font(app, args.font_file)
    window = MainWindow(MotorController(backend), live_control=args.backend != "simulation")
    if args.windowed or args.screenshot:
        window.show()
    else:
        window.showFullScreen()
    if args.screenshot:
        window.resize(1280, 720)

        def save_screenshot() -> None:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.screenshot), "PNG"):
                print(f"ERROR: cannot save screenshot to {args.screenshot}", file=sys.stderr)
                app.exit(3)
                return
            app.quit()

        QTimer.singleShot(250, save_screenshot)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
