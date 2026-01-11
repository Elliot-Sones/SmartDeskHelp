# Running Full Conversational Data Generation on Hosted GPU

## ✅ Local Test Results

**Status**: Test completed successfully!
- Generated: 100 examples (75 positive + 25 negative)
- Quality: Excellent conversational style
- Failures: 0
- Time: ~1.5 minutes

## Instructions for Hosted GPU (Vast.ai / RunPod / etc.)

### Step 1: Upload Files to GPU Instance

```bash
# From your local machine, upload the T5finetuning folder
scp -r /Users/elliot18/Desktop/Home/Projects/kel/T5finetuning root@<gpu-ip>:~/
```

Or use the web interface to upload the folder.

### Step 2: SSH into GPU Instance

```bash
ssh root@<gpu-ip>
cd ~/T5finetuning
```

### Step 3: Set Configuration for Full Run

Edit `01_prepare_data_conversational.py` line 39:

```python
# Change from:
NUM_EXAMPLES_TO_GENERATE = 100  # TEST MODE

# To:
NUM_EXAMPLES_TO_GENERATE = 150000  # FULL RUN (will auto-split 75% pos, 25% neg)
```

This will generate:
- **112,500 positive conversational examples** (75%)
- **37,500 negative conversational refusals** (25%)
- **Total: 150,000 examples**

### Step 4: Install Dependencies

```bash
pip install anthropic tqdm
```

### Step 5: Set API Key

```bash
export ANTHROPIC_API_KEY='sk-ant-api03-...'
```

### Step 6: Run Data Generation

```bash
python3 01_prepare_data_conversational.py
```

**Expected Duration**:
- 150K examples × 1.2 seconds/example = ~50 hours
- **WAIT!** That's too slow. Let me optimize...

### OPTIMIZED VERSION (Parallel Processing)

The current script processes sequentially. For the full run, you should parallelize:

#### Option A: Use Async Processing (Recommended)

I'll create an optimized version that batches requests. Claude's API supports concurrent requests.

#### Option B: Split the Work

Run positive and negative in parallel:

```bash
# Terminal 1 (Positive examples)
export GENERATE_TYPE="positive" && python3 01_prepare_data_conversational.py &

# Terminal 2 (Negative examples)
export GENERATE_TYPE="negative" && python3 01_prepare_data_conversational.py &
```

But this still won't help much. Let me create an async version...

---

## BETTER APPROACH: Async Batch Processing

I'll create a faster version that processes in parallel batches.

### Expected Stats for Full Run

**With Current Sequential Processing**:
- Time: ~50 hours ❌ Too slow
- Cost: ~$4.50

**With Async Batch Processing** (10 concurrent):
- Time: ~5 hours ✅ Much better
- Cost: ~$4.50 (same)

---

## What to Do Now

1. I'll create an optimized async version: `01_prepare_data_conversational_async.py`
2. You upload that to your GPU
3. Run it there (5 hours instead of 50)
4. Download the generated files
5. Run training

Sound good?
