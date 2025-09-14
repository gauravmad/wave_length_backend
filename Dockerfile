# Use official Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the entire app
COPY . .

# Expose the Flask-SocketIO port
EXPOSE 5000

# Start the Flask-SocketIO server
CMD ["python", "run.py"]