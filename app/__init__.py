from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from app.config import Config
from app.routes.user_routes import user_bp
from app.routes.send_otp import send_otp_bp
from app.routes.verify_otp import verify_otp_bp
from app.socket.chat_socket import register_chat_events

# Initialize SocketIO without app first
socketio = SocketIO(cors_allowed_origins="*")

def create_app():
    app = Flask(
        __name__,
        static_folder="../public",     # Serve static files (if any)
        static_url_path="/"           # Root path
    )

    app.config.from_object(Config)

    # ✅ Enable CORS for all routes including /api
    CORS(app, resources={r"/*": {"origins": "*"}})
    
    # Initialize SocketIO with the app
    socketio.init_app(app, cors_allowed_origins="*")

    # Register your API blueprints
    app.register_blueprint(user_bp, url_prefix="/api/user")
    app.register_blueprint(send_otp_bp, url_prefix="/api/send-otp")
    app.register_blueprint(verify_otp_bp, url_prefix="/api/verify-otp")

    # Register custom WebSocket events
    register_chat_events(socketio)

    # Serve index.html for root (optional for SPA)
    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app
