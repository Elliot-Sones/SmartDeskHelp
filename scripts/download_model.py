import os
from huggingface_hub import snapshot_download, login

MODEL_ID = "google/functiongemma-270m-it"
TARGET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../resources/models/function-gemma-270m-it"))

def download_model():
    print(f"Downloading {MODEL_ID} to {TARGET_DIR}...")
    
    try:
        # Try downloading (works if already logged in via CLI)
        snapshot_download(
            repo_id=MODEL_ID,
            local_dir=TARGET_DIR,
            local_dir_use_symlinks=False,  # Important for bundling!
            ignore_patterns=["*.git*", "*.msgpack", "*.h5"] # Optional: exclude unneeded files if any
        )
        print("✓ Model downloaded successfully!")
        
    except Exception as e:
        print("\n❌ Error downloading model.")
        print(f"Details: {e}")
        
        if "401" in str(e) or "gated" in str(e).lower():
            print("\nauthentication REQUIRED:")
            print("This model is gated. We need your HuggingFace token.")
            token = input("Please paste your HF Access Token here: ").strip()
            
            if token:
                print("Logging in...")
                login(token=token)
                print("Retrying download...")
                snapshot_download(
                    repo_id=MODEL_ID,
                    local_dir=TARGET_DIR,
                    local_dir_use_symlinks=False
                )
                print("✓ Model downloaded successfully!")
            else:
                print("Skipped. Model not downloaded.")

if __name__ == "__main__":
    download_model()
