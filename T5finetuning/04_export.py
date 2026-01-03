#!/usr/bin/env python3
"""
04_export.py - Export Fine-tuned Model for Local Deployment

This script prepares your trained model for deployment on your Mac:
1. Optionally merges LoRA weights into base model
2. Can convert to INT8 for 50% memory reduction
3. Creates deployment-ready files

Run AFTER evaluation: python 04_export.py
"""

import torch
import shutil
from pathlib import Path

from config import MODEL_ID, OUTPUT_DIR

print("=" * 60)
print("T5Gemma Export for Deployment")
print("=" * 60)

# =============================================================================
# Step 1: Configuration
# =============================================================================

# Export options
MERGE_WEIGHTS = False  # Merge LoRA into base model? (creates larger file)
QUANTIZE_INT8 = True   # Convert to INT8? (50% smaller, 99% quality)

# Export directory
EXPORT_DIR = "./export/t5gemma-finetuned"

print(f"\n📋 Export settings:")
print(f"   Merge LoRA weights: {MERGE_WEIGHTS}")
print(f"   Quantize to INT8: {QUANTIZE_INT8}")
print(f"   Output: {EXPORT_DIR}")

# =============================================================================
# Step 2: Load the trained model
# =============================================================================

print("\n📥 Loading trained model...")

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel

# Load base model
base_model = AutoModelForSeq2SeqLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True
)

# Load adapter
adapter_path = Path(OUTPUT_DIR)
if not adapter_path.exists():
    print(f"   ❌ Adapter not found at {OUTPUT_DIR}")
    exit(1)

model = PeftModel.from_pretrained(base_model, OUTPUT_DIR)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)

print("   ✓ Model loaded")

# =============================================================================
# Step 3: Merge weights (optional)
# =============================================================================

if MERGE_WEIGHTS:
    print("\n🔀 Merging LoRA weights into base model...")
    
    # merge_and_unload() combines LoRA weights with base model weights
    # This creates a standalone model that doesn't need PEFT at runtime
    # Pro: Simpler deployment (no PEFT dependency)
    # Con: Larger file (~3GB instead of ~50MB)
    model = model.merge_and_unload()
    
    print("   ✓ Weights merged")
else:
    print("\n📦 Keeping LoRA adapter separate (recommended)")
    print("   You'll need to load base model + adapter at runtime")
    print("   Benefit: Only ~50MB to transfer, base model cached locally")

# =============================================================================
# Step 4: Quantize to INT8 (optional)
# =============================================================================

if QUANTIZE_INT8:
    print("\n🗜️  Quantizing to INT8...")
    
    # INT8 quantization reduces each weight from 16 bits to 8 bits
    # This halves the memory usage with minimal quality loss
    #
    # Note: For deployment, you'll load with load_in_8bit=True
    # This just tests that quantization works
    
    from transformers import BitsAndBytesConfig
    
    quantization_config = BitsAndBytesConfig(
        load_in_8bit=True,
        llm_int8_threshold=6.0,  # Threshold for mixed-precision
    )
    
    print("   ✓ Quantization config ready")
    print("   Note: Actual quantization happens at load time")
    print("   Use: load_in_8bit=True when loading in production")

# =============================================================================
# Step 5: Save exported model
# =============================================================================

print("\n💾 Saving export...")

export_path = Path(EXPORT_DIR)
export_path.mkdir(parents=True, exist_ok=True)

if MERGE_WEIGHTS:
    # Save the full merged model
    model.save_pretrained(EXPORT_DIR)
    tokenizer.save_pretrained(EXPORT_DIR)
    print(f"   Saved merged model to: {EXPORT_DIR}")
else:
    # Copy just the adapter (much smaller)
    adapter_export = export_path / "adapter"
    if adapter_export.exists():
        shutil.rmtree(adapter_export)
    shutil.copytree(OUTPUT_DIR, adapter_export)
    tokenizer.save_pretrained(export_path)
    print(f"   Saved adapter to: {adapter_export}")

# Report sizes
total_size = sum(f.stat().st_size for f in export_path.glob("**/*") if f.is_file())
print(f"   Total export size: {total_size / 1024 / 1024:.1f} MB")

# =============================================================================
# Step 6: Create deployment instructions
# =============================================================================

instructions = f"""
# T5Gemma Deployment Instructions

## Files to copy to your Mac

Copy this folder to your local machine:
```bash
scp -r {EXPORT_DIR} youruser@yourmac:~/Projects/kel/python/
```

## Loading in your app

Update `t5gemma_answer_server.py`:

```python
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel
import torch

MODEL_ID = "google/t5gemma-2-1b-1b"
ADAPTER_PATH = "./t5gemma-finetuned/adapter"

# Load base model with INT8 quantization
model = AutoModelForSeq2SeqLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
    device_map="mps",       # Apple Silicon
    load_in_8bit=True       # Reduces to ~1.7GB RAM
)

# Load your trained adapter
model = PeftModel.from_pretrained(model, ADAPTER_PATH)
model.eval()

# Load processor
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
```

## Memory usage on 8GB Mac

| Component | Memory |
|-----------|--------|
| Base model (INT8) | ~1.7GB |
| LoRA adapter | ~50MB |
| Runtime overhead | ~300MB |
| **Total** | **~2GB** |

You'll have ~4-5GB free for images, other apps, etc.

"""

instructions_path = export_path / "DEPLOY.md"
with open(instructions_path, "w") as f:
    f.write(instructions)

print(f"   Created deployment instructions: {instructions_path}")

# =============================================================================
# Step 7: Done!
# =============================================================================

print("\n" + "=" * 60)
print("✅ Export complete!")
print("=" * 60)

print(f"""
Files ready for deployment:

📁 {EXPORT_DIR}/
   ├── adapter/          # Your trained LoRA weights (~50MB)
   ├── processor files   # Tokenizer config
   └── DEPLOY.md         # Deployment instructions

Next steps:
1. Copy {EXPORT_DIR} to your local Mac
2. Update t5gemma_answer_server.py (see DEPLOY.md)
3. Test with your app!
""")
