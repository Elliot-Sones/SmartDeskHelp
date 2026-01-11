#!/usr/bin/env python3
"""
Function-Gemma Server
A lightweight HTTP server that loads Google's function-gemma-270m-it
and provides tool routing decisions for the Kel AI assistant.

Usage:
    python function_gemma_server.py

The server runs on http://localhost:8765 and provides:
    POST /route - Takes a query and returns the best tool to use
    GET /health - Health check endpoint
"""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='[FunctionGemma] %(message)s')
logger = logging.getLogger(__name__)

# Model will be loaded lazily on first request
model = None
processor = None
model_lock = threading.Lock()

# File type categories for filtering
FILE_TYPES = ["pdf", "image", "document", "code", "video", "audio", "archive", "any"]

# Location categories for filtering  
LOCATIONS = ["documents", "downloads", "desktop", "photos", "projects", "home", "anywhere"]

# Date range options
DATE_RANGES = ["today", "week", "month", "year", "anytime"]

# ========================================
# KEYWORD PRE-FILTER (Enhanced with edge case fixes)
# Catches obvious queries BEFORE using the model
# This is instant (<1ms) and highly accurate
# ========================================

SYSTEM_KEYWORDS = [
    # Performance keywords
    "slow", "fast", "lag", "lagging", "freeze", "freezing", "hang", "hanging", 
    "stuck", "crash", "crashing", "performance",
    # Hardware keywords
    "ram", "memory", "cpu", "processor", "storage", "disk", "space", 
    "battery", "fan", "fans", "spinning", "loud", "noise", "noisy",
    "temperature", "hot", "heating", "overheating", "gpu", "graphics",
    # Specs keywords
    "specs", "spec", "hardware", "system", "computer", "machine",
    # Process keywords
    "process", "processes", "running", "using", "usage",
    # Questions about capability
    "can i run", "enough", "requirements", "capable"
]

WEB_KEYWORDS = [
    # Weather
    "weather", "temperature outside", "forecast", "rain",
    # News/Current events
    "news", "latest", "current", "today's",
    # Stock/Finance (external)
    "stock", "price of", "market", "bitcoin", "crypto",
    # General knowledge (external)
    "who is", "what is", "when was", "where is",
    # Time-based (external)
    "time in", "timezone",
    # Software/Updates (external)
    "update available", "new version", "latest version",
    # Events (external)
    "when does", "when is", "start date", "release date",
    # Technical help (external)
    "how do i", "how to", "fix", "tutorial", "guide",
    # Recommendations (external)
    "best", "recommend", "alternatives", "top 10", "vs"
]

FILE_KEYWORDS = [
    # Action verbs
    "find", "search", "locate", "where", "open", "show me", "look for", "do i have",
    "get", "pull up", "bring up", "load", "access",
    # File types
    "file", "document", "pdf", "photo", "picture", "image", "video", "spreadsheet",
    "presentation", "script", "code", "note", "notes",
    # Locations/containers
    "folder", "directory", "project", "download", "saved", 
    # Possessive/recent
    "my", "recent", "last", "latest", "yesterday", "today", "week",
    # File extensions
    ".pdf", ".doc", ".txt", ".json", ".py", ".js", ".csv", ".xls",
    # Implicit file actions
    "resume", "contract", "report", "tax", "invoice", "receipt"
]

# FIX #1: Casual/conversational queries → conversation
CASUAL_KEYWORDS = [
    "hello", "hi", "hey", "thanks", "thank you", "bye", "goodbye",
    "how are you", "what's up", "good morning", "good night",
    "help", "what can you do", "who are you", "your name",
    "just saying", "nevermind", "never mind", "don't worry"
]

# FIX #2: Personal memory queries → get_user_memory
MEMORY_KEYWORDS = [
    "about me", "do you know me", "what do you know about me",
    "my favorite", "my preference", "i like", "i prefer",
    "remember when", "last time", "you told me", "i told you",
    "my name", "my job", "my work", "my hobby", "my interest"
]

