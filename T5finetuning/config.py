"""
config.py - Central Configuration for T5Gemma Fine-tuning

This file contains all hyperparameters and settings in one place.
Modify these values to experiment with different configurations.
"""

# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

# The base model we're fine-tuning
# T5Gemma-2-1b-1b has 1B encoder + 1B decoder = ~2B total parameters
MODEL_ID = "google/t5gemma-2-1b-1b"

# Where to save the trained adapter
OUTPUT_DIR = "./output/t5gemma-lora-adapter"

# =============================================================================
# LORA CONFIGURATION
# =============================================================================

# LoRA Rank (r): Controls adapter capacity
# - Higher r = more parameters = better quality but slower/larger
# - Lower r = fewer parameters = faster but potentially lower quality
# Typical values: 4, 8, 16, 32, 64
# We use 32 for good quality on a reasoning task
LORA_R = 32

# LoRA Alpha: Scaling factor for LoRA weights
# Rule of thumb: Set to 2x the rank
# This affects the magnitude of the LoRA update
LORA_ALPHA = 64

# LoRA Dropout: Regularization to prevent overfitting
# 0.05-0.1 is typical for fine-tuning
LORA_DROPOUT = 0.05

# Which layers to apply LoRA to
# 
# KEY INSIGHT: We only need to train the DECODER, not the encoder!
# 
# The encoder already knows how to:
#   - Understand text structure
#   - Process images (OCR, visual understanding)
#   - Create good representations of content
# 
# What the decoder needs to LEARN:
#   - Cross-attention: "Which chunk has the answer?"
#   - Self-attention: "How to generate concise Q&A format"
#   - Output: "When to say 'Not found'"
# 
# For T5Gemma, decoder layer names include "decoder" prefix
# We target attention projections in decoder only
# VERIFIED T5Gemma-2-1b-1b LAYERS:
# The model uses "model.decoder.layers.X" structure
# There are NO explicit "cross_attn" layers (it's handled via the unified attention block)
# We target all linear projections in the decoder to maximize adaptation
LORA_TARGET_MODULES = [
    "q_proj", "v_proj", "k_proj", "o_proj", # Attention
    "gate_proj", "up_proj", "down_proj"     # MLP (Feed Forward)
]

# ALTERNATIVE: If the above patterns don't match T5Gemma's architecture,
# use these simpler patterns that let PEFT auto-detect decoder layers:
# LORA_TARGET_MODULES = ["q_proj", "v_proj"]
# Then set modules_to_save=[] and exclude encoder manually

# =============================================================================
# DATA CONFIGURATION
# =============================================================================

# How many training examples to use
# More data = better generalization but longer training
# 50K is a good balance for ~1.5hr training on A100
# 150K to cover the full SQuAD dataset (~130k)
NUM_TRAIN_EXAMPLES = 150000

# Ratio of "unanswerable" examples (model should say "Not found")
# This teaches the model to refuse when answer isn't in context
# 10% is good for high-quality retrieval systems (like LEANN)
# - High enough: Model learns refusal capability
# - Low enough: Model prioritizes finding answers over refusing
NEGATIVE_EXAMPLE_RATIO = 0.10

# Maximum input length (context + question)
# T5Gemma supports 128K, but we limit for training speed
# 1024 tokens ≈ ~750 words, enough for multi-chunk contexts
MAX_INPUT_LENGTH = 1024

# Maximum output length (answer)
# Answers should be concise - 128 tokens is plenty
MAX_OUTPUT_LENGTH = 128

# =============================================================================
# TRAINING CONFIGURATION
# =============================================================================

# Number of complete passes through the training data
# 3 epochs is standard - less may underfit, more may overfit
NUM_EPOCHS = 3

# How many examples to process at once (per GPU)
# A100 80GB MAXIMIZED SETTINGS:
# Batch 64 is safe with LoRA + Gradient Checkpointing
# Batch 128 is RISKY (might OOM crash)
BATCH_SIZE = 64

# Process this many batches before updating weights
# Effective batch size = BATCH_SIZE × GRADIENT_ACCUMULATION
# 64 × 2 = 128 effective batch size (Excellent stability)
GRADIENT_ACCUMULATION_STEPS = 2

# Learning rate: How big of a step to take during optimization
# 5e-4 is typical for LoRA fine-tuning (higher than full fine-tuning)
# Too high = unstable training, too low = slow convergence
LEARNING_RATE = 5e-4

# Warmup: Gradually increase learning rate at the start
# Prevents large early updates that could destabilize training
# 500 steps ≈ 5% of training
WARMUP_STEPS = 500

# Weight decay: L2 regularization to prevent overfitting
# 0.01 is standard
WEIGHT_DECAY = 0.01

# Mixed precision training: Use BF16 for speed + stability
# BF16 is PREFERRED over FP16 on A100 because:
#   - Same exponent range as FP32 (no overflow/underflow issues)
#   - A100 has native BF16 Tensor Cores
#   - More stable gradients during training
USE_BF16 = True
USE_FP16 = False  # Set to True only if GPU doesn't support BF16

# How often to log training metrics
# How often to log training metrics
# Set to 5 for very frequent updates (every few seconds)
LOGGING_STEPS = 5

# How often to save checkpoints
SAVE_STEPS = 1000

# =============================================================================
# WANDB CONFIGURATION (Optional experiment tracking)
# =============================================================================

WANDB_PROJECT = "t5gemma-rag-finetuning"
WANDB_RUN_NAME = "t5gemma-1b-1b-rag"

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

# This is how we format multi-chunk contexts
# Matches your production LEANN output format
CONTEXT_TEMPLATE = """Context:
{chunks}

Question: {question}"""

# Template for each chunk in the context
CHUNK_TEMPLATE = "[{index}] {source}: {content}"

# What the model should say when it can't find the answer
NO_ANSWER_RESPONSE = "Not found in provided context."
