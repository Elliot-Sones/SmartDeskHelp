#!/bin/bash
# Comprehensive stress test with realistic, complex, combined queries
# Updated expectations for multi_query design

URL="http://localhost:8765/route"

test_query() {
    local query="$1"
    local expected_tool="$2"
    local description="$3"
    local result=$(curl -s -X POST "$URL" -H "Content-Type: application/json" -d "{\"query\": \"$query\"}" --max-time 120)
    local actual_tool=$(echo "$result" | jq -r '.tool')
    local args=$(echo "$result" | jq -c '.arguments')
    
    if [ "$actual_tool" == "$expected_tool" ]; then
        echo "✅ PASS: $description"
        echo "   Query: \"$query\""
        echo "   Tool: $actual_tool"
    else
        echo "❌ FAIL: $description"
        echo "   Query: \"$query\""
        echo "   Expected: $expected_tool"
        echo "   Got: $actual_tool"
    fi
    echo ""
}

echo "========================================================"
echo "MULTI-QUERY STRESS TEST (with updated expectations)"
echo "========================================================"
echo ""

echo "=== FILE SEARCH (Should route to local_query) ===" 
test_query "find my resume" "local_query" "Clear file search"
test_query "open the spreadsheet" "local_query" "File open request"
test_query "show me all my python scripts" "local_query" "File type filter"
test_query "open the most recent document I worked on" "local_query" "Recency file open"

echo "=== SYSTEM (Should route to local_query) ==="
test_query "my Mac is running really slow" "local_query" "Performance issue"
test_query "how much RAM do I have" "local_query" "RAM check"
test_query "am I running low on memory" "local_query" "Memory concern"
test_query "why is my fan spinning loud" "local_query" "Fan concern"

echo "=== WEB SEARCH (Should route to web_query) ==="
test_query "is there a new macOS update available" "web_query" "Update availability"
test_query "when does WWDC 2024 start" "web_query" "Event timing"
test_query "how do I fix a kernel panic" "web_query" "Tech support"
test_query "current Bitcoin price" "web_query" "Real-time data"

echo "=== AMBIGUOUS -> MULTI_QUERY (gather both system + web) ==="
test_query "is 8GB RAM enough for video editing" "multi_query" "Capability question"
test_query "can my computer run Stable Diffusion" "multi_query" "Software requirements"
test_query "compare my specs to Cyberpunk 2077 requirements" "multi_query" "Spec comparison"
test_query "what LLM should I download for my 8GB Mac" "multi_query" "LLM recommendation"
test_query "check if my system meets requirements for Xcode" "multi_query" "Requirements check"

echo "=== CONVERSATION (Should route to conversation) ==="
test_query "hey what's up" "conversation" "Greeting"
test_query "thanks for the help" "conversation" "Thanks"
test_query "bye see you later" "conversation" "Farewell"

echo "=== EDGE CASES ==="
test_query "find the weather report I downloaded" "local_query" "File with web keyword"
test_query "open my notes app" "local_query" "App launch"

echo "========================================================"
echo "STRESS TEST COMPLETE"
echo "========================================================"