# FIX #4: Vision/screenshot queries → see
SEE_KEYWORDS = [
    "see", "look at", "what's on", "screen", "screenshot",
    "what do you see", "describe what", "what am i looking at",
    "what is this", "analyze this", "what's happening",
    "show me what", "look at my", "can you see"
]

# FIX #3: Multi-tool patterns → gather context from multiple sources
# These queries benefit from calling multiple tools and letting the LLM synthesize
MULTI_TOOL_PATTERNS = [
    # Capability/requirements questions (needs local specs + web info)
    ("enough for", ["local_query:system", "web_query"]),
    ("can my computer run", ["local_query:system", "web_query"]),
    ("can i run", ["local_query:system", "web_query"]),
    ("will it run on my", ["local_query:system", "web_query"]),
    ("requirements", ["local_query:system", "web_query"]),
    # Comparative queries
    ("compare my", ["local_query:system", "web_query"]),
    ("compare specs", ["local_query:system", "web_query"]),
    # Model/software recommendations  
    ("best model", ["local_query:system", "web_query"]),
    ("what model should i", ["local_query:system", "web_query"]),
    ("recommend a model", ["local_query:system", "web_query"]),
    ("which llm", ["local_query:system", "web_query"]),
]

# Ambiguity indicators - when these are present, gather more context
AMBIGUOUS_PATTERNS = [
    "is it", "should i", "can i", "will it", "enough", 
    "better", "best", "recommend", "which one"
]

# READ INTENT PATTERNS - queries asking about file CONTENTS (not just finding files)
# These should trigger deep content search via lazy chunking
READ_INTENT_PATTERNS = [
    "what does", "what's in", "what is in", "whats in",
    "say about", "says about", "contain", "contents of",
    "read", "show me what", "tell me what",
    "summarize", "summary of", "explain what",
    "describe what", "what are the", "list what",
    "details in", "information in", "data in"
]

# Stopwords to remove when extracting search terms
# These dilute embedding similarity
SEARCH_STOPWORDS = {
    # Question words
    "what", "where", "when", "who", "how", "why", "which", "whose",
    # Verbs/actions (common in questions)
    "does", "do", "did", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "can", "could", "will", "would", "should",
    "say", "says", "said", "tell", "show", "find", "get", "give",
    "contain", "contains", "include", "includes",
    # Prepositions/articles
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "with", "about",
    "from", "by", "as", "into", "through",
    # Pronouns
    "my", "your", "his", "her", "its", "our", "their", "me", "you", "it",
    # Common filler words
    "please", "just", "also", "some", "any", "all", "this", "that", "these", "those"
}

def extract_search_terms(query: str, username: str = None) -> list:
    """
    Extract key search terms from a natural language query.
    Removes stopwords and question patterns to get core terms for embedding search.
    If 'my' is present and username is provided, injects the username (digits removed).
    
    Example: "What does my resume say?" + username="elliot18"
           -> ["resume", "elliot"]
    """
    # Normalize
    text = query.lower().strip()
    
    # Remove punctuation
    text = ''.join(c if c.isalnum() or c.isspace() else ' ' for c in text)
    
    # Split into words
    words = text.split()
    
    # Check for "my" or implied ownership
    has_ownership = "my" in words
    
    # Remove stopwords
    terms = [w for w in words if w not in SEARCH_STOPWORDS and len(w) > 1]
    
    # Inject username if "my" was present
    if has_ownership and username:
        # Remove numbers from username as requested by user
        clean_username = ''.join([c for c in username if not c.isdigit()])
        if clean_username and len(clean_username) > 1:
            terms.append(clean_username)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_terms = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique_terms.append(term)
    
    return unique_terms


