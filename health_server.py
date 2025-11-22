"""
Simple health check server for Koyeb deployment.
Runs alongside main_runner.py in a separate thread.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import json
from datetime import datetime

# Track script status
health_status = {
    "status": "starting",
    "last_cycle": None,
    "cycles_completed": 0,
    "last_error": None,
    "started_at": datetime.now().isoformat()
}

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(health_status, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass

def start_health_server(port=8000):
    """Start health check server in background thread"""
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[Health] Server started on port {port}")
    return server

def update_health(status=None, last_cycle=None, error=None):
    """Update health status"""
    global health_status
    if status:
        health_status["status"] = status
    if last_cycle:
        health_status["last_cycle"] = last_cycle
        health_status["cycles_completed"] += 1
    if error:
        health_status["last_error"] = str(error)
