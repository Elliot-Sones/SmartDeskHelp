#!/usr/bin/env python3
"""
T5Gemma Answer Server
A lightweight HTTP server that loads Google's T5Gemma-2-1b-1b encoder-decoder model
and generates concise answers from context + query.

MULTIMODAL: Supports both text-only and text+image inputs.

Usage:
    python t5gemma_answer_server.py

The server runs on http://localhost:8766 and provides:
    POST /answer  - Takes context + query (+ optional image) and returns a concise answer
    POST /stream  - Same as /answer but streams tokens
    GET /health   - Health check endpoint
"""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Generator
import threading
import time
import base64
import io

# Configure logging
logging.basicConfig(level=logging.INFO, format='[T5Gemma] %(message)s')
logger = logging.getLogger(__name__)

# Model will be loaded lazily on first request
model = None
processor = None
model_lock = threading.Lock()
device = None

# Server config
PORT = 8766
MODEL_ID = "google/t5gemma-2-1b-1b"


def load_model() -> bool:
    """Load the T5Gemma-2-1b-1b model from HuggingFace"""
    global model, processor, device

    with model_lock:
        if model is not None:
            return True

        try:
            logger.info(f"Loading {MODEL_ID}...")

            from transformers import AutoProcessor, AutoModelForSeq2SeqLM
            import torch

            # Detect device
            if torch.backends.mps.is_available():
                device = "mps"  # Apple Silicon
            elif torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"

            logger.info(f"Using device: {device}")

            # Load processor (handles both text and images for multimodal)
            processor = AutoProcessor.from_pretrained(MODEL_ID)
            
            # Load model
            model = AutoModelForSeq2SeqLM.from_pretrained(
                MODEL_ID,
                torch_dtype=torch.float16 if device != "cpu" else torch.float32,
                device_map=device
            )

            logger.info("Model loaded successfully!")
            return True

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            import traceback
            traceback.print_exc()
            return False


def decode_image(image_data: Optional[str]) -> Optional['PIL.Image.Image']:
    """Decode base64 image data to PIL Image"""
    if not image_data:
        return None
    
    try:
        from PIL import Image
        
        # Handle data URL format
        if image_data.startswith('data:'):
            # Extract base64 part after comma
            image_data = image_data.split(',', 1)[1]
        
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        return image.convert('RGB')
    except Exception as e:
        logger.error(f"Failed to decode image: {e}")
        return None


