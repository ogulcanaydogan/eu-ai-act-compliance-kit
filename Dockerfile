FROM python:3.11-slim

LABEL maintainer="EU AI Act Compliance Kit Contributors"
LABEL description="Automated EU AI Act compliance checker"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Set entry point
ENTRYPOINT ["ai-act"]
CMD ["--help"]

# Metadata
ENV EU_AI_ACT_VERSION="0.1.0"
EXPOSE 8000
