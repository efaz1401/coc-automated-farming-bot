"""Entry point for Clash of Clans Farming Bot.

Usage:
  python main.py             # Launches modern Desktop Visual GUI
  python main.py --web       # Launches Browser Web UI server on http://localhost:8088
  python main.py --cli       # Run bot headless in terminal
  python main.py --once      # Single search+evaluate test, then exit
"""
from __future__ import annotations
import argparse
import logging
import os
import sys

os.makedirs("logs", exist_ok=True)
from bot import Bot, load_config


def run_cli(args):
    cfg = load_config(args.config)
    logging.basicConfig(
        level=getattr(logging, cfg.get("logging", {}).get("level", "INFO")),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(cfg.get("logging", {}).get("file", "logs/bot.log")),
        ],
    )
    bot = Bot(cfg)
    if args.once:
        if not bot.adb.ensure_connected():
            print("No ADB device found. Connect emulator: `adb connect 127.0.0.1:5555`.")
            return
        img, gray = bot.grab()
        print("Scouted Loot:", bot.vis.read_loot(img))
        print("\nTemplate Detections:")
        matches = bot.vis.find_all_matches(gray)
        for name in ("attack_button", "find_match", "next_button", "train_button"):
            match = matches.get(name) or bot.vis.find(gray, name)
            print(f"  {name} -> {match}")
        return
    bot.run()


def run_web(args):
    cfg = load_config(args.config)
    logging.basicConfig(
        level=getattr(logging, cfg.get('logging', {}).get('level', 'INFO')),
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(cfg.get('logging', {}).get('file', 'logs/bot.log')),
        ],
    )
    from web.server import WebServer
    import webbrowser

    server = WebServer(config_path=args.config, host="0.0.0.0", port=args.port)
    server.start(block=False)

    url = f"http://localhost:{server.port}"
    print("=" * 60)
    print(f"[*] CoC Farming Bot -- Web Control Suite running at: {url}")
    print("=" * 60)
    if getattr(args, "open", False):
        webbrowser.open(url)
    try:
        if server._thread:
            server._thread.join()
    except KeyboardInterrupt:
        server.stop()
        print("\nWeb server stopped.")


def main():
    ap = argparse.ArgumentParser(description="Clash of Clans Farming Bot")
    ap.add_argument("--config", default="config.yaml", help="Path to config file")
    ap.add_argument("--web", action="store_true", help="Launch Web UI in browser (default port 8088)")
    ap.add_argument("--port", type=int, default=8088, help="Web server port (default: 8088)")
    ap.add_argument("--open", action="store_true", help="Auto-open browser when starting web server")
    ap.add_argument("--cli", action="store_true", help="Run in command-line mode without GUI")
    ap.add_argument("--gui", action="store_true", help="Launch Desktop Visual GUI (default)")
    ap.add_argument("--once", action="store_true", help="Single search+evaluate, then exit")
    args = ap.parse_args()

    if args.web:
        run_web(args)
    elif args.cli or args.once:
        run_cli(args)
    else:
        # Default mode: Desktop Visual GUI
        try:
            import tkinter as tk
            from ui.app import BotGUI

            root = tk.Tk()
            app = BotGUI(root, config_path=args.config)
            root.mainloop()
        except Exception as e:
            print(f"Desktop GUI unavailable ({e}). Starting Web UI instead...")
            run_web(args)


if __name__ == "__main__":
    main()
