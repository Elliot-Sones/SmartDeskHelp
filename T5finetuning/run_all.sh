#!/bin/bash
set -e  # Exit on error

echo "========================================================"
echo "🚀 STARTING T5GEMMA-2 FINETUNING PIPELINE"
echo "========================================================"

# Step 0: Login to W&B (Optional, un-comment if you want to automate login)
# wandb login <YOUR_KEY>

# Step 1: Install Dependencies
echo -e "\n📦 Installing Dependencies..."
pip install -r requirements.txt

# Step 2: Generate Massive Dataset (150k+)
echo -e "\nChecking if data exists..."
if [ ! -f "data/train_hard.jsonl" ]; then
    echo "⚡ Generating 150k+ Training Examples (Downloading SQuAD)..."
    python 01_prepare_data.py
else
    echo "✅ Data already found! Skipping generation."
fi

# Step 3: Train the Model
echo -e "\n🔥 Starting Training (Batch Size 32 / Accum 8)..."
echo "   Effective Batch Size: 256"
python 02_train.py

echo -e "\n✅ PIPELINE COMPLETE!"
echo "   Download the 'output' folder now."
