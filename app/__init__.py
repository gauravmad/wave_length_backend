from flask import Flask, send_from_directory
from flask_socketio import SocketIO
from app.config import Config
from app.routes.user_routes import user_bp
from app.routes.send_otp import send_otp_bp
from app.socket.chat_socket import register_chat_events

socketio = SocketIO(cors_allowed_origins="*")

def create_app():
    app = Flask(
        __name__,
        static_folder="../public",
        static_url_path="/"
    )
    app.config.from_object(Config)

    # Register Blueprints
    app.register_blueprint(user_bp, url_prefix="/api/user")
    app.register_blueprint(send_otp_bp, url_prefix="/api/send-otp")

    # Init socketio with app ✅
    socketio.init_app(app, cors_allowed_origins="*")

    # Register chat events ✅
    register_chat_events(socketio)

    # Serve index.html on /
    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app
