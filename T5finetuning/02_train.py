#!/usr/bin/env python3
"""
02_train.py - Fine-tune T5Gemma-2-1b-1b with LoRA

This is the main training script. It:
1. Loads the base T5Gemma model
2. Adds LoRA adapters (small trainable layers)
3. Trains on your prepared dataset
4. Saves the adapter weights

Architecture Recap:
- T5Gemma is an encoder-decoder model
- Encoder: Reads and compresses the context (FROZEN during training)
- Decoder: Generates the answer (TRAINED with LoRA)
- Cross-attention: Where decoder "looks at" encoder output (TRAINED with LoRA)

Run: python 02_train.py
Output: ./output/t5gemma-lora-adapter/
"""

import json
import torch
from pathlib import Path
from tqdm import tqdm

# =============================================================================
# Step 1: Import configuration and libraries
# =============================================================================

from config import (
    MODEL_ID,
    OUTPUT_DIR,
    LORA_R,
    LORA_ALPHA,
    LORA_DROPOUT,
    LORA_TARGET_MODULES,
    MAX_INPUT_LENGTH,
    MAX_OUTPUT_LENGTH,
    NUM_EPOCHS,
    BATCH_SIZE,
    GRADIENT_ACCUMULATION_STEPS,
    LEARNING_RATE,
    WARMUP_STEPS,
    WEIGHT_DECAY,
    USE_BF16,
    USE_FP16,
    LOGGING_STEPS,
    SAVE_STEPS,
    WANDB_PROJECT,
    WANDB_RUN_NAME,
)

print("=" * 60)
print("T5Gemma Fine-tuning with LoRA")
print("=" * 60)

# =============================================================================
# Step 2: Setup device and precision
# =============================================================================

print("\n🔧 Setting up environment...")

# Detect available hardware
if torch.cuda.is_available():
    device = "cuda"
    gpu_name = torch.cuda.get_device_name(0)
    gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"   GPU: {gpu_name} ({gpu_memory:.1f} GB)")
else:
    device = "cpu"
    print("   ⚠️  No GPU detected, training will be slow")

# Set random seed for reproducibility
# This ensures you get the same results if you run training again
torch.manual_seed(42)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(42)

# =============================================================================
# Step 3: Load the base model
# =============================================================================

print(f"\n📥 Loading base model: {MODEL_ID}")

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# Load the tokenizer (instead of processor, to avoid multimodal attribute error)
# AutoProcessor fails on text-only Gemma 3 models due to missing image_token_id
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
processor = None # Removed to prevent confusion, using tokenizer directly

# Load the model
# explicit device map handling for better compatibility (Mac/CPU/Vast)
if torch.cuda.is_available():
    device_map = "auto"
    torch_dtype = torch.float16
elif torch.backends.mps.is_available():
    device_map = None # MPS handles device placement manually usually or via .to()
    torch_dtype = torch.float16
else:
    device_map = None
    torch_dtype = torch.float32

model = AutoModelForSeq2SeqLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch_dtype,
    device_map=device_map,
    trust_remote_code=True
)

# If not using auto device map (e.g. Mac/CPU), move manually
if device_map is None:
    model.to(device)

# Report model size
total_params = sum(p.numel() for p in model.parameters())
print(f"   Model loaded: {total_params / 1e9:.2f}B parameters")
print(f"   Memory usage: {model.get_memory_footprint() / 1e9:.2f} GB")

# Print layer names to verify LoRA targets
print("\n🔍 Inspecting model layer names (for LoRA target verification)...")
decoder_layers = [name for name, _ in model.named_modules() if "decoder" in name.lower()]
print(f"   Found {len(decoder_layers)} decoder-related layers")
# Show a few examples
sample_layers = [l for l in decoder_layers if "attn" in l.lower()][:5]
for layer in sample_layers:
    print(f"   Example: {layer}")

# =============================================================================
# Step 4: Add LoRA adapters
# =============================================================================

print("\n🔧 Adding LoRA adapters...")

from peft import LoraConfig, get_peft_model, TaskType

# Configure LoRA
# LoRA works by adding small "adapter" matrices to specific layers
# Instead of updating the full weight matrix W, we update W + A×B
# where A and B are much smaller matrices (determined by LORA_R)