def keyword_pre_filter(query: str, username: str = None) -> Optional[dict]:

    """
    Fast keyword-based pre-filter for obvious non-file queries.
    Returns a tool call dict if a match is found, None otherwise.
    
    Now handles: casual chat, user memory, and multi-tool queries.
    """
    query_lower = query.lower()
    
    # FIX #1: Check for casual/conversational (no tool needed)
    if any(kw in query_lower for kw in CASUAL_KEYWORDS):
        # Don't trigger for file-related casual ("hello.txt")
        if not any(ext in query_lower for ext in [".txt", ".pdf", ".doc", ".py", ".js"]):
            logger.info(f"[PreFilter] Casual query detected → conversation")
            return {
                "name": "conversation",
                "arguments": {"type": "chat"}
            }
    
    # Check for see/screenshot queries (vision model)
    if any(kw in query_lower for kw in SEE_KEYWORDS):
        logger.info(f"[PreFilter] See query detected → see (vision)")
        return {
            "name": "see",
            "arguments": {"query": query}
        }
    
    # FIX #2: Check for user memory queries
    if any(kw in query_lower for kw in MEMORY_KEYWORDS):
        # Make sure it's not about files
        file_match_count = sum(1 for kw in FILE_KEYWORDS if kw in query_lower)
        if file_match_count == 0:
            logger.info(f"[PreFilter] Memory query detected → local_query(memory)")
            return {
                "name": "local_query",
                "arguments": {"intent": "recall", "target": "memory", "query": query}
            }
    
    # FIX #3: Check for multi-tool patterns
    for pattern, tools in MULTI_TOOL_PATTERNS:
        if pattern in query_lower:
            logger.info(f"[PreFilter] Multi-query pattern detected: {tools}")
            # Return multi_query to gather context from multiple tools
            return {
                "name": "multi_query",
                "arguments": {"query": query},
                "tools": tools,
                "combine_strategy": "parallel"
            }
    
    # Check for system info queries (with improved conflict resolution)
    system_match_count = sum(1 for kw in SYSTEM_KEYWORDS if kw in query_lower)
    if system_match_count >= 1:
        file_match_count = sum(1 for kw in FILE_KEYWORDS if kw in query_lower)
        # FIX: Prioritize files when both match and file is more specific
        if file_match_count == 0 or system_match_count > file_match_count:
            metrics = []
            if any(kw in query_lower for kw in ["slow", "fast", "lag", "freeze", "performance", "cpu", "processor"]):
                metrics.extend(["cpu", "processes"])
            if any(kw in query_lower for kw in ["ram", "memory"]):
                metrics.append("memory")
            if any(kw in query_lower for kw in ["storage", "disk", "space"]):
                metrics.append("disk")
            if any(kw in query_lower for kw in ["battery"]):
                metrics.append("battery")
            if any(kw in query_lower for kw in ["gpu", "graphics"]):
                metrics.append("gpu")
            
            if not metrics:
                metrics = ["all"]
            
            logger.info(f"[PreFilter] System query detected, metrics: {metrics}")
            return {
                "name": "local_query",
                "arguments": {"intent": "analyze", "target": "system", "query": query, "metrics": metrics}
            }
    
    # Check for web search queries (with improved conflict resolution)
    web_match_count = sum(1 for kw in WEB_KEYWORDS if kw in query_lower)
    if web_match_count >= 1:
        file_match_count = sum(1 for kw in FILE_KEYWORDS if kw in query_lower)
        # FIX: If both file and web keywords present, prefer file (local first)
        if file_match_count == 0:
            logger.info(f"[PreFilter] Web query detected")
            return {
                "name": "web_query",
                "arguments": {"query": query, "intent": "search"}
            }
        else:
            # Has file keywords too - this is about a local file (e.g., "weather report I downloaded")
            # Prioritize local_query since this is a local computer assistant
            logger.info(f"[PreFilter] Mixed file+web query → local_query (files)")
            return {
                "name": "local_query",
                "arguments": {"intent": "find", "target": "files", "query": query}
            }
    
    # Check for disk analysis queries
    if any(phrase in query_lower for phrase in [
        "what's taking space", "using space", "large files", "big files",
        "clean up", "cleanup", "free up space", "disk usage", "storage usage"
    ]):
        focus = "overview"
        if "large" in query_lower or "big" in query_lower:
            focus = "large_files"
        elif "clean" in query_lower or "free up" in query_lower:
            focus = "cleanup"
        
        logger.info(f"[PreFilter] Disk analysis query detected, focus: {focus}")
        return {
            "name": "local_query",
            "arguments": {"intent": "analyze", "target": "disk", "query": query}
        }
    
    # Check for ambiguous patterns - these benefit from multiple tools
    has_ambiguous = any(pattern in query_lower for pattern in AMBIGUOUS_PATTERNS)
    
    # Check for OPEN intent (user wants to open/launch a file)
    open_keywords = ["open", "launch", "load", "pull up", "bring up", "start", "run"]
    wants_to_open = any(kw in query_lower for kw in open_keywords)
    
    # Check for READ intent (user wants to know what's INSIDE a file)
    # This triggers deep content search via lazy chunking
    wants_to_read = any(pattern in query_lower for pattern in READ_INTENT_PATTERNS)
    
    # DEFAULT: Check for file-like queries (confident local)
    file_match_count = sum(1 for kw in FILE_KEYWORDS if kw in query_lower)
    if file_match_count >= 2 and not has_ambiguous:
        # Strong file signal - confident local query
        # Determine intent: read > open > find (in priority order)
        if wants_to_read:
            # Extract search terms for better embedding matching
            search_terms = extract_search_terms(query, username)
            
            args = {"intent": "read", "target": "files", "query": query}
            if search_terms:
                args["search_terms"] = search_terms
                
            logger.info(f"[PreFilter] Read intent detected → local_query(read) with terms: {search_terms}")
            return {
                "name": "local_query",
                "arguments": args
            }
        elif wants_to_open:
            intent = "open"
        else:
            intent = "find"
        search_terms = extract_search_terms(query, username)
        logger.info(f"[PreFilter] File query detected, matches: {file_match_count}, intent: {intent}, search_terms: {search_terms}")
        return {
            "name": "local_query",
            "arguments": {"intent": intent, "target": "files", "query": query, "search_terms": search_terms}
        }
    
    # AMBIGUOUS: For uncertain queries, gather context from multiple tools
    # Let the main LLM synthesize with rich context
    if has_ambiguous or (file_match_count == 1):
        logger.info(f"[PreFilter] Ambiguous query → multi_query (system + web)")
        return {
            "name": "multi_query",
            "arguments": {"query": query},
            "tools": ["local_query:system", "web_query"],
            "combine_strategy": "parallel"
        }
    
    # Final fallback: no strong signals, default to local_query
    search_terms = extract_search_terms(query, username)
    logger.info(f"[PreFilter] No match, defaulting to local_query, search_terms: {search_terms}")
    return {
        "name": "local_query",
        "arguments": {"intent": "find", "target": "files", "query": query, "search_terms": search_terms}
    }

