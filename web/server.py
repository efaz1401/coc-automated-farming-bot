"""Multi-threaded REST API and Web server for Clash of Clans Farming Bot."""
from __future__ import annotations
import collections
import datetime as dt
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
import os
import threading
import time
from urllib.parse import parse_qs, urlparse
import cv2
import numpy as np
import yaml

from bot.adb import AdbDevice
from bot.bot import Bot, load_config
from bot.vision import Vision

log = logging.getLogger("coc.web")

# In-memory circular buffer for web logs
MAX_LOG_HISTORY = 200
LOG_HISTORY = collections.deque(maxlen=MAX_LOG_HISTORY)
_log_lock = threading.Lock()


class WebLogHandler(logging.Handler):
    """Captures logs into circular buffer for web UI display."""
    def emit(self, record):
        try:
            msg = self.format(record)
            with _log_lock:
                LOG_HISTORY.append({
                    "time": dt.datetime.now().strftime("%H:%M:%S"),
                    "level": record.levelname,
                    "message": msg,
                })
        except Exception:
            pass


web_handler = WebLogHandler()
web_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
logging.getLogger().addHandler(web_handler)


class BotAPIHandler(SimpleHTTPRequestHandler):
    # Server instance references (populated by WebServer)
    bot: Bot = None
    config_path: str = "config.yaml"
    static_dir: str = ""

    def log_message(self, format, *args):
        # Suppress standard HTTP request logging in console to avoid clutter
        pass

    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 400):
        self.send_json({"error": message, "ok": False}, status=status)

    def read_json_body(self) -> dict:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len == 0:
            return {}
        raw = self.rfile.read(content_len).decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Static assets and SPA root
        if path == "/" or path == "/index.html":
            return self._serve_static("index.html", "text/html")
        elif path.startswith("/static/"):
            rel_file = path[len("/static/"):]
            return self._serve_static(rel_file)
        elif path.startswith("/assets/"):
            rel_file = path[len("/assets/"):]
            return self._serve_asset(rel_file)

        # API: Status & Stats
        elif path == "/api/status":
            stats = dict(self.bot.stats)
            started = stats.get("started")
            uptime = int((dt.datetime.now() - started).total_seconds()) if started else 0
            stats["uptime_sec"] = uptime
            if isinstance(started, (dt.datetime, dt.date)):
                stats["started"] = started.isoformat()

            data = {
                "ok": True,
                "is_running": self.bot.is_running(),
                "is_paused": self.bot.is_paused(),
                "phase": self.bot.stats.get("current_phase", "Idle"),
                "device": self.bot.adb.serial,
                "devices": AdbDevice.list_devices(),
                "stats": stats,
            }
            return self.send_json(data)

        # API: Screen Image
        elif path == "/api/screen.png":
            return self._serve_screen(query.get("overlay", ["0"])[0] == "1")

        # API: Config
        elif path == "/api/config":
            return self.send_json({"ok": True, "config": self.bot.cfg})

        # API: Devices
        elif path == "/api/devices":
            return self.send_json({"ok": True, "devices": AdbDevice.list_devices()})

        # API: Templates Status
        elif path == "/api/templates":
            tpls = self.bot.vis.get_template_status()
            digits = self.bot.vis.get_digit_status()
            return self.send_json({"ok": True, "templates": tpls, "digits": digits})

        # API: Logs
        elif path == "/api/logs":
            with _log_lock:
                logs = list(LOG_HISTORY)
            return self.send_json({"ok": True, "logs": logs})

        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/bot/start":
            if not self.bot.adb.ensure_connected():
                return self.send_error_json("No ADB device connected. Connect an emulator first.")
            self.bot.start_in_thread()
            return self.send_json({"ok": True, "message": "Bot started"})

        elif path == "/api/bot/pause":
            if self.bot.is_paused():
                self.bot.resume()
                msg = "Bot resumed"
            else:
                self.bot.pause()
                msg = "Bot paused"
            return self.send_json({"ok": True, "message": msg, "is_paused": self.bot.is_paused()})

        elif path == "/api/bot/stop":
            self.bot.stop()
            return self.send_json({"ok": True, "message": "Bot stopped"})

        elif path == "/api/bot/reset":
            self.bot.reset_stats()
            return self.send_json({"ok": True, "message": "Statistics reset"})

        elif path == "/api/screen/grab":
            try:
                if not self.bot.adb.ensure_connected():
                    return self.send_error_json("No ADB device connected")
                self.bot.grab()
                return self.send_json({"ok": True, "message": "Screen grabbed successfully"})
            except Exception as e:
                return self.send_error_json(f"Screen grab failed: {e}")

        elif path == "/api/devices/connect":
            body = self.read_json_body()
            addr = body.get("address", "").strip()
            if not addr:
                return self.send_error_json("Address required")
            ok, msg = AdbDevice.connect_device(addr)
            if ok:
                self.bot.adb.serial = addr
            return self.send_json({"ok": ok, "message": msg, "address": addr})

        elif path == "/api/devices/select":
            body = self.read_json_body()
            serial = body.get("serial", "").strip()
            if serial:
                self.bot.adb.serial = serial
                log.info("Web user switched active ADB serial to %s", serial)
            return self.send_json({"ok": True, "device": self.bot.adb.serial})

        elif path == "/api/config":
            body = self.read_json_body()
            new_cfg = body.get("config")
            if not new_cfg:
                return self.send_error_json("Config required")
            try:
                # Preserve active ADB serial so reload_config doesn't revert it
                if self.bot.adb.serial:
                    if "emulator" not in new_cfg:
                        new_cfg["emulator"] = {}
                    new_cfg["emulator"]["adb_serial"] = self.bot.adb.serial
                with open(self.config_path, "w", encoding="utf-8") as f:
                    yaml.dump(new_cfg, f, default_flow_style=False)
                self.bot.reload_config(new_cfg)
                return self.send_json({"ok": True, "message": "Settings saved and applied successfully"})
            except Exception as e:
                return self.send_error_json(f"Failed to save settings: {e}")

        elif path == "/api/logs/clear":
            with _log_lock:
                LOG_HISTORY.clear()
            return self.send_json({"ok": True, "message": "Logs cleared"})

        elif path == "/api/templates/crop":
            body = self.read_json_body()
            raw_name = body.get("name", "")
            target_name = os.path.basename(raw_name).strip()
            target_type = body.get("type", "button")  # button | digit | loot_box
            roi = body.get("roi")  # [x, y, w, h] px in 1280x720

            if not target_name:
                return self.send_error_json("Valid target name required")
            if not roi or len(roi) != 4:
                return self.send_error_json("Valid ROI [x, y, w, h] required")

            # Need last screen
            img = self._get_current_screen()
            if img is None:
                return self.send_error_json("No screen available. Grab screen first.")

            ox, oy, ow, oh = int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3])
            crop = img[oy:oy + oh, ox:ox + ow]
            if crop.size == 0:
                return self.send_error_json("Invalid crop boundaries")

            if target_type == "button":
                p = self.bot.cfg.get("templates", {}).get(target_name) or os.path.join("assets", f"{target_name}.png")
                os.makedirs(os.path.dirname(p) or "assets", exist_ok=True)
                cv2.imwrite(p, crop)
                self.bot.vis.reload_templates()
                return self.send_json({"ok": True, "message": f"Saved template '{target_name}'", "path": p})

            elif target_type == "digit":
                os.makedirs(os.path.join("assets", "digits"), exist_ok=True)
                p = os.path.join("assets", "digits", f"{target_name}.png")
                cv2.imwrite(p, crop)
                self.bot.vis.reload_templates()
                return self.send_json({"ok": True, "message": f"Saved digit '{target_name}'", "path": p})

            elif target_type == "loot_box":
                # Calibrate gold and auto-calculate offsets
                bx, by = round(ox / 1280, 3), round(oy / 720, 3)
                bw, bh = round(ow / 1280, 3), round(oh / 720, 3)
                boxes = {
                    "gold": [bx, by, bw, bh],
                    "elixir": [bx, round(by + 0.07, 3), bw, bh],
                    "dark": [bx, round(by + 0.14, 3), bw, bh],
                }
                if "vision" not in self.bot.cfg:
                    self.bot.cfg["vision"] = {}
                self.bot.cfg["vision"]["loot_boxes"] = boxes
                with open(self.config_path, "w", encoding="utf-8") as f:
                    yaml.dump(self.bot.cfg, f, default_flow_style=False)
                self.bot.reload_config(self.bot.cfg)
                return self.send_json({"ok": True, "message": "Calibrated loot boxes", "boxes": boxes})

            return self.send_error_json("Unknown crop target type")

        elif path == "/api/test/ocr":
            img = self._get_current_screen()
            if img is None:
                return self.send_error_json("No screen available")
            loot = self.bot.vis.read_loot(img)
            return self.send_json({"ok": True, "loot": loot})

        elif path == "/api/test/buttons":
            img = self._get_current_screen()
            if img is None:
                return self.send_error_json("No screen available")
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            matches = self.bot.vis.find_all_matches(gray)
            return self.send_json({"ok": True, "matches": matches})

        elif path == "/api/emergency/return_home":
            def _ret():
                try:
                    if self.bot.adb.ensure_connected():
                        m = self.bot.wait_for("return_home", timeout=3)
                        if m:
                            self.bot.adb.tap(m[0], m[1])
                        else:
                            fb = self.bot.f.get("return_home_fallback", [0.5, 0.92])
                            self.bot.tap_frac(fb[0], fb[1])
                except Exception as e:
                    log.warning("Emergency return home failed: %s", e)

            threading.Thread(target=_ret, daemon=True).start()
            return self.send_json({"ok": True, "message": "Emergency return home signal sent"})

        elif path == "/api/village/upgrade":
            if self.bot.is_running():
                return self.send_error_json("Bot is running. Pause or stop the bot before triggering manual upgrades.", 409)

            def _upg():
                try:
                    if self.bot.adb.ensure_connected():
                        self.bot.upgrade_village_now()
                except Exception as e:
                    log.warning("Village upgrade API error: %s", e)

            threading.Thread(target=_upg, daemon=True).start()
            return self.send_json({"ok": True, "message": "Village upgrade cycle initiated"})

        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

    # ---------- Internal Helpers ----------
    def _get_current_screen(self) -> np.ndarray | None:
        # Prefer live grab when bot is not running; fall back to cached file
        if not self.bot.is_running():
            try:
                if self.bot.adb.ensure_connected():
                    img, _ = self.bot.grab()
                    return img
            except Exception:
                pass
        # Fall back to last saved debug screenshot
        last_seen = os.path.join(self.bot.cfg.get("vision", {}).get("debug_dir", "logs/last_seen"), "screen.png")
        if os.path.exists(last_seen):
            img = cv2.imread(last_seen)
            if img is not None:
                return img
        return None

    def _serve_screen(self, with_overlay: bool = False):
        img = self._get_current_screen()
        if img is None:
            # Generate placeholder image
            img = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(img, "No Screen Feed — Click Grab Screen", (320, 360),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (150, 150, 150), 2)

        disp = img.copy()
        if with_overlay:
            H, W = disp.shape[:2]
            colors = {"gold": (0, 215, 255), "elixir": (200, 50, 255), "dark": (255, 100, 100)}
            for name, box in self.bot.vis.loot_boxes.items():
                x, y = int(box[0] * W), int(box[1] * H)
                w, h = int(box[2] * W), int(box[3] * H)
                c = colors.get(name, (0, 255, 0))
                cv2.rectangle(disp, (x, y), (x + w, y + h), c, 2)
                cv2.putText(disp, name.upper(), (x, max(15, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, c, 1)

        ok, buf = cv2.imencode(".png", disp)
        if not ok:
            self.send_response(500)
            self.end_headers()
            return

        body = buf.tobytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, rel_path: str, content_type: str | None = None):
        static_base = os.path.normpath(self.static_dir)
        full_path = os.path.normpath(os.path.join(static_base, rel_path.lstrip("/\\")))
        if not full_path.startswith(static_base) or not os.path.isfile(full_path):
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        if not content_type:
            content_type, _ = mimetypes.guess_type(full_path)
            if not content_type:
                content_type = "application/octet-stream"

        try:
            with open(full_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.end_headers()

    def _serve_asset(self, rel_path: str):
        assets_base = os.path.normpath(os.path.join(os.getcwd(), "assets"))
        full_path = os.path.normpath(os.path.join(assets_base, rel_path.lstrip("/\\")))
        if not full_path.startswith(assets_base) or not os.path.isfile(full_path):
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        content_type, _ = mimetypes.guess_type(full_path)
        if not content_type:
            content_type = "image/png"

        try:
            with open(full_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.end_headers()


class WebServer:
    def __init__(self, bot: Bot | None = None, config_path: str = "config.yaml", host: str = "0.0.0.0", port: int = 8088):
        self.config_path = config_path
        self.bot = bot or Bot(load_config(config_path))
        self.host = host
        self.port = port
        self.static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

        BotAPIHandler.bot = self.bot
        BotAPIHandler.config_path = self.config_path
        BotAPIHandler.static_dir = self.static_dir

        self.httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self, block: bool = True):
        # If requested port fails (e.g. port 8080 taken by Oracle TNSLSNR or Hyper-V reserved), fallback
        candidate_ports = [self.port]
        if self.port != 8088:
            candidate_ports.append(8088)
        if self.port != 8000:
            candidate_ports.append(8000)
        candidate_ports.append(0)  # OS dynamically selects free ephemeral port if all else fails

        bound = False
        for p in candidate_ports:
            try:
                self.httpd = ThreadingHTTPServer((self.host, p), BotAPIHandler)
                self.port = self.httpd.server_address[1]
                bound = True
                break
            except OSError as e:
                log.warning("Could not bind to %s:%d (%s), trying next port...", self.host, p, e)

        if not bound:
            raise RuntimeError(f"Could not bind WebServer on {self.host} to any available port.")

        self._running = True
        log.info("CoC Farming Bot Web Server running on http://%s:%d",
                 "localhost" if self.host == "0.0.0.0" else self.host, self.port)
        if block:
            try:
                self.httpd.serve_forever()
            except KeyboardInterrupt:
                self.stop()
        else:
            self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self._thread.start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self._running = False
            log.info("Web Server stopped")


def start_server(bot: Bot | None = None, config_path: str = "config.yaml", host: str = "0.0.0.0", port: int = 8088, block: bool = True) -> WebServer:
    server = WebServer(bot=bot, config_path=config_path, host=host, port=port)
    server.start(block=block)
    return server
