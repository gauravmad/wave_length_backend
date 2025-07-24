from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    print("🚀 Starting Flask-SocketIO server...")
    print("📡 Socket.IO enabled with CORS: *")
    print("🌐 Server will be available at http://localhost:5000")
    socketio.run(
        app, 
        host="0.0.0.0", 
        port=5000, 
        debug=False,
        allow_unsafe_werkzeug=True
    )
