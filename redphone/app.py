"""Main Flask application for The Red Phone."""

import logging
import os
from datetime import datetime
from functools import wraps
from typing import Optional

from flask import Flask, jsonify, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit

from .config import config
from .discovery import discovery, Phone
from .quiet_hours import is_quiet_hours
from .openvpn import openvpn

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.get("logging.level", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "..", "ui", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "..", "ui", "static"),
)
app.config["SECRET_KEY"] = os.urandom(24)

socketio = SocketIO(app, cors_allowed_origins="*")


# Phone state
class PhoneState:
    IDLE = "idle"
    DIALING = "dialing"
    CALLING = "calling"
    RINGING = "ringing"
    IN_CALL = "in_call"


state = {
    "status": PhoneState.IDLE,
    "current_call": None,
    "handset_lifted": False,
}


# Context processor to inject debug vars into all templates
@app.context_processor
def inject_debug():
    return {
        "debug_enabled": config.debug_enabled,
        "debug_config": config.get("debug", {}),
        "current_call": state.get("current_call"),
    }


# ============================================================================
# Authentication
# ============================================================================


def admin_required(f):
    """Decorator requiring admin authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not config.get("admin.enabled", False):
            return jsonify({"error": "Admin interface disabled"}), 403

        auth = request.headers.get("Authorization", "")
        password = config.get("admin.password", "")

        if auth.replace("Bearer ", "") != password:
            return jsonify({"error": "Unauthorized"}), 401

        return f(*args, **kwargs)
    return decorated


# ============================================================================
# Web UI Routes
# ============================================================================


@app.route("/")
def index():
    """Main phone screen."""
    phones = discovery.get_phones()
    return render_template(
        "index.html",
        phones=phones,
        phone_name=config.phone_name,
        state=state["status"],
        handset_lifted=state["handset_lifted"],
        is_quiet=is_quiet_hours(),
        debug_enabled=config.debug_enabled,
        debug_config=config.get("debug", {}),
    )


@app.route("/call/<int:extension>")
def call_screen(extension: int):
    """Calling screen."""
    phones = discovery.get_phones()
    target = next((p for p in phones if p.extension == extension), None)

    if not target:
        return redirect(url_for("index"))

    # Check quiet hours
    if is_quiet_hours():
        return render_template(
            "confirm_call.html",
            target=target,
            phone_name=config.phone_name,
        )

    return render_template(
        "calling.html",
        target=target,
        phone_name=config.phone_name,
    )


@app.route("/confirm-call/<int:extension>", methods=["POST"])
def confirm_call(extension: int):
    """Confirm call during quiet hours."""
    phones = discovery.get_phones()
    target = next((p for p in phones if p.extension == extension), None)

    if not target:
        return redirect(url_for("index"))

    return render_template(
        "calling.html",
        target=target,
        phone_name=config.phone_name,
    )


@app.route("/incoming")
def incoming_screen():
    """Incoming call screen."""
    caller = state.get("current_call")
    return render_template(
        "incoming.html",
        caller=caller,
        phone_name=config.phone_name,
    )


@app.route("/in-call")
def in_call_screen():
    """Active call screen."""
    peer = state.get("current_call")
    return render_template(
        "in_call.html",
        peer=peer,
        phone_name=config.phone_name,
    )


@app.route("/setup")
def setup_screen():
    """WiFi setup screen (captive portal)."""
    return render_template("setup.html")


@app.route("/admin")
@admin_required
def admin_screen():
    """Admin interface."""
    return render_template(
        "admin.html",
        config=config.to_dict(),
        phones=discovery.get_phones(),
    )


# ============================================================================
# REST API
# ============================================================================


@app.route("/api/info")
def api_info():
    """Get this phone's info (for discovery)."""
    return jsonify({
        "name": config.phone_name,
        "extension": config.extension,
        "status": state["status"],
    })


@app.route("/api/status")
def api_status():
    """Get phone status."""
    return jsonify({
        "name": config.phone_name,
        "extension": config.extension,
        "status": state["status"],
        "handset_lifted": state["handset_lifted"],
        "current_call": state["current_call"],
        "is_quiet_hours": is_quiet_hours(),
    })


@app.route("/api/phones")
def api_phones():
    """List discovered phones."""
    phones = discovery.get_phones()
    return jsonify({
        "phones": [p.to_dict() for p in phones],
    })


@app.route("/api/config", methods=["GET"])
def api_get_config():
    """Get configuration."""
    return jsonify(config.to_dict())


