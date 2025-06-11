# Gunicorn configuration file
# This ensures timeout and worker settings are applied even if render.yaml has issues

import os
bind = f"0.0.0.0:{os.environ.get('PORT', 10000)}"
workers = 1
worker_class = "sync"
timeout = 300  # 5 minutes
keepalive = 2
max_requests = 100
max_requests_jitter = 50
preload_app = True
worker_connections = 1000 