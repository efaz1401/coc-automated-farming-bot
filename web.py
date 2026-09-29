"""Web server launcher for Clash of Clans Farming Bot.

Usage:
  python web.py                  # Starts server on http://localhost:8080
  python web.py --port 5000      # Custom port
  python web.py --open           # Automatically open in default browser
"""
from __future__ import annotations
import argparse
import sys
import webbrowser

from web.server import start_server


def main():
    parser = argparse.ArgumentParser(description="Clash of Clans Farming Bot — Web Control Suite")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8088, help="Port to listen on (default: 8088)")
    parser.add_argument("--open", action="store_true", help="Automatically open browser on start")
    args = parser.parse_args()

    from web.server import WebServer
    server = WebServer(config_path=args.config, host=args.host, port=args.port)
    server.start(block=False)

    url = f"http://localhost:{server.port}"
    print("=" * 60)
    print(f"[*] Clash of Clans Farming Bot -- Web Control Suite")
    print(f"[*] Access the UI at: {url}")
    print(f"[*] Press Ctrl+C to stop the web server.")
    print("=" * 60)

    if args.open:
        webbrowser.open(url)

    try:
        if server._thread:
            server._thread.join()
    except KeyboardInterrupt:
        server.stop()
        print("\nWeb server stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
