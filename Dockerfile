# Cache-bust: v2
FROM runpod/base:0.6.2-cuda12.2.0

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/hf_cache

# Ensure python symlink exists
RUN ln -sf $(which python3) /usr/local/bin/python 2>/dev/null || true

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install torch with CUDA 12.4 support
RUN python3 -m pip install --no-cache-dir torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124

# Clone ControlFoley
RUN git clone https://github.com/xiaomi-research/controlfoley.git /app/controlfoley && \
    cd /app/controlfoley && \
    python3 -m pip install --no-cache-dir -r requirements.txt 2>/dev/null || true

# Download ControlFoley weights
RUN python3 -m pip install --no-cache-dir huggingface_hub && \
    python3 -c "from huggingface_hub import snapshot_download; snapshot_download('YJX-Xiaomi/ControlFoley', local_dir='/app/controlfoley/model_weights')" || true

# Install ACE-Step
RUN python3 -m pip install --no-cache-dir git+https://github.com/ace-step/ACE-Step.git || true

# Install remaining deps
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Add controlfoley to Python path
ENV PYTHONPATH="/app/controlfoley:${PYTHONPATH}"

COPY handler.py /app/handler.py

CMD ["python3", "-u", "/app/handler.py"]
