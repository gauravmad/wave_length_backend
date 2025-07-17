from flask import Flask, send_from_directory
from app.config import Config
from app.routes.user_routes import user_bp
import os

def create_app():
    app = Flask(
        __name__,
        static_folder="../public",
        static_url_path="/"
    )
    app.config.from_object(Config)

    # Register Blueprints
    app.register_blueprint(user_bp, url_prefix="/api/user")

    # Serve index.html on /
    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app
