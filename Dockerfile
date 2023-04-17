# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY ./riboseqorg /app

RUN pip install --upgrade pip
RUN apt-get update && apt-get install -y tzdata build-essential
# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variable
ENV NAME World

# Run the command to start Django
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]