# ========================================
# META-TOOL DEFINITIONS
# 3 consolidated tools instead of 8 specific ones
# FunctionGemma extracts rich parameters from user queries
# ========================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "local_query",
            "description": "Query anything on the user's local computer: files, system info, apps, or personal memories",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": ["find", "read", "open", "list", "analyze", "recall"],
                        "description": "What to do: find=search for something, read=get contents, open=launch, list=show items, analyze=examine system, recall=remember personal facts"
                    },
                    "target": {
                        "type": "string",
                        "enum": ["files", "system", "memory", "apps", "disk"],
                        "description": "What to query: files=documents/photos/etc, system=CPU/RAM/processes, memory=personal facts about user, apps=installed applications, disk=storage analysis"
                    },
                    "query": {
                        "type": "string",
                        "description": "The search terms or what to look for"
                    },
                    "file_types": {
                        "type": "array",
                        "items": {"type": "string", "enum": FILE_TYPES},
                        "description": "Filter by file type(s) when target is 'files'"
                    },
                    "location": {
                        "type": "string",
                        "enum": LOCATIONS,
                        "description": "Where to search (documents, downloads, desktop, etc)"
                    },
                    "date_range": {
                        "type": "string",
                        "enum": DATE_RANGES,
                        "description": "Filter by when (today, week, month, year)"
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["cpu", "memory", "disk", "processes", "battery", "gpu", "all"]},
                        "description": "Which system metrics when target is 'system'"
                    }
                },
                "required": ["intent", "target", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_query",
            "description": "Get information from the internet: weather, news, facts, prices, current events",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for on the web"
                    },
                    "intent": {
                        "type": "string",
                        "enum": ["search", "lookup", "check", "compare"],
                        "description": "search=general search, lookup=specific fact, check=verify status, compare=find options"
                    },
                    "topic": {
                        "type": "string",
                        "enum": ["weather", "news", "facts", "prices", "events", "general"],
                        "description": "Topic category to help focus the search"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "conversation",
            "description": "Normal conversation without any computer actions - greetings, thanks, questions about the assistant",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["greeting", "farewell", "thanks", "help", "chat"],
                        "description": "Type of conversational message"
                    }
                },
                "required": []
            }
        }
    }
]


