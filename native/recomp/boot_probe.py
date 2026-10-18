"""Record a bounded headless runtime session; captures are not gameplay proof."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--framework", required=True, type=Path)
    ap.add_argument("--exe", required=True, type=Path)
    ap.add_argument("--game", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--seconds", type=float, default=45)
    ap.add_argument("--frames", type=int, help="Stop at or after this sampled emulated frame")
    ap.add_argument("--port", type=int, default=44362)
    args = ap.parse_args()
    if not 1 <= args.seconds <= 300 or not 1024 <= args.port <= 65535:
        ap.error("Use 1..300 seconds and a port in 1024..65535")
    if args.frames is not None and not 1 <= args.frames <= 1000000:
        ap.error("Use a frame target in 1..1000000")
    out = args.output.resolve()
    source_repo = Path(__file__).resolve().parents[2]
    if out.is_relative_to(source_repo) or source_repo.is_relative_to(out):
        ap.error("Private captures must be outside the source repository and its parents")
    if out.exists():
        ap.error("Choose a fresh output directory")
    exe, game = args.exe.resolve(), args.game.resolve()
    client_path = args.framework.resolve() / "tools/debug_client.py"
    if not all(p.is_file() for p in (exe, game, client_path)):
        ap.error("Runtime, game config or debug client is missing")
    # Refuse to attach to an already-running user's session on this port.
    with socket.socket() as check:
        check.bind(("127.0.0.1", args.port))
    spec = importlib.util.spec_from_file_location("psx_probe_client", client_path)
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    out.mkdir(parents=True)
    events, diagnostics = [], {}
    started = time.monotonic()
    command = [str(exe), "--game", str(game), "--headless", "--no-launcher",
               "--renderer", "software", "--debug-port", str(args.port),
               "--memcard-dir", str(out / "saves")]
    report = {"command": command, "requested_seconds": args.seconds,
              "requested_frame": args.frames, "frame_target_reached": False, "events": events,
              "environment": {key: value for key, value in os.environ.items()
                              if key in ("PSX_HLE_SCHEDULER", "PSX_BIOS_HLE", "PSX_BIOS_HLE_KEEP_INTRO", "PSX_FORCE_INTERP",
                                         "PSX_OVERLAY_AUTOCOMPILE_OFF", "PSX_OVERLAY_CAPTURES")}}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (out / "runtime.log").open("wb") as log:
        process = subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=flags)
        connected = False
        next_capture = 0.0
        try:
            while process.poll() is None and time.monotonic() - started < args.seconds:
                elapsed = time.monotonic() - started
                try:
                    state = client.query("127.0.0.1", args.port, {"cmd": "frame"}, timeout=2)
                    connected = True
                    events.append({"seconds": round(elapsed, 2), "state": state})
                    if elapsed >= next_capture:
                        shot = out / f"frame-{len(events):03d}.png"
                        result = client.query("127.0.0.1", args.port,
                                              {"cmd": "screenshot_file", "path": shot.as_posix()}, timeout=2)
                        events[-1]["screenshot"] = result
                        next_capture = elapsed + 10
                    if args.frames is not None and state.get("frame", -1) >= args.frames:
                        report["frame_target_reached"] = True
                        break
                except (OSError, ValueError) as error:
                    events.append({"seconds": round(elapsed, 2), "error": str(error)})
                time.sleep(1)
            report["exit_before_cleanup"] = process.poll()
            if connected and process.poll() is None:
                for name in ("get_registers", "gpu_state", "cdrom_state", "cdrom_command_history",
                             "overlay_loader_status", "dirty_ram_stats", "pad_status", "first_failure"):
                    try:
                        diagnostics[name] = client.query("127.0.0.1", args.port, {"cmd": name}, timeout=3)
                    except (OSError, ValueError) as error:
                        diagnostics[name] = {"error": str(error)}
                try:
                    diagnostics["final_screenshot"] = client.query(
                        "127.0.0.1", args.port,
                        {"cmd": "screenshot_file", "path": (out / "final.png").as_posix()}, timeout=3)
                except (OSError, ValueError) as error:
                    diagnostics["final_screenshot"] = {"error": str(error)}
        finally:
            if connected and process.poll() is None:
                try:
                    client.query("127.0.0.1", args.port, {"cmd": "quit"}, timeout=2)
                except (OSError, ValueError):
                    pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            report.update(connected=connected, exit_code=process.returncode,
                          elapsed_seconds=round(time.monotonic() - started, 2), diagnostics=diagnostics)
            (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"connected": connected, "samples": len(events),
                      "exit_before_cleanup": report.get("exit_before_cleanup"),
                      "report": str(out / "report.json")}))
    return 0 if (connected and report.get("exit_before_cleanup") is None
                 and (args.frames is None or report["frame_target_reached"])) else 2


if __name__ == "__main__":
    raise SystemExit(main())
