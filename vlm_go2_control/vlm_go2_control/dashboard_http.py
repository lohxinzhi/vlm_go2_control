"""Local HTTP endpoints for the ROS robot dashboard."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
from urllib.parse import urlsplit


class DashboardHTTPServer(ThreadingHTTPServer):
    """Serve the dashboard and pass validated requests to the ROS node."""

    daemon_threads = True

    def __init__(self, address, node, page):
        self.node = node
        self.token = secrets.token_urlsafe(32)
        self.page = page.replace('__CONTROL_TOKEN__', self.token).encode('utf-8')
        super().__init__(address, DashboardRequestHandler)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Handle camera polling, conversation history, and control commands."""

    def log_message(self, _format, *_args):
        pass

    def respond(self, status, content, content_type='application/json'):
        body = json.dumps(content).encode() if content_type == 'application/json' else content
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            self.respond(200, self.server.page, 'text/html; charset=utf-8')
        elif path == '/api/state':
            self.respond(200, self.server.node.dashboard_state())
        elif path in ('/camera.jpg', '/top-down.jpg'):
            image = self.server.node.camera_jpeg(path[1:-4])
            if image is None:
                self.respond(503, {'error': 'Waiting for camera images.'})
            else:
                self.respond(200, image, 'image/jpeg')
        else:
            self.respond(404, {'error': 'Not found.'})

    def do_POST(self):
        # Only the page served by this instance can issue robot commands.
        if not secrets.compare_digest(
                self.headers.get('X-Control-Token', ''), self.server.token):
            self.respond(403, {'error': 'Reload the dashboard to reconnect.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8192:
                raise ValueError('Invalid request size.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            path = urlsplit(self.path).path
            if path == '/api/chat':
                self.server.node.send_chat(data.get('text'))
            elif path == '/api/manual':
                self.server.node.set_manual_control(data.get('enabled'))
            elif path == '/api/teleop':
                direction = data.get('direction')
                if not isinstance(direction, str):
                    raise ValueError('Expected a direction.')
                self.server.node.set_direction(
                    direction, data.get('client_id'), data.get('sequence'))
            else:
                self.respond(404, {'error': 'Not found.'})
                return
            self.respond(200, {'ok': True})
        except (ValueError, TypeError, UnicodeDecodeError) as error:
            self.respond(400, {'error': str(error)})
        except RuntimeError as error:
            self.respond(409, {'error': str(error)})
