#!/usr/bin/env python3
"""
Simple LLM connectivity test - a "hello world" ping test.
"""

import sys
import os
import pytest

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from proposal_analyzer.llm_client import query
from proposal_analyzer.config import get_llm_provider, get_local_llm_config

def test_llm_connectivity():
    """Simple ping test to check if LLM is available and responding."""
    
    # Get current provider
    provider = get_llm_provider()
    print(f"🔍 Testing LLM connectivity...")
    print(f"📡 Provider: {provider}")
    
    if provider == "local":
        config = get_local_llm_config()
        print(f"🤖 Model: {config['model_name']}")
        print(f"🌐 URL: {config['base_url']}")
        print(f"🔒 SSL Verify: {config['verify_ssl']}")
    else:
        print(f"🤖 Model: OpenAI (default)")
    
    # Simple test message
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Respond concisely."},
        {"role": "user", "content": "Hello! Please respond with exactly: 'LLM connectivity test successful'"}
    ]
    
    try:
        print("📤 Sending test message...")
        response = query(messages=messages, provider=provider)
        print(f"📥 Response received: {response}")
        
        if "successful" in response.lower():
            print("✅ LLM connectivity test PASSED")
            return True
        else:
            print("⚠️  LLM responded but with unexpected content")
            return False
            
    except Exception as e:
        print(f"❌ LLM connectivity test FAILED: {e}")
        return False

def standalone_test():
    """Standalone version for direct execution."""
    success = test_llm_connectivity()
    return success

if __name__ == "__main__":
    success = standalone_test()
    sys.exit(0 if success else 1) 