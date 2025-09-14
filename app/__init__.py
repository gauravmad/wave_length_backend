from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from app.config import Config
from app.routes.user_routes import user_bp
from app.routes.send_otp import send_otp_bp
from app.routes.verify_otp import verify_otp_bp
from app.routes.character_routes import character_bp
from app.routes.analyze_image import upload_image_bp
# from app.routes.speech_to_text import speech_to_text_bp
from app.routes.user_analytics import user_analytics_bp
from app.routes.categorization import user_categorization_bp
from app.routes.report import report_bp
from app.routes.chat import chat_bp
from app.routes.memo_routes import memo_bp
from app.socket.chat_socket import register_chat_events

# Initialize SocketIO without app first
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode='eventlet',  # 🔄 switch to eventlet
    logger=True,
    engineio_logger=True
)

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
    socketio.init_app(
        app, 
        cors_allowed_origins="*",
        async_mode='threading',
        logger=True,
        engineio_logger=True,
        ping_timeout=60,        # Increase timeout
        ping_interval=25        # Ping interval
    )

    # Register your API blueprints
    app.register_blueprint(user_bp, url_prefix="/api/user")
    app.register_blueprint(send_otp_bp, url_prefix="/api/send-otp")
    app.register_blueprint(verify_otp_bp, url_prefix="/api/verify-otp")
    # app.register_blueprint(character_bp,url_prefix="/api/character")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")
    app.register_blueprint(memo_bp, url_prefix="/api/memo")
    app.register_blueprint(upload_image_bp, url_prefix="/api/upload-image")
    app.register_blueprint(user_analytics_bp, url_prefix="/api/user-analytics")
    app.register_blueprint(user_categorization_bp, url_prefix="/api/user-categorization")
    app.register_blueprint(report_bp, url_prefix="/api/submit-report")
    # app.register_blueprint(speech_to_text_bp, url_prefix="/api/speech-to-text")

    # Register custom WebSocket events
    register_chat_events(socketio)

    # Serve index.html for root (optional for SPA)
    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    # Serve webhook test page
    @app.route("/webhook_test.html")
    def webhook_test():
        return send_from_directory(app.static_folder, "webhook_test.html")

    @app.route("/health")
    def health():
        return {"status": "healthy", "socketio": "enabled"} 

    return app
