import os
import uuid
import runpod
import boto3
import torch
import torchaudio

# Configure R2 Client
s3 = boto3.client('s3',
    endpoint_url=f"https://{os.environ.get('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY')
)
BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')

# Global variables to track which model is in VRAM
current_loaded_model = None
model_instance = None

def load_model(model_type):
    """
    Dynamically swaps models in VRAM to keep GPU usage low.
    model_type: 'sfx' (ControlFoley) or 'music' (ACE-Step)
    """
    global current_loaded_model, model_instance
    
    if current_loaded_model == model_type:
        return model_instance
        
    print(f"[{model_type}] Model not in VRAM. Purging old model and loading...")
    
    # 1. Purge old model from VRAM
    if model_instance is not None:
        del model_instance
        torch.cuda.empty_cache()
    
    # 2. Download weights from R2 if not cached locally
    model_dir = f"/tmp/models/{model_type}"
    os.makedirs(model_dir, exist_ok=True)
    
    # In production: pull specific safetensors for Foley or ACE here
    # s3.download_file(BUCKET_NAME, f"models/{model_type}/model.safetensors", f"{model_dir}/model.safetensors")
    
    # 3. Load into VRAM
    if model_type == "sfx":
        print("Loading ControlFoley into VRAM...")
        # model_instance = FoleyModel.load(model_dir).to("cuda")
    elif model_type == "music":
        print("Loading ACE-Step into VRAM...")
        # model_instance = ACEStepModel.load(model_dir).to("cuda")
        
    current_loaded_model = model_type
    return model_instance

def generate_audio(job):
    job_input = job.get("input", {})
    req_type = job_input.get("type", "sfx")  # 'sfx' or 'music'
    prompt = job_input.get("prompt", "")
    duration = job_input.get("duration", 2.0)
    
    if not prompt:
        return {"error": "Missing prompt."}
        
    # 1. Ensure correct model is in VRAM
    model = load_model(req_type)
    
    # 2. Generate Audio 
    print(f"Generating {req_type}: '{prompt}' for {duration}s")
    
    # 3. Save to temp file
    output_filename = f"{uuid.uuid4()}.wav"
    output_path = f"/tmp/{output_filename}"
    
    # torchaudio.save(output_path, generated_waveform, 44100)
    
    # 4. Upload to R2 and get signed URL
    # s3.upload_file(output_path, BUCKET_NAME, f"generated/{output_filename}")
    # url = s3.generate_presigned_url('get_object', Params={'Bucket': BUCKET_NAME, 'Key': f"generated/{output_filename}"}, ExpiresIn=3600)
    
    url = "https://example.com/fake_audio.wav"
    
    return {
        "status": "success",
        "type": req_type,
        "url": url
    }

runpod.serverless.start({"handler": generate_audio})