@app.route("/api/config", methods=["PUT"])
@admin_required
def api_update_config():
    """Update configuration."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    for key, value in data.items():
        config.set(key, value)

    config.save()
    return jsonify({"status": "ok"})


@app.route("/api/vpn/status")
def api_vpn_status():
    """Get VPN connection status."""
    return jsonify({
        "connected": openvpn.is_connected,
        "vpn_ip": openvpn.get_vpn_ip(),
        "provider": config.get("network.vpn", "openvpn"),
    })


@app.route("/api/vpn/setup", methods=["POST"])
@admin_required
def api_vpn_setup():
    """Set up VPN credentials and config."""
    data = request.get_json()
    
    # Handle credentials
    if "username" in data and "password" in data:
        if not openvpn.setup_credentials(data["username"], data["password"]):
            return jsonify({"error": "Failed to save credentials"}), 500
    
    # Handle .ovpn config
    if "ovpn_config" in data:
        if not openvpn.setup_config(data["ovpn_config"]):
            return jsonify({"error": "Failed to save OpenVPN config"}), 500
    
    return jsonify({"status": "ok"})


@app.route("/api/vpn/connect", methods=["POST"])
@admin_required
def api_vpn_connect():
    """Start VPN connection."""
    if openvpn.start():
        return jsonify({"status": "connecting"})
    return jsonify({"error": "Failed to start VPN"}), 500


@app.route("/api/vpn/disconnect", methods=["POST"])
@admin_required
def api_vpn_disconnect():
    """Stop VPN connection."""
    openvpn.stop()
    return jsonify({"status": "disconnected"})


@app.route("/api/call", methods=["POST"])
def api_call():
    """Initiate a call."""
    data = request.get_json()
    extension = data.get("extension")

    if not extension:
        return jsonify({"error": "Extension required"}), 400

    phones = discovery.get_phones()
    target = next((p for p in phones if p.extension == extension), None)

    if not target:
        return jsonify({"error": "Phone not found"}), 404

    # TODO: Actually initiate SIP call via Asterisk
    state["status"] = PhoneState.CALLING
    state["current_call"] = target.to_dict()

    # Notify UI
    socketio.emit("state_change", {
        "status": state["status"],
        "target": state["current_call"],
    })

    return jsonify({"status": "calling", "target": target.to_dict()})


@app.route("/api/hangup", methods=["POST"])
def api_hangup():
    """Hang up current call."""
    # TODO: Actually hang up via Asterisk
    state["status"] = PhoneState.IDLE
    state["current_call"] = None

    socketio.emit("state_change", {"status": state["status"]})
    return jsonify({"status": "ok"})


@app.route("/api/answer", methods=["POST"])
def api_answer():
    """Answer incoming call."""
    if state["status"] != PhoneState.RINGING:
        return jsonify({"error": "No incoming call"}), 400

    # TODO: Actually answer via Asterisk
    state["status"] = PhoneState.IN_CALL

    socketio.emit("state_change", {"status": state["status"]})
    return jsonify({"status": "ok"})


# ============================================================================
# Debug API (when debug.enabled = true)
# ============================================================================


def debug_required(f):
    """Decorator requiring debug mode to be enabled."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not config.debug_enabled:
            return jsonify({"error": "Debug mode not enabled"}), 403
        return f(*args, **kwargs)
    return decorated


@app.route("/api/debug/state")
@debug_required
def api_debug_state():
    """Get full phone state for debugging."""
    return jsonify({
        "state": state,
        "config": {
            "phone_name": config.phone_name,
            "extension": config.extension,
            "vpn": config.get("network.vpn"),
            "debug": config.get("debug"),
        },
        "vpn_connected": openvpn.is_connected if config.get("network.vpn") == "openvpn" else None,
        "vpn_ip": openvpn.get_vpn_ip() if config.get("network.vpn") == "openvpn" else None,
        "discovered_phones": len(discovery.get_phones()),
        "is_quiet_hours": is_quiet_hours(),
    })


@app.route("/api/debug/simulate/handset", methods=["POST"])
@debug_required
def api_debug_simulate_handset():
    """Simulate handset lift/replace."""
    data = request.get_json() or {}
    lifted = data.get("lifted", not state["handset_lifted"])  # Toggle if not specified
    
    state["handset_lifted"] = lifted
    
    if lifted:
        # Simulate lifting handset
        if state["status"] == PhoneState.IDLE:
            state["status"] = PhoneState.DIALING
        elif state["status"] == PhoneState.RINGING:
            state["status"] = PhoneState.IN_CALL
    else:
        # Simulate replacing handset
        state["status"] = PhoneState.IDLE
        state["current_call"] = None
    
    socketio.emit("state_change", {
        "status": state["status"],
        "handset_lifted": state["handset_lifted"],
    })
    
    return jsonify({
        "status": "ok",
        "handset_lifted": state["handset_lifted"],
        "phone_state": state["status"],
    })


@app.route("/api/debug/simulate/incoming", methods=["POST"])
@debug_required
def api_debug_simulate_incoming():
    """Simulate incoming call."""
    data = request.get_json() or {}
    
    caller = {
        "name": data.get("caller_name", "Debug Caller"),
        "extension": data.get("caller_extension", 999),
        "hostname": data.get("caller_hostname", "debug-phone"),
        "ip": "127.0.0.1",
    }
    
    state["status"] = PhoneState.RINGING
    state["current_call"] = caller
    
    socketio.emit("state_change", {
        "status": state["status"],
        "caller": caller,
    })
    socketio.emit("incoming_call", {"caller": caller})
    
    return jsonify({
        "status": "ok",
        "phone_state": state["status"],
        "caller": caller,
    })


