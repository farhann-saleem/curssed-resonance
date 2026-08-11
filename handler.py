import os
import uuid
import io
import base64
import runpod
import boto3
import torch
import torchaudio

# R2 Client
s3 = boto3.client('s3',
    endpoint_url=f"https://{os.environ.get('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY')
)
BUCKET_NAME = os.environ.get('R2_BUCKET_NAME', 'comfy')

# Global model state — hot-swap between SFX and music
current_model_type = None
sfx_model = None  # ControlFoley
music_model = None  # ACE-Step


def load_sfx_model():
    """Load ControlFoley for sound effect generation."""
    global sfx_model
    if sfx_model is not None:
        return sfx_model

    print("Loading ControlFoley model...")
    from controlfoley.inference_utils import ModelConfig, all_model_cfg
    from controlfoley.audio_model import create_audio_generation_model
    from controlfoley.feature_extractor import FeaturesUtils
    from lib.flow_matching import FlowMatching

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float32

    # Use default model config
    model_cfg = all_model_cfg["default"]
    net = create_audio_generation_model(model_cfg.model_name).to(device, dtype).eval()

    weights_path = "/app/controlfoley/model_weights/model.pt"
    if os.path.exists(weights_path):
        net.load_weights(torch.load(weights_path, map_location=device, weights_only=True))

    fm = FlowMatching(num_steps=model_cfg.num_steps)
    feature_utils = FeaturesUtils(device=device, dtype=dtype)

    sfx_model = {
        "net": net,
        "fm": fm,
        "feature_utils": feature_utils,
        "device": device,
        "cfg_strength": model_cfg.cfg_strength if hasattr(model_cfg, 'cfg_strength') else 4.5,
    }
    print("ControlFoley loaded.")
    return sfx_model


def load_music_model():
    """Load ACE-Step for music generation."""
    global music_model
    if music_model is not None:
        return music_model

    print("Loading ACE-Step model...")
    from acestep.pipeline_ace_step import ACEStepPipeline

    music_model = ACEStepPipeline(
        checkpoint_dir="/app/ace-step/checkpoints",
        dtype="bfloat16",
        torch_compile=False,
        cpu_offload=True,  # Save VRAM by offloading inactive stages
        overlapped_decode=True,
    )
    print("ACE-Step loaded.")
    return music_model


def _unload_model(model_type):
    """Free VRAM by unloading a model."""
    global sfx_model, music_model
    if model_type == "sfx" and sfx_model is not None:
        del sfx_model
        sfx_model = None
        torch.cuda.empty_cache()
    elif model_type == "music" and music_model is not None:
        del music_model
        music_model = None
        torch.cuda.empty_cache()


def generate_sfx(prompt, duration=2.0, negative_prompt="music, room tone, speech, reverb tail"):
    """Generate sound effect from text using ControlFoley T2A mode."""
    global current_model_type
    if current_model_type == "music":
        _unload_model("music")

    model = load_sfx_model()
    current_model_type = "sfx"

    from controlfoley.inference_utils import generate

    rng = torch.Generator(device=model["device"])
    rng.manual_seed(torch.randint(0, 2**32, (1,)).item())

    # T2A mode: no video/audio conditioning, just text prompt
    audios = generate(
        clip_frames=None,
        visual_frames=None,
        sync_frames=None,
        audio_frames=None,
        timbre_frames=None,
        timbre_duration=None,
        text=[prompt],
        negative_text=[negative_prompt],
        feature_utils=model["feature_utils"],
        net=model["net"],
        fm=model["fm"],
        rng=rng,
        cfg_strength=model["cfg_strength"],
    )

    # audios is a tensor [batch, channels, samples]
    audio = audios[0]  # first item in batch

    # Trim to requested duration
    sr = 16000  # ControlFoley default sample rate
    max_samples = int(duration * sr)
    if audio.shape[-1] > max_samples:
        audio = audio[..., :max_samples]

    # Encode to base64 WAV
    buf = io.BytesIO()
    torchaudio.save(buf, audio.cpu(), sr, format="wav")
    return base64.b64encode(buf.getvalue()).decode()


