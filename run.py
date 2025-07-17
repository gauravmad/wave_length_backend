import sys
import os

# Add your app directory to the import path
sys.path.insert(0, os.path.abspath("app"))

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)