lora_config = LoraConfig(
    # Task type tells PEFT this is a sequence-to-sequence model
    # Different model types have different layer names
    task_type=TaskType.SEQ_2_SEQ_LM,
    
    # Rank (r): The dimension of the low-rank matrices
    # A 1000x1000 matrix becomes 1000×r and r×1000
    # Lower r = fewer parameters but potentially less capacity
    r=LORA_R,
    
    # Alpha: Scaling factor, affects the magnitude of LoRA updates
    # The actual update is scaled by (alpha / r)
    # Higher alpha = larger updates
    lora_alpha=LORA_ALPHA,
    
    # Dropout: Randomly zeros some LoRA activations during training
    # Helps prevent overfitting
    lora_dropout=LORA_DROPOUT,
    
    # Which model layers to add LoRA to
    # We target attention layers (q, k, v, o) AND MLP layers (gate, up, down)
    # This includes BOTH self-attention AND cross-attention in the decoder
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    
    # Don't merge LoRA weights during training
    # We need them separate so we can save just the adapter
    inference_mode=False,
)

# Apply LoRA to the model
# This wraps certain layers with LoRA adapters
# Original weights are frozen, only LoRA weights are trainable
# Apply LoRA to the model
model = get_peft_model(model, lora_config)

print("\n🔍 VERIFYING LoRA TARGETS (Critical Check):")
print("   The following layers are now TRAINABLE:")
trainable_layers = [n for n, p in model.named_parameters() if p.requires_grad]
for layer_name in trainable_layers[:10]: # Print first 10
    print(f"   ✅ {layer_name}")
if len(trainable_layers) > 10:
    print(f"   ... and {len(trainable_layers) - 10} more.")

if len(trainable_layers) == 0:
    print("\n   ❌ CRITICAL ERROR: No LoRA layers created! Check LORA_TARGET_MODULES config.")
    exit(1)
else:
    print(f"\n   ✅ Success! {len(trainable_layers)} LoRA adapters successfully attached.")

# Print trainable parameters
model.print_trainable_parameters()

# =============================================================================
# Step 5: Define data loading and tokenization functions
# =============================================================================

from datasets import Dataset

def load_phase_data(phase_file: str) -> Dataset:
    """Load a single phase JSONL file and convert to Dataset"""
    data_path = Path(f"./data/{phase_file}")
    if not data_path.exists():
        raise FileNotFoundError(f"Phase file not found: {data_path}")
    
    raw_data = []
    with open(data_path) as f:
        for line in f:
            raw_data.append(json.loads(line))
    
    return Dataset.from_list(raw_data)


def tokenize_function(examples):
    """Convert text examples to token IDs"""
    model_inputs = tokenizer(
        text=examples["input"],
        truncation=True,
        max_length=MAX_INPUT_LENGTH,
        padding="max_length",
        return_tensors=None
    )
    
    labels = tokenizer(
        text=examples["output"],
        truncation=True,
        max_length=MAX_OUTPUT_LENGTH,
        padding="max_length",
        return_tensors=None
    )
    
    model_inputs["labels"] = [
        [(l if l != tokenizer.pad_token_id else -100) for l in label]
        for label in labels["input_ids"]
    ]
    
    return model_inputs


# =============================================================================
# Step 6: Define phased training
# =============================================================================

# =============================================================================
# PHASE CONFIGURATION
# =============================================================================
#
# The order matters! Curriculum learning principle:
#   1. First teach WHAT to find (extraction)
#   2. Then teach HOW to format (chunks)
#   3. Then teach HOW to say it (conversational)
#   4. Finally teach WHEN to refuse (negatives)
#
# If you skip conversational phase, outputs will be terse extractions.
# If you only use conversational, model may hallucinate (no extraction foundation).

PHASES = [
    # Phase 1: Learn to extract answers (foundation)
    ("🟢 PHASE 1: EXTRACTION", "generated/layer1_squad.jsonl", "Basic Extraction"),

    # Phase 2: Learn chunk format and reasoning
    ("🟡 PHASE 2: REASONING & FORMAT", "generated/layer2_reasoning.jsonl", "Logic + complex formats"),

    # Phase 3: Learn conversational style (NEW - comment out to skip)
    ("🔵 PHASE 3: CONVERSATIONAL", "generated/train_conversational.jsonl", "Natural responses"),

    # Phase 4: Learn polite refusals
    ("🟠 PHASE 4: REFUSALS", "generated/layer5_negatives.jsonl", "Polite refusals"),
]

print("\n📋 Training Plan:")
for phase_name, phase_file, description in PHASES:
    try:
        ds = load_phase_data(phase_file)
        print(f"   {phase_name}: {len(ds):,} examples ({description})")
    except FileNotFoundError:
        print(f"   {phase_name}: ❌ File not found ({phase_file})")

# Data collator
from transformers import Seq2SeqTrainer, Seq2SeqTrainingArguments, DataCollatorForSeq2Seq

# Using standard DataCollatorWithPadding or manually handling padding because DataCollatorForSeq2Seq
# tries to call model.prepare_decoder_input_ids_from_labels which is broken on t5gemma2
from transformers import DataCollatorWithPadding

