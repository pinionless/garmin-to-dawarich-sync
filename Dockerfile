# ========================================================
# = Dockerfile
# ========================================================
# syntax=docker/dockerfile:1.4

# == Base Image ============================================
# Use an official Python runtime as a parent image
FROM python:3.12-slim-bookworm

# == Working Directory ============================================
# Set the working directory in the container
WORKDIR /usr/src/app

# == Dependencies ============================================
# Copy the requirements file into the container
COPY requirements.txt ./

# install git then install requirements (including git+…)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

# == Application Code ============================================
# Copy the current directory contents into the container at /usr/src/app
COPY . .

# == Network Configuration ============================================
# Make port 5000 available to the world outside this container
EXPOSE 5000

# == Environment Variables ============================================
# Define environment variables for Flask
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
# Ensure Python output is sent straight to terminal without being buffered
ENV PYTHONUNBUFFERED=1

# == Execution Command ============================================
# Run the Flask app (defined in the FLASK_APP environment variable, e.g., app.py)
# using the Flask development server.
CMD ["flask", "run"]