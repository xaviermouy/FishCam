#!/usr/bin/env python3
"""
FishCam Status API

Lightweight HTTP API serving system status data and a web dashboard.
Intended to run in background during WiFi (config) mode only.

Install dependency:
    pip install flask

Endpoints:
    GET  /           → serves dashboard.html (the web UI)
    GET  /status     → full system status as JSON
    POST /sync_rtc   → force NTP sync + push to WittyPi RTC

Usage:
    python3 run_api.py
"""

# pip install flask
from flask import Flask, jsonify, send_file, request

from pathlib import Path

import config
from system_status import collect
from wittypi_utils import sync_rtc_from_ntp


# ── One-time config load ──────────────────────────────────────────────────────

_script_dir  = Path(__file__).parent
_fishcam_id  = config.get_fishcam_id()
_paths       = config.get_paths()
_imu_cfg     = config.get_imu_settings()
_wittypi_cfg = config.get_wittypi_settings()
_buzzer_cfg  = config.get_buzzer_settings()
_port        = config.get_config().config.get('api', {}).get('port', 5000)


# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)


def _add_cors(response):
    """Add CORS headers so the dashboard can be loaded from any origin.

    Reflects the requesting Origin back rather than using '*', because
    '*' does not match 'null' (the origin sent by file:// pages in Chrome).
    Without this, opening dashboard.html from a local file blocks all fetches.

    Access-Control-Allow-Private-Network is required by Chrome's Private
    Network Access (PNA) policy when a local file fetches from a private IP.
    """
    origin = request.headers.get('Origin')
    response.headers['Access-Control-Allow-Origin']          = origin if origin else '*'
    response.headers['Access-Control-Allow-Credentials']     = 'true'
    response.headers['Access-Control-Allow-Private-Network'] = 'true'
    response.headers['Access-Control-Allow-Methods']         = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers']         = 'Content-Type'
    return response


app.after_request(_add_cors)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    """Serve the static dashboard HTML file."""
    html_path = _script_dir / 'dashboard.html'
    return send_file(str(html_path))


@app.route('/status')
def status():
    """Return full system status as JSON."""
    data = collect(
        _script_dir, _fishcam_id, _paths, _imu_cfg, _wittypi_cfg, _buzzer_cfg
    )

    # Tuples are not JSON-serialisable — convert to lists
    if isinstance(data.get('camera'), tuple):
        data['camera'] = list(data['camera'])
    if isinstance(data.get('imu_bus'), tuple):
        data['imu_bus'] = list(data['imu_bus'])

    return jsonify(data)


@app.route('/sync_rtc', methods=['POST'])
def sync_rtc():
    """Force NTP sync and push time to WittyPi RTC."""
    install_dir = _wittypi_cfg.get('install_dir', '/home/fishcam/Desktop/wittypi')
    try:
        ntp_ok, ntp_msg, rtc_ok, rtc_msg = sync_rtc_from_ntp(install_dir)
        return jsonify({
            'ntp_ok':  ntp_ok,
            'ntp_msg': ntp_msg,
            'rtc_ok':  rtc_ok,
            'rtc_msg': rtc_msg,
        })
    except Exception as e:
        return jsonify({
            'ntp_ok':  False,
            'ntp_msg': str(e),
            'rtc_ok':  False,
            'rtc_msg': 'sync_rtc_from_ntp raised an exception',
        }), 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=_port, threaded=True)
