# Use Ubuntu as base image
FROM ubuntu:20.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Update and install system dependencies
RUN apt-get update && \
    apt-get install -y \
    python3.8 \
    python3.8-dev \
    python3.8-distutils \
    python3-pip \
    git \
    build-essential \
    wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install pip for Python 3.8
RUN wget https://bootstrap.pypa.io/get-pip.py && \
    python3.8 get-pip.py && \
    rm get-pip.py

# Set Python 3.8 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1

# Set work directory
WORKDIR /app

# Clone the repository
RUN git clone https://github.com/riboseqorg/RiboSeqOrg-DataPortal.git .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Run migrations
RUN python3 riboseqorg/manage.py migrate

# Expose port
EXPOSE 8000

# Start development server
CMD ["python3", "riboseqorg/manage.py", "runserver", "0.0.0.0:8000"]

