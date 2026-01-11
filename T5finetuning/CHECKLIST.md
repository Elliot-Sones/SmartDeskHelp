# GPU Training Checklist

## ✅ Completed (Local)

- [x] Test conversational data generation (100 examples)
- [x] Verify output quality
- [x] Create async version for 10x speedup
- [x] Update training configuration
- [x] Prepare all scripts

## ⏳ To Do (On GPU)

### Before You Start
- [ ] Rent GPU instance (A100 recommended, 24GB VRAM)
- [ ] Get SSH access to GPU
- [ ] Budget: ~$24 ($4.50 Claude + $19.50 GPU)
- [ ] Time budget: ~13 hours

### Step 1: Upload & Setup
```bash
# From Mac
scp -r /Users/elliot18/Desktop/Home/Projects/kel/T5finetuning root@<gpu-ip>:~/
```

- [ ] Files uploaded to GPU
- [ ] SSH into GPU: `ssh root@<gpu-ip>`
- [ ] Navigate to folder: `cd ~/T5finetuning`

### Step 2: Install Dependencies
```bash
pip install anthropic tqdm transformers datasets peft accelerate bitsandbytes wandb
```

- [ ] Dependencies installed
- [ ] Verify: `python3 -c "import anthropic; import transformers"`

### Step 3: Set Environment
```bash
export ANTHROPIC_API_KEY='sk-ant-api03-...'

# Optional but recommended
huggingface-cli login   # For model access
wandb login             # For training tracking
```

- [ ] API key set
- [ ] HuggingFace login (optional)
- [ ] W&B login (optional)

### Step 4: Generate Conversational Data (~5 hours)
```bash
python3 01_prepare_data_conversational_async.py
```

**Expected output:**
- `data/generated/train_conversational_positive.jsonl` (~150 MB, 112,500 examples)
- `data/generated/train_conversational_negative.jsonl` (~50 MB, 37,500 examples)

- [ ] Script started
- [ ] Monitor progress (check file sizes growing)
- [ ] Positive file generated
- [ ] Negative file generated
- [ ] Total: 150,000 conversational examples

### Step 5: Train Model (~8 hours)
```bash
python3 02_train.py
```

**Expected phases:**
1. Phase 1: Extraction (37K examples, ~2.5 hrs)
2. Phase 2: Conversational (112.5K examples, ~4 hrs)
3. Phase 3: Refusals (37.5K examples, ~2 hrs)

- [ ] Phase 1 completed
- [ ] Phase 2 completed
- [ ] Phase 3 completed
- [ ] Adapter saved to `output/t5gemma-lora-adapter/`

### Step 6: Evaluate Model
```bash
python3 03_evaluate.py --adapter ./output/t5gemma-lora-adapter
```

- [ ] Evaluation run
- [ ] Quality looks good (conversational answers)

### Step 7: Export
```bash
python3 04_export.py
```

- [ ] Model exported to `export/t5gemma-finetuned/`
- [ ] Size verified (~50 MB adapter)

### Step 8: Download to Mac
```bash
# From Mac terminal
scp -r root@<gpu-ip>:~/T5finetuning/export/t5gemma-finetuned ~/Desktop/
```

- [ ] Adapter downloaded
- [ ] Verify files exist locally

### Step 9: Test Locally
```python
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel

# Load base model
model = AutoModelForSeq2SeqLM.from_pretrained(
    "google/t5gemma-2-1b-1b",
    device_map="mps",
    load_in_8bit=True
)

# Load your adapter
model = PeftModel.from_pretrained(model, "~/Desktop/t5gemma-finetuned/adapter")
tokenizer = AutoTokenizer.from_pretrained("google/t5gemma-2-1b-1b")

# Test
prompt = "Context:\nRAM usage 7.8GB/8GB\n\nQuestion: Why is my computer slow?"
inputs = tokenizer(prompt, return_tensors="pt")
outputs = model.generate(**inputs, max_new_tokens=100)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
```

- [ ] Model loads locally
- [ ] Generates conversational answers
- [ ] Quality verified

## 🎉 Done!

You now have a fine-tuned T5Gemma model that:
- Runs on your 8GB Mac M2
- Gives conversational answers
- Knows when to refuse
- Uses only ~2GB RAM

## Estimated Timeline

| Day | Tasks | Hours |
|-----|-------|-------|
| Day 1 | Upload, setup, start data gen | 1 hour work, 5 hours wait |
| Day 2 | Training (can run overnight) | 8 hours wait |
| Day 3 | Evaluate, export, download | 1 hour work |

**Total active work: ~2 hours**
**Total wall time: ~13 hours (mostly waiting)**

## Cost Tracking

- [ ] Data generation cost: $_____
- [ ] GPU rental cost: $_____
- [ ] Total: $_____ (expected ~$24)

---

**Ready? Start with Step 1!** 🚀