# NOTE: Since we already pre-processed labels in tokenize_function, we just need padding.
data_collator = DataCollatorForSeq2Seq(
    tokenizer=tokenizer,
    model=None, # PASSING NONE prevents the collator from calling the broken model method!
    padding=True,
    label_pad_token_id=-100
)

# Initialize W&B
try:
    import wandb
    wandb.init(
        project=WANDB_PROJECT,
        name=WANDB_RUN_NAME,
        config={
            "model": MODEL_ID,
            "lora_r": LORA_R,
            "lora_alpha": LORA_ALPHA,
            "batch_size": BATCH_SIZE,
            "learning_rate": LEARNING_RATE,
            "epochs_per_phase": 1,
            "total_phases": 3,
        }
    )
except:
    print("   W&B not available, continuing without logging")

# =============================================================================
# Step 7: Train each phase sequentially
# =============================================================================

print("\n" + "=" * 60)
print("🔥 STARTING PHASED TRAINING")
print("=" * 60)

global_step = 0

for phase_idx, (phase_name, phase_file, description) in enumerate(PHASES):
    print(f"\n{'='*60}")
    print(f"{phase_name}")
    print(f"   File: {phase_file}")
    print(f"   Description: {description}")
    print(f"   Expected: Loss will {'drop quickly' if phase_idx == 0 else 'bump then drop'}")
    print(f"{'='*60}")
    
    # Load and tokenize this phase's data
    try:
        phase_dataset = load_phase_data(phase_file)
    except FileNotFoundError as e:
        print(f"   ⚠️  Skipping phase: {e}")
        continue
    
    print(f"   Loading {len(phase_dataset):,} examples...")
    
    tokenized_dataset = phase_dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=phase_dataset.column_names,
        desc=f"Tokenizing {phase_name}"
    )
    
    # Training args for this phase (1 epoch per phase)
    phase_output_dir = f"{OUTPUT_DIR}/phase_{phase_idx + 1}"
    
    training_args = Seq2SeqTrainingArguments(
        output_dir=phase_output_dir,
        num_train_epochs=1,  # 1 epoch per phase
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        learning_rate=LEARNING_RATE,
        warmup_steps=WARMUP_STEPS if phase_idx == 0 else 100,  # Full warmup for phase 1, smaller for 2/3
        weight_decay=WEIGHT_DECAY,
        bf16=USE_BF16 and torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=USE_FP16 and torch.cuda.is_available() and not (USE_BF16 and torch.cuda.is_bf16_supported()),
        logging_steps=LOGGING_STEPS,
        logging_first_step=True,
        save_steps=SAVE_STEPS,
        save_total_limit=1,
        eval_strategy="no",
        report_to="wandb" if 'wandb' in dir() else "none",
        run_name=f"{WANDB_RUN_NAME}_phase{phase_idx + 1}",
        gradient_checkpointing=True,
        disable_tqdm=False,
    )
    
    # Create trainer for this phase
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
    )
    
    # Train!
    print(f"\n   � Training on {phase_name}...")
    trainer.train()
    
    # Log phase completion
    print(f"\n   ✅ {phase_name} complete!")
    
    # Save checkpoint after each phase
    checkpoint_path = f"{OUTPUT_DIR}/checkpoint_phase_{phase_idx + 1}"
    model.save_pretrained(checkpoint_path)
    tokenizer.save_pretrained(checkpoint_path)  # Required for resuming training
    print(f"   💾 Checkpoint saved: {checkpoint_path}")

# =============================================================================
# Step 8: Save final adapter
# =============================================================================

print("\n" + "=" * 60)
print("💾 Saving final trained adapter...")
print("=" * 60)

model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print(f"   Final adapter saved to: {OUTPUT_DIR}")

adapter_size = sum(f.stat().st_size for f in Path(OUTPUT_DIR).glob("**/*") if f.is_file())
print(f"   Total size: {adapter_size / 1024 / 1024:.1f} MB")

# =============================================================================
# Step 9: Done!
# =============================================================================

print("\n" + "=" * 60)
print("✅ ALL PHASES COMPLETE!")
print("=" * 60)
print(f"""
Training Summary:
  Phase 1 (Easy):   Basic Q&A format learned
  Phase 2 (Medium): Chunk format learned
  Phase 3 (Hard):   Multi-chunk selection + refusal learned

Adapter saved to: {OUTPUT_DIR}

Next steps:
  1. Run: python 03_evaluate.py (test the model)
  2. Run: python 04_export.py (prepare for deployment)
  3. Copy adapter to your local machine
""")

# Clean up
if torch.cuda.is_available():
    torch.cuda.empty_cache()
