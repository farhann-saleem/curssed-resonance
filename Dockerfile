# Cache-bust: clean build
FROM runpod/base:0.6.2-cuda12.2.0

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/hf_cache

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install torch with CUDA 12.4 support
RUN pip install --no-cache-dir torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124

# Clone ControlFoley
RUN git clone https://github.com/xiaomi-research/controlfoley.git /app/controlfoley && \
    cd /app/controlfoley && \
    pip install --no-cache-dir -r requirements.txt 2>/dev/null || true

# Download ControlFoley weights
RUN pip install --no-cache-dir huggingface_hub && \
    python -c "from huggingface_hub import snapshot_download; snapshot_download('YJX-Xiaomi/ControlFoley', local_dir='/app/controlfoley/model_weights')" || true

# Install ACE-Step
RUN pip install --no-cache-dir git+https://github.com/ace-step/ACE-Step.git || true

# Install remaining deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Add controlfoley to Python path
ENV PYTHONPATH="/app/controlfoley:${PYTHONPATH}"

COPY handler.py /app/handler.py

CMD ["python", "-u", "/app/handler.py"]
