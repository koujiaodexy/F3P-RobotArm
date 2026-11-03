"""Bounded, single-process desktop WebSocket bridge for this Windows computer."""
import argparse
import json
import logging
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'artifacts/display-mirror-20261030/tools'
sys.path.insert(0, str(TOOLS / 'websockify-0.13.0'))
from websockify.auth_plugins import AuthenticationError, ExpectOrigin
from websockify.websocketproxy import LibProxyServer, ProxyRequestHandler

SERVICE_ID = 'f3p-desktop-proxy-v2'


class MirrorHandler(ProxyRequestHandler):
    def setup(self):
        self.request.settimeout(15)
        super().setup()

    def new_websocket_client(self):
        # HTTP headers have a deadline; an authenticated desktop may stay idle.
        # The WebSocket heartbeat handles that stage instead of the HTTP timeout.
        self.request.settimeout(None)
        return super().new_websocket_client()

    def parse_request(self):
        if not super().parse_request():
            return False
        if self.headers.get('Host') != self.server.expected_host:
            self.send_error(403, 'Invalid Host')
            self.close_connection = True
            return False
        return True

    def do_GET(self):
        if self.path == '/f3p-health':
            raw = json.dumps({'service': SERVICE_ID, 'pid': os.getpid(),
                              'target': '127.0.0.1:%d' % self.server.target_port,
                              'threaded': True}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        super().do_GET()


class MirrorServer(LibProxyServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, port=6080, target_port=5901, web=None, max_clients=16):
        self.slots = threading.BoundedSemaphore(max_clients)
        super().__init__(RequestHandlerClass=MirrorHandler, listen_host='127.0.0.1',
                         listen_port=port, target_host='127.0.0.1',
                         target_port=target_port,
                         web=str(web or TOOLS / 'noVNC-1.7.0'))
        self.expected_host = '127.0.0.1:%d' % self.server_address[1]
        # LibProxyServer 0.13 resets auth_plugin in its constructor. Restore it
        # explicitly, so switching to threads cannot silently disable Origin.
        self.auth_plugin = ExpectOrigin('http://' + self.expected_host)
        self.unix_listen = None
        self.file_only = True
        self.heartbeat = 20

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.sendall(b'HTTP/1.1 503 Busy\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (AuthenticationError, ConnectionError, TimeoutError)):
            logging.getLogger(__name__).info('Rejected or closed local desktop connection')
            return
        super().handle_error(request, client_address)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=6080)
    parser.add_argument('--target-port', type=int, default=5901)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        assert (TOOLS / 'noVNC-1.7.0/vnc.html').is_file()
        print(SERVICE_ID + ': ready; loopback only; bounded threads; Origin enforced')
        return
    logging.basicConfig(level=logging.INFO)
    with MirrorServer(args.port, args.target_port) as server:
        print(json.dumps({'service': SERVICE_ID, 'pid': os.getpid(),
                          'address': server.server_address}), flush=True)
        server.serve_forever(poll_interval=.5)


if __name__ == '__main__':
    main()