@app.route("/api/debug/simulate/call_answered", methods=["POST"])
@debug_required  
def api_debug_simulate_call_answered():
    """Simulate remote party answering our call."""
    if state["status"] != PhoneState.CALLING:
        return jsonify({"error": "Not in calling state"}), 400
    
    state["status"] = PhoneState.IN_CALL
    
    socketio.emit("state_change", {"status": state["status"]})
    
    return jsonify({
        "status": "ok",
        "phone_state": state["status"],
    })


@app.route("/api/debug/simulate/call_ended", methods=["POST"])
@debug_required
def api_debug_simulate_call_ended():
    """Simulate remote party ending the call."""
    state["status"] = PhoneState.IDLE
    state["current_call"] = None
    
    socketio.emit("state_change", {"status": state["status"]})
    socketio.emit("call_ended", {})
    
    return jsonify({
        "status": "ok",
        "phone_state": state["status"],
    })


@app.route("/api/debug/simulate/discovery", methods=["POST"])
@debug_required
def api_debug_simulate_discovery():
    """Simulate discovering a phone."""
    data = request.get_json() or {}
    
    from .discovery import Phone
    from datetime import datetime
    
    phone = Phone(
        name=data.get("name", "Debug Phone"),
        hostname=data.get("hostname", "debug-phone"),
        ip=data.get("ip", "10.0.0.99"),
        extension=data.get("extension", 199),
        status="online",
        last_seen=datetime.now(),
        source="debug",
    )
    
    # Add to discovery
    key = f"{phone.hostname}_{phone.extension}"
    discovery.phones[key] = phone
    
    # Notify UI
    socketio.emit("phones_updated", {
        "phones": [p.to_dict() for p in discovery.get_phones()],
    })
    
    return jsonify({
        "status": "ok",
        "phone": phone.to_dict(),
        "total_phones": len(discovery.get_phones()),
    })


@app.route("/api/debug/reset", methods=["POST"])
@debug_required
def api_debug_reset():
    """Reset phone to idle state."""
    state["status"] = PhoneState.IDLE
    state["current_call"] = None
    state["handset_lifted"] = False
    
    socketio.emit("state_change", {
        "status": state["status"],
        "handset_lifted": state["handset_lifted"],
    })
    
    return jsonify({"status": "ok", "state": state})


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "asterisk": "running",  # TODO: Actually check
        "vpn": "connected" if openvpn.is_connected else "disconnected",
        "vpn_ip": openvpn.get_vpn_ip(),
        "discovery": "active" if discovery._running else "stopped",
    })


# ============================================================================
# WebSocket Events
# ============================================================================


@socketio.on("connect")
def handle_connect():
    """Client connected."""
    emit("state_change", {
        "status": state["status"],
        "phones": [p.to_dict() for p in discovery.get_phones()],
    })


@socketio.on("handset_lifted")
def handle_handset_lifted():
    """Handset was lifted."""
    state["handset_lifted"] = True
    if state["status"] == PhoneState.IDLE:
        state["status"] = PhoneState.DIALING
    elif state["status"] == PhoneState.RINGING:
        # Answer the call
        state["status"] = PhoneState.IN_CALL

    emit("state_change", {"status": state["status"]}, broadcast=True)


@socketio.on("handset_replaced")
def handle_handset_replaced():
    """Handset was replaced."""
    state["handset_lifted"] = False
    state["status"] = PhoneState.IDLE
    state["current_call"] = None

    emit("state_change", {"status": state["status"]}, broadcast=True)


# ============================================================================
# Discovery Callbacks
# ============================================================================


def on_phones_updated(phones: list[Phone]):
    """Called when phone list changes."""
    socketio.emit("phones_updated", {
        "phones": [p.to_dict() for p in phones],
    })


# ============================================================================
# Startup
# ============================================================================


def main():
    """Run the application."""
    vpn_type = config.get("network.vpn", "tailscale")
    
    # Start VPN if configured
    if vpn_type == "openvpn":
        logger.info("Starting OpenVPN connection...")
        openvpn.start()
    elif vpn_type == "tailscale":
        logger.info("Using Tailscale VPN (ensure 'tailscale up' has been run)")
    else:
        logger.info("No VPN configured - using local network only")
    
    # Register discovery callback
    discovery.on_phones_updated(on_phones_updated)

    # Start discovery
    discovery.start()

    # Run Flask
    host = "0.0.0.0"
    port = 5000
    debug = config.get("logging.level") == "DEBUG"

    logger.info(f"Starting The Red Phone on {host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
