#!/usr/bin/env python3
from http.server import ThreadingHTTPServer

from panel_config import HOST, PORT
from web_handler import PanelRequestHandler


def main():
    server = ThreadingHTTPServer((HOST, PORT), PanelRequestHandler)
    print(f"panel listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
