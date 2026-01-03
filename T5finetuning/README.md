# T5Gemma-2 Fine-tuning for RAG

Fine-tuning T5Gemma-2-1b-1b for extractive question-answering in a RAG (Retrieval-Augmented Generation) context.

## Quick Start (on Vast.ai A100)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Login to HuggingFace (for T5Gemma access)
huggingface-cli login

# 3. Prepare training data
python 01_prepare_data.py

# 4. Fine-tune the model
python 02_train.py

# 5. Test the fine-tuned model
python 03_evaluate.py

# 6. Export for deployment
python 04_export.py
```

## Files

| File | Purpose |
|------|---------|
| `requirements.txt` | Python dependencies |
| `01_prepare_data.py` | Downloads and formats training datasets |
| `02_train.py` | Main fine-tuning script with LoRA |
| `03_evaluate.py` | Tests model on sample queries |
| `04_export.py` | Exports model for local deployment |
| `config.py` | Central configuration |

## Expected Results

- Training time: ~1-2 hours on A100
- Model size: ~50MB (LoRA adapter only)
- Quality: Should answer questions from context accurately

## Deployment

After training, copy the adapter folder to your local machine:
```bash
scp -r ./output/t5gemma-lora-adapter user@your-mac:~/Projects/kel/python/
```