def generate_answer(context: str, query: str, image_data: Optional[str] = None, max_tokens: int = 256) -> str:
    """
    Generate a concise answer given context, query, and optional image.
    Uses encoder-decoder architecture for efficient context processing.
    """
    global model, processor

    if not load_model():
        return "Error: Model not available"

    try:
        import torch

        # Decode image if provided
        image = decode_image(image_data)
        
        # Format prompt - T5Gemma works best with simpler direct prompts
        if image:
            # Multimodal: Image token followed by question
            if context and context.strip():
                prompt = f"<start_of_image> Context: {context}\n\nQuestion: {query}"
            else:
                prompt = f"<start_of_image> {query}"
        else:
            # Text-only: Direct question with context
            if context and context.strip():
                prompt = f"Context: {context}\n\nQuestion: {query}"
            else:
                prompt = query

        logger.info(f"Prompt ({len(prompt)} chars): {prompt[:200]}...")

        # Tokenize with processor (handles both text and images)
        if image:
            inputs = processor(
                text=prompt,
                images=image,
                return_tensors="pt",
                truncation=True,
                max_length=8192
            )
        else:
            inputs = processor(
                text=prompt,
                return_tensors="pt",
                truncation=True,
                max_length=8192
            )

        # Move to model device
        model_device = next(model.parameters()).device
        inputs = {k: v.to(model_device) for k, v in inputs.items()}
        
        logger.info(f"Input tokens: {inputs['input_ids'].shape}")

        # Get pad token id
        pad_token_id = None
        if hasattr(processor, 'tokenizer') and processor.tokenizer.pad_token_id:
            pad_token_id = processor.tokenizer.pad_token_id
        elif hasattr(processor, 'pad_token_id') and processor.pad_token_id:
            pad_token_id = processor.pad_token_id
        else:
            # Fallback to eos token
            if hasattr(processor, 'tokenizer'):
                pad_token_id = processor.tokenizer.eos_token_id
            else:
                pad_token_id = processor.eos_token_id

        # Generate
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,  # Deterministic for factual extraction
                num_beams=1,      # Greedy for speed
                pad_token_id=pad_token_id
            )
        
        logger.info(f"Output tokens: {outputs.shape}")
        logger.info(f"Output token ids: {outputs[0].tolist()[:20]}...")  # First 20 token ids

        # Decode response - try both with and without special tokens
        if hasattr(processor, 'tokenizer'):
            tokenizer = processor.tokenizer
        else:
            tokenizer = processor
            
        answer_with_special = tokenizer.decode(outputs[0], skip_special_tokens=False)
        answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        logger.info(f"Raw answer (with special): '{answer_with_special[:200]}...'")
        logger.info(f"Raw answer (no special): '{answer}'")

        return answer.strip()

    except Exception as e:
        logger.error(f"Error generating answer: {e}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}"


def stream_answer(context: str, query: str, image_data: Optional[str] = None, max_tokens: int = 256) -> Generator[str, None, None]:
    """
    Stream answer tokens one at a time.
    Uses TextIteratorStreamer for real-time output.
    """
    global model, processor

    if not load_model():
        yield "Error: Model not available"
        return

    try:
        import torch
        from transformers import TextIteratorStreamer
        from threading import Thread

        # Decode image if provided
        image = decode_image(image_data)
        
        # Format prompt
        if image:
            prompt = f"""<start_of_image> Answer the question based on the image and context below. Be concise and direct.

Context:
{context}

Question: {query}

Answer:"""
        else:
            prompt = f"""Answer the question based on the context below. Be concise and direct.

Context:
{context}

Question: {query}

Answer:"""

        # Tokenize
        if image:
            inputs = processor(
                text=prompt,
                images=image,
                return_tensors="pt",
                truncation=True,
                max_length=8192
            )
        else:
            inputs = processor(
                text=prompt,
                return_tensors="pt",
                truncation=True,
                max_length=8192
            )
        
        model_device = next(model.parameters()).device
        inputs = {k: v.to(model_device) for k, v in inputs.items()}

        # Set up streamer - use tokenizer if available
        tokenizer = processor.tokenizer if hasattr(processor, 'tokenizer') else processor
        streamer = TextIteratorStreamer(
            tokenizer,
            skip_special_tokens=True,
            skip_prompt=True
        )

        # Generation kwargs
        generation_kwargs = {
            **inputs,
            "max_new_tokens": max_tokens,
            "do_sample": False,
            "num_beams": 1,
            "streamer": streamer,
            "pad_token_id": tokenizer.pad_token_id if tokenizer.pad_token_id else tokenizer.eos_token_id
        }

        # Run generation in background thread
        thread = Thread(target=model.generate, kwargs=generation_kwargs)
        thread.start()

        # Yield tokens as they come
        for token in streamer:
            yield token

        thread.join()

    except Exception as e:
        logger.error(f"Error streaming answer: {e}")
        import traceback
        traceback.print_exc()
        yield f"Error: {str(e)}"


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the T5Gemma answer server"""

    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info("%s - %s" % (self.address_string(), format % args))

    def send_json(self, data: dict, status: int = 200):
        """Send a JSON response"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        """Handle GET requests"""
        if self.path == "/health":
            self.send_json({
                "status": "ok",
                "model": MODEL_ID,
                "loaded": model is not None,
                "multimodal": True
            })
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        """Handle POST requests"""

        if self.path == "/answer":
            # Non-streaming answer
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode()
                data = json.loads(body)

                context = data.get("context", "")
                query = data.get("query", "")
                image_data = data.get("image", None)  # Optional base64 image
                max_tokens = data.get("max_tokens", 256)

                if not query:
                    self.send_json({"error": "Missing query"}, 400)
                    return

                start_time = time.time()
                answer = generate_answer(context, query, image_data, max_tokens)
                elapsed_ms = int((time.time() - start_time) * 1000)

                self.send_json({
                    "answer": answer,
                    "elapsed_ms": elapsed_ms,
                    "success": True,
                    "multimodal": image_data is not None
                })

            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON"}, 400)
            except Exception as e:
                logger.error(f"Error handling /answer: {e}")
                self.send_json({"error": str(e)}, 500)

        elif self.path == "/stream":
            # Streaming answer
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode()
                data = json.loads(body)

                context = data.get("context", "")
                query = data.get("query", "")
                image_data = data.get("image", None)  # Optional base64 image
                max_tokens = data.get("max_tokens", 256)

                if not query:
                    self.send_json({"error": "Missing query"}, 400)
                    return

                # Send streaming response
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                for token in stream_answer(context, query, image_data, max_tokens):
                    # Send as SSE event
                    event_data = json.dumps({"token": token})
                    self.wfile.write(f"data: {event_data}\n\n".encode())
                    self.wfile.flush()

                # Send done event
                self.wfile.write(f"data: {json.dumps({'done': True})}\n\n".encode())
                self.wfile.flush()

            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON"}, 400)
            except Exception as e:
                logger.error(f"Error handling /stream: {e}")
                # Try to send error in stream format
                try:
                    self.wfile.write(f"data: {json.dumps({'error': str(e)})}\n\n".encode())
                except:
                    pass

        else:
            self.send_json({"error": "Not found"}, 404)


def main():
    """Start the T5Gemma answer server"""
    server = HTTPServer(("localhost", PORT), RequestHandler)

    logger.info(f"Starting T5Gemma Answer Server on http://localhost:{PORT}")
    logger.info("Endpoints:")
    logger.info("  POST /answer  - Generate answer from context + query (+ optional image)")
    logger.info("  POST /stream  - Stream answer tokens")
    logger.info("  GET  /health  - Health check")
    logger.info("")
    logger.info(f"Model: {MODEL_ID}")
    logger.info("Multimodal: Yes (supports text + image)")
    logger.info("Model will be loaded on first request...")
    logger.info("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