def generate_music(prompt, duration=30.0, lyrics="[instrumental]"):
    """Generate music from text using ACE-Step."""
    global current_model_type
    if current_model_type == "sfx":
        _unload_model("sfx")

    model = load_music_model()
    current_model_type = "music"

    result = model(
        audio_duration=duration,
        prompt=prompt,
        lyrics=lyrics,
        infer_step=27,
        guidance_scale=15.0,
        scheduler_type="euler",
        cfg_type="apg",
        omega=10.0,
        guidance_interval=0.5,
        guidance_interval_decay=0.0,
        min_guidance_scale=3.0,
        use_erg_tag=True,
        use_erg_lyric=False,
        use_erg_diffusion=True,
        seed=-1,  # random
    )

    # result contains generated audio path or tensor
    if isinstance(result, dict) and "audio" in result:
        audio = result["audio"]
        sr = result.get("sr", 44100)
    elif isinstance(result, tuple):
        sr, audio = result
    else:
        # ACE-Step saves to file, read it back
        import glob
        output_files = glob.glob("/tmp/ace_output_*.wav")
        if output_files:
            audio, sr = torchaudio.load(output_files[-1])
        else:
            raise Exception("ACE-Step produced no output")

    buf = io.BytesIO()
    if isinstance(audio, torch.Tensor):
        torchaudio.save(buf, audio.cpu(), sr, format="wav")
    else:
        raise Exception(f"Unexpected audio type: {type(audio)}")

    return base64.b64encode(buf.getvalue()).decode()


def handler(job):
    """
    Handles SFX and music generation requests.

    SFX (ControlFoley T2A):
    {"input": {"type": "sfx", "prompt": "glass breaking", "duration": 2.0}}

    Music (ACE-Step):
    {"input": {"type": "music", "prompt": "upbeat chiptune", "duration": 30, "lyrics": "[instrumental]"}}

    Batch SFX (from pipeline s7_assets.py):
    {"input": {"action": "controlfoley_batch", "queries": [{"prompt": "...", "duration": 1.0}]}}
    """
    job_input = job.get("input", {})
    action = job_input.get("action", "")
    req_type = job_input.get("type", "sfx")

    try:
        # ── Batch SFX (from pipeline) ───────────────────────────────────
        if action == "controlfoley_batch":
            queries = job_input.get("queries", [])
            if not queries:
                return {"error": "No queries provided."}

            results = []
            for i, q in enumerate(queries):
                prompt = q.get("prompt", "")
                duration = q.get("dur_s", q.get("duration", 1.0))
                negative = q.get("negative_prompt", "music, room tone, speech, reverb tail")

                if not prompt:
                    results.append({"error": "empty prompt"})
                    continue

                try:
                    audio_b64 = generate_sfx(prompt, duration, negative)
                    results.append({"audio_base64": audio_b64, "prompt": prompt})
                    print(f"  SFX [{i}]: '{prompt[:40]}' OK")
                except Exception as e:
                    print(f"  SFX [{i}]: '{prompt[:40]}' FAILED - {e}")
                    results.append({"error": str(e), "prompt": prompt})

            return {"results": results}

        # ── Single request ──────────────────────────────────────────────
        prompt = job_input.get("prompt", "")
        if not prompt:
            return {"error": "Missing prompt."}

        duration = job_input.get("duration", 2.0 if req_type == "sfx" else 30.0)

        if req_type == "sfx":
            negative = job_input.get("negative_prompt", "music, room tone, speech, reverb tail")
            audio_b64 = generate_sfx(prompt, duration, negative)
        elif req_type == "music":
            lyrics = job_input.get("lyrics", "[instrumental]")
            audio_b64 = generate_music(prompt, duration, lyrics)
        else:
            return {"error": f"Unknown type: {req_type}"}

        return {
            "status": "success",
            "type": req_type,
            "audio_base64": audio_b64,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