def load_model():
    """Load the function-gemma model from HuggingFace"""
    global model, processor
    
    with model_lock:
        if model is not None:
            return True
            
        try:
            logger.info("Loading function-gemma-270m-it...")
            
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch
            import os

            # Determine path to bundled model
            # When packaged, the model should be in resources/models/function-gemma-270m-it
            # Relative to this script (python/function_gemma_server.py), it is ../resources/models/.../
            base_dir = os.path.dirname(os.path.abspath(__file__))
            bundled_path = os.path.abspath(os.path.join(base_dir, "../resources/models/function-gemma-270m-it"))
            
            model_id = "google/functiongemma-270m-it" # Fallback to HF hub
            
            if os.path.exists(bundled_path) and os.path.exists(os.path.join(bundled_path, "config.json")):
                logger.info(f"Found bundled model at: {bundled_path}")
                model_id = bundled_path
            else:
                logger.info("Bundled model not found, falling back to HuggingFace Hub...")
            
            # Detect device
            if torch.backends.mps.is_available():
                device = "mps"  # Apple Silicon
            elif torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"
            
            logger.info(f"Using device: {device}")
            
            # Load model and tokenizer
            processor = AutoTokenizer.from_pretrained(model_id)
            model = AutoModelForCausalLM.from_pretrained(
                model_id,
                torch_dtype=torch.float16 if device != "cpu" else torch.float32,
                device_map=device
            )
            
            logger.info("✓ Model loaded successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False


def route_query(query: str, username: str = None) -> Optional[dict]:
    """
    Hybrid routing: keyword pre-filter + FunctionGemma with few-shot examples.
    
    1. First tries keyword pre-filter (instant, catches system/web queries)
    2. Falls back to FunctionGemma for file operations (with parameter extraction)
    
    Returns a dict with:
        - name: The tool name
        - arguments: Dict of extracted parameters (file_types, location, date_range, etc.)
    """
    global model, processor
    
    # STEP 1: Try keyword pre-filter first (instant, <1ms)
    # Fast keyword-based pre-filter
    # This covers 80% of common queries instantly (0ms latency)
    pre_filter_result = keyword_pre_filter(query, username)

    if pre_filter_result is not None:
        logger.info(f"[Router] Pre-filter matched: {pre_filter_result['name']}")
        return pre_filter_result
    
    # STEP 2: Use FunctionGemma for file operations (with few-shot examples)
    if not load_model():
        return None
    
    try:
        import torch
        
        # Enhanced system prompt with few-shot examples (Solution #3)
        system_prompt = """You are a precise tool router for file operations. Given a user query, choose the right tool and extract parameters.

EXAMPLES:
- "find my resume" → search_files with query="resume", file_types=["pdf", "document"]
- "photos from last week" → search_files with query="photos", file_types=["image"], date_range="week"
- "open the project report" → open_file with query="project report", file_types=["pdf", "document"]
- "what's in my notes.txt" → read_file_content with query="notes.txt"
- "tax documents in downloads" → search_files with query="tax", file_types=["pdf"], location="downloads"
- "recent code changes" → search_files with query="code", file_types=["code"], date_range="week"

RULES:
- Use search_files to find files by name or description
- Use open_file to open a file with the default application  
- Use read_file_content to read and show what's inside a file
- If the query mentions file types (pdf, photos, documents), include file_types
- If the query mentions a location (downloads, desktop), include location
- If the query mentions time (today, this week, recent), include date_range

Always respond with a function call."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        # Apply chat template with tools
        inputs = processor.apply_chat_template(
            messages,
            tools=TOOLS,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True
        )
        
        # Move to same device as model
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        
        # Generate - increased max_new_tokens to accommodate arguments
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=150,  # Increased for richer output
                do_sample=False,
                pad_token_id=processor.eos_token_id
            )
        
        # Decode response
        response = processor.decode(outputs[0], skip_special_tokens=False)
        logger.info(f"Raw response: {response[-500:]}")  # Log last 500 chars for debugging
        
        # Extract full function call from response
        # Function-gemma uses <start_function_call> and <end_function_call> tokens
        if "<start_function_call>" in response:
            call_start = response.find("<start_function_call>") + len("<start_function_call>")
            call_end = response.find("<end_function_call>")
            if call_end > call_start:
                call_content = response[call_start:call_end].strip()
                # Parse the function call JSON
                try:
                    call_data = json.loads(call_content)
                    tool_name = call_data.get("name", "no_tool")
                    arguments = call_data.get("arguments", {})
                    
                    # Apply smart defaults based on query analysis
                    arguments = apply_smart_defaults(query, tool_name, arguments)
                    
                    logger.info(f"Parsed tool call: {tool_name} with args: {arguments}")
                    return {"name": tool_name, "arguments": arguments}
                    
                except json.JSONDecodeError:
                    # Try to extract function name and arguments separately
                    import re
                    name_match = re.search(r'"name"\s*:\s*"([^"]+)"', call_content)
                    if name_match:
                        tool_name = name_match.group(1)
                        # Try to extract arguments
                        args_match = re.search(r'"arguments"\s*:\s*(\{[^}]*\})', call_content)
                        arguments = {}
                        if args_match:
                            try:
                                arguments = json.loads(args_match.group(1))
                            except:
                                pass
                        arguments = apply_smart_defaults(query, tool_name, arguments)
                        return {"name": tool_name, "arguments": arguments}
        
        # Fallback: look for tool names in response and infer from query
        response_lower = response.lower()
        for tool in TOOLS:
            tool_name = tool["function"]["name"]
            if tool_name in response_lower:
                arguments = apply_smart_defaults(query, tool_name, {})
                return {"name": tool_name, "arguments": arguments}
        
        return {"name": "no_tool", "arguments": {}}
        
    except Exception as e:
        logger.error(f"Error during inference: {e}")
        import traceback
        traceback.print_exc()
        return None


def apply_smart_defaults(query: str, tool_name: str, arguments: dict) -> dict:
    """
    Apply smart defaults to arguments based on query analysis.
    This fills in gaps when FunctionGemma doesn't extract all parameters.
    """
    query_lower = query.lower()
    
    # Only apply defaults for file-related tools
    if tool_name not in ["search_files", "read_file_content", "open_file"]:
        return arguments
    
    # Infer file_types from query if not provided
    if "file_types" not in arguments or not arguments.get("file_types"):
        file_type_hints = []
        
        if any(word in query_lower for word in ["photo", "picture", "image", "selfie", "screenshot"]):
            file_type_hints.extend(["image"])
        if any(word in query_lower for word in ["pdf", "document", "report", "resume", "contract"]):
            file_type_hints.extend(["pdf", "document"])
        if any(word in query_lower for word in ["video", "movie", "recording"]):
            file_type_hints.extend(["video"])
        if any(word in query_lower for word in ["music", "song", "audio", "podcast"]):
            file_type_hints.extend(["audio"])
        if any(word in query_lower for word in ["code", "script", "program", "python", "javascript"]):
            file_type_hints.extend(["code"])
        if any(word in query_lower for word in ["zip", "archive", "compressed"]):
            file_type_hints.extend(["archive"])
        
        if file_type_hints:
            arguments["file_types"] = list(set(file_type_hints))
    
    # Infer location from query if not provided
    if "location" not in arguments or not arguments.get("location"):
        if "download" in query_lower:
            arguments["location"] = "downloads"
        elif "document" in query_lower and "file_types" not in arguments:
            arguments["location"] = "documents"
        elif "desktop" in query_lower:
            arguments["location"] = "desktop"
        elif any(word in query_lower for word in ["photo", "picture", "image"]):
            arguments["location"] = "photos"
        elif any(word in query_lower for word in ["project", "code", "repo"]):
            arguments["location"] = "projects"
    
    # Infer date_range from query if not provided
    if "date_range" not in arguments or not arguments.get("date_range"):
        if any(word in query_lower for word in ["today", "just now", "this morning"]):
            arguments["date_range"] = "today"
        elif any(word in query_lower for word in ["this week", "recent", "lately", "yesterday"]):
            arguments["date_range"] = "week"
        elif any(word in query_lower for word in ["this month", "last month"]):
            arguments["date_range"] = "month"
        elif any(word in query_lower for word in ["this year", "last year"]):
            arguments["date_range"] = "year"
    
    return arguments


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the function-gemma server"""
    
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
            self.send_json({"status": "ok", "model": "function-gemma-270m-it"})
        else:
            self.send_json({"error": "Not found"}, 404)
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == "/route":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode()
                data = json.loads(body)
                
                query = data.get("query", "")
                username = data.get("username", None)
                if not query:
                    self.send_json({"error": "Missing query"}, 400)
                    return
                
                result = route_query(query, username)
                
                if result:
                    # Return full tool call: {name, arguments}
                    self.send_json({
                        "tool": result["name"],
                        "arguments": result.get("arguments", {}),
                        "success": True
                    })
                else:
                    self.send_json({"error": "Model not available"}, 503)
                    
            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON"}, 400)
            except Exception as e:
                logger.error(f"Error handling request: {e}")
                self.send_json({"error": str(e)}, 500)
        
        elif self.path == "/search":
            # LEANN search endpoint
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode()
                data = json.loads(body)
                
                query = data.get("query", "")
                intent = data.get("intent", "read")
                source = data.get("source")
                folder = data.get("folder")
                top_k = data.get("top_k", 10)
                
                if not query:
                    self.send_json({"error": "Missing query"}, 400)
                    return
                
                # Import search module
                from leann_search import search
                result = search(query, intent=intent, source=source, folder=folder, top_k=top_k)
                self.send_json(result)
                
            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON"}, 400)
            except Exception as e:
                logger.error(f"Search error: {e}")
                self.send_json({"error": str(e), "results": []}, 500)
        
        elif self.path == "/index_status":
            # Check if LEANN index exists
            try:
                from leann_search import index_exists, INDEX_PATH
                exists = index_exists()
                self.send_json({
                    "indexed": exists,
                    "path": INDEX_PATH if exists else None
                })
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        
        elif self.path == "/system_info":
            # Real-time system information endpoint
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"
                data = json.loads(body) if body else {}
                
                # Get requested sections (default: all)
                sections = data.get("sections", ["all"])
                if isinstance(sections, str):
                    sections = [sections]
                
                # Import and call system_info module
                from system_info import get_system_info, format_system_info_for_llm
                
                info = get_system_info(sections)
                formatted = format_system_info_for_llm(info)
                
                self.send_json({
                    "success": True,
                    "data": info,
                    "formatted": formatted,
                })
                
            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON"}, 400)
            except ImportError as e:
                logger.error(f"system_info module not found: {e}")
                self.send_json({
                    "error": "System info module not available. Run: pip install psutil",
                    "success": False,
                }, 500)
            except Exception as e:
                logger.error(f"System info error: {e}")
                self.send_json({"error": str(e), "success": False}, 500)
        
        elif self.path == "/search_photos":
            # Hybrid photo search: keyword first, embedding fallback
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"
                data = json.loads(body) if body else {}
                
                query = data.get("query", "")
                keywords = data.get("keywords", [])
                limit = data.get("limit", 10)
                
                # If no keywords provided, extract from query
                if not keywords and query:
                    # Basic keyword extraction (Function Gemma should do this ideally)
                    keywords = [w.strip() for w in query.lower().split() 
                               if len(w.strip()) > 2 and w.strip() not in 
                               {"the", "and", "for", "with", "from", "photo", "picture", "image", "find", "show", "open"}]
                
                logger.info(f"Photo search: keywords={keywords}, limit={limit}")
                
                # Import photos scanner
                from indexing.photos_scanner import get_photos_scanner
                
                scanner = get_photos_scanner()
                
                if not scanner.is_available():
                    self.send_json({
                        "success": False,
                        "error": "Apple Photos not available. Install osxphotos: pip install osxphotos",
                        "results": [],
                    })
                    return
                
                # FAST PATH: Keyword search
                results = scanner.search_by_keywords(keywords, limit=limit)
                
                if len(results) >= 3:
                    # Found enough results with keywords
                    self.send_json({
                        "success": True,
                        "method": "keyword",
                        "results": [r.to_dict() for r in results],
                        "count": len(results),
                    })
                    return
                
                # SLOW PATH: Embedding fallback (if keyword search found < 3 results)
                if len(results) < 3 and query:
                    logger.info("Keyword search found few results, trying embedding fallback...")
                    
                    try:
                        from leann_search import search as leann_search
                        
                        embedding_results = leann_search(
                            query=query,
                            intent="find",
                            source="photos",
                            top_k=limit
                        )
                        
                        # Merge results (keyword results first, then embedding)
                        seen_paths = {r.file_path for r in results}
                        for er in embedding_results.get("results", []):
                            if er.get("file_path") not in seen_paths and len(results) < limit:
                                # Convert LEANN result to PhotoEntry-like dict
                                results.append(type('PhotoEntry', (), {
                                    'to_dict': lambda: er,
                                    'file_path': er.get('file_path'),
                                })())
                        
                        self.send_json({
                            "success": True,
                            "method": "hybrid",
                            "results": [r.to_dict() for r in results],
                            "count": len(results),
                        })
                        return
                        
                    except Exception as e:
                        logger.debug(f"Embedding fallback failed: {e}")
                
                # Return whatever we found
                self.send_json({
                    "success": True,
                    "method": "keyword",
                    "results": [r.to_dict() for r in results],
                    "count": len(results),
                })
                
            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON"}, 400)
            except ImportError as e:
                logger.error(f"Photos scanner not available: {e}")
                self.send_json({
                    "error": "Photos scanner not available. Run: pip install osxphotos",
                    "success": False,
                    "results": [],
                }, 500)
            except Exception as e:
                logger.error(f"Photo search error: {e}")
                import traceback
                traceback.print_exc()
                self.send_json({"error": str(e), "success": False, "results": []}, 500)
        
        else:
            self.send_json({"error": "Not found"}, 404)


def main():
    """Start the function-gemma server"""
    port = 8765
    server = HTTPServer(("localhost", port), RequestHandler)
    
    logger.info(f"Starting Function-Gemma server on http://localhost:{port}")
    logger.info("Endpoints:")
    logger.info("  POST /route         - Route a query to the best tool")
    logger.info("  POST /search        - Search LEANN index")
    logger.info("  POST /search_photos - Search Apple Photos (hybrid: keyword + embedding)")
    logger.info("  POST /system_info   - Get real-time system info (CPU, RAM, Disk, etc.)")
    logger.info("  POST /index_status  - Check LEANN index status")
    logger.info("  GET  /health        - Health check")
    logger.info("")
    logger.info("Model will be loaded on first request...")
    logger.info("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
