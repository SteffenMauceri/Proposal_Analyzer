#!/usr/bin/env python3
"""
Test script to determine the actual context length of the configured LLM.
This test sends sequential numbers and asks the LLM to identify the highest number it saw.
"""

import pytest
import time
from functools import partial
from proposal_analyzer.llm_client import query
from proposal_analyzer.config import get_llm_provider, get_local_llm_config

# Try to import tiktoken for proper token counting
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    print("Warning: tiktoken not available. Using rough token estimates.")


class TestContextLength:
    """Test suite for determining LLM context length limits."""
    
    def _estimate_tokens(self, text: str, model_name: str = "gpt-4o") -> int:
        """
        Estimate token count for the given text.
        Uses tiktoken if available, otherwise rough estimation.
        """
        if TIKTOKEN_AVAILABLE:
            try:
                # Try to get encoding for the specific model
                if "gpt-4" in model_name.lower():
                    encoding = tiktoken.encoding_for_model("gpt-4")
                else:
                    # Default to cl100k_base which is used by GPT-4 and GPT-3.5-turbo
                    encoding = tiktoken.get_encoding("cl100k_base")
                return len(encoding.encode(text))
            except Exception:
                # Fallback to rough estimation
                pass
        
        # Rough estimation: ~4 characters per token on average
        return len(text) // 4
    
    def _test_specific_length_improved(self, target_tokens: int, model_name: str, provider: str):
        """
        Improved test that checks for both min and max numbers to detect truncation.
        Also uses proper token counting.
        
        Args:
            target_tokens: Target number of tokens to test
            model_name: LLM model name
            provider: LLM provider ('local' or 'openai')
        
        Returns:
            dict: Contains success status, actual tokens used, and diagnostic info
        """
        try:
            # Generate test data with special markers at beginning and end
            start_marker = "BEGINNING_MARKER_ALPHA"
            end_marker = "ENDING_MARKER_OMEGA"
            
            # Create a sequence that aims for the target token count
            # We'll iteratively build it to match the target
            base_content = f"{start_marker}, "
            numbers = []
            current_content = base_content
            
            # Build content to approximately match target tokens
            for i in range(1, 100000):  # Upper bound to prevent infinite loop
                test_number = str(i)
                test_addition = f"{test_number}, "
                
                # Check if adding this would exceed our target
                test_content = current_content + test_addition + end_marker
                estimated_tokens = self._estimate_tokens(test_content, model_name)
                
                if estimated_tokens >= target_tokens:
                    break
                    
                numbers.append(test_number)
                current_content += test_addition
            
            # Finalize content
            numbers_text = current_content + end_marker
            actual_estimated_tokens = self._estimate_tokens(numbers_text, model_name)
            
            # Expected values
            expected_min = "1"
            expected_max = str(len(numbers)) if numbers else "0"
            highest_number = len(numbers)
            
            # Create test prompt
            system_prompt = """You are a number analyzer. I will give you a sequence that contains:
1. A BEGINNING_MARKER_ALPHA at the start
2. Sequential numbers (1, 2, 3, etc.) 
3. An ENDING_MARKER_OMEGA at the end

Your task is to find these elements:
- The beginning marker (ignore any numbers in the marker text itself)
- The smallest number in the actual sequence
- The largest number in the actual sequence  
- The ending marker (ignore any numbers in the marker text itself)

IMPORTANT: Only count numbers that are part of the sequential list, NOT numbers within the marker text.

Respond in this exact format:
START: [YES/NO]
MIN: [smallest number or NONE]
MAX: [largest number or NONE] 
END: [YES/NO]"""
            
            user_prompt = f"""Here is the sequence:
{numbers_text}

Please analyze and respond in the specified format."""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Add rough token count of the messages
            total_prompt_tokens = self._estimate_tokens(system_prompt + user_prompt, model_name)
            
            # Call the LLM and measure wall clock time
            start_time = time.perf_counter()
            response = query(messages=messages, model=model_name, provider=provider)
            end_time = time.perf_counter()
            wall_clock_time = end_time - start_time
            
            # Parse response
            response_lines = [line.strip() for line in response.strip().split('\n')]
            
            found_start = False
            found_end = False
            found_min = None
            found_max = None
            
            for line in response_lines:
                if line.startswith("START:"):
                    found_start = "YES" in line.upper()
                elif line.startswith("MIN:"):
                    min_part = line.split(":", 1)[1].strip()
                    if min_part != "NONE" and min_part.isdigit():
                        found_min = int(min_part)
                elif line.startswith("MAX:"):
                    max_part = line.split(":", 1)[1].strip()
                    if max_part != "NONE" and max_part.isdigit():
                        found_max = int(max_part)
                elif line.startswith("END:"):
                    found_end = "YES" in line.upper()
            
            # Determine success
            success = (
                found_start and 
                found_end and 
                found_min == 1 and 
                found_max == highest_number
            )
            
            return {
                "success": success,
                "estimated_tokens": actual_estimated_tokens,
                "prompt_tokens": total_prompt_tokens,
                "wall_clock_time": wall_clock_time,
                "expected_min": 1,
                "expected_max": highest_number,
                "found_start": found_start,
                "found_end": found_end,
                "found_min": found_min,
                "found_max": found_max,
                "response": response[:200] + "..." if len(response) > 200 else response
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "estimated_tokens": 0,
                "prompt_tokens": 0,
                "wall_clock_time": 0.0,
                "expected_min": 0,
                "expected_max": 0,
                "found_start": False,
                "found_end": False,
                "found_min": None,
                "found_max": None,
                "response": ""
            }
    
    def test_context_length_quick(self):
        """Quick test with common context lengths to get a rough estimate."""
        provider = get_llm_provider()
        if provider == 'local':
            config = get_local_llm_config()
            model_name = config['model_name']
        else:
            model_name = 'gpt-4o'
        
        # Test common context lengths with improved method
        test_lengths = [4000, 8000, 16000, 32000, 64000, 128000]
        last_successful = 0
        
        print(f"🔍 Testing LLM Context Length (Improved Method)")
        print(f"🤖 Model: {model_name} (provider: {provider})")
        print(f"🔧 Token counting: {'tiktoken' if TIKTOKEN_AVAILABLE else 'estimated'}")
        print()
        
        for length in test_lengths:
            print(f"Testing {length:,} tokens...", end=" ")
            result = self._test_specific_length_improved(length, model_name, provider)
            
            if result["success"]:
                last_successful = length
                print(f"✅ SUCCESS")
                print(f"   📊 Estimated tokens: {result['estimated_tokens']:,}")
                print(f"   ⏱️  Wall clock time: {result['wall_clock_time']:.2f} seconds")
                print(f"   🚀 Tokens/second: {result['estimated_tokens'] / result['wall_clock_time']:,.0f}")
                print(f"   🔍 Found START: {result['found_start']}, END: {result['found_end']}")
                print(f"   🔢 Range: {result['found_min']} to {result['found_max']} (expected: {result['expected_min']} to {result['expected_max']})")
            else:
                print(f"❌ FAILED")
                print(f"   📊 Estimated tokens: {result['estimated_tokens']:,}")
                print(f"   ⏱️  Wall clock time: {result['wall_clock_time']:.2f} seconds")
                if result['wall_clock_time'] > 0:
                    print(f"   🚀 Tokens/second: {result['estimated_tokens'] / result['wall_clock_time']:,.0f}")
                print(f"   🔍 Found START: {result['found_start']}, END: {result['found_end']}")
                print(f"   🔢 Found range: {result['found_min']} to {result['found_max']} (expected: {result['expected_min']} to {result['expected_max']})")
                if result.get('error'):
                    print(f"   ❌ Error: {result['error']}")
                else:
                    print(f"   📝 Response sample: {result['response']}")
                break
            print()
        
        print(f"🏁 Last successful context length: {last_successful:,} tokens")
        assert last_successful > 0, "Should handle at least some context"
        return last_successful
    
    def test_context_length_full(self):
        """Full test up to 32k tokens with 2k increments."""
        provider = get_llm_provider()
        if provider == 'local':
            config = get_local_llm_config()
            model_name = config['model_name']
        else:
            model_name = 'gpt-4o'
        
        target_tokens = 32000
        step_size = 4000
        current_tokens = step_size
        last_successful = 0
        
        print(f"🔍 Testing LLM Context Length up to {target_tokens:,} tokens")
        print(f"🤖 Model: {model_name} (provider: {provider})")
        
        while current_tokens <= target_tokens:
            success = self._test_specific_length(current_tokens, model_name, provider)
            
            if success:
                last_successful = current_tokens
                print(f"✅ {current_tokens:,} tokens: SUCCESS")
            else:
                print(f"❌ {current_tokens:,} tokens: FAILED")
                break
                
            current_tokens += step_size
        
        print(f"\n🏁 RESULTS:")
        print(f"✅ Last successful context length: {last_successful:,} tokens")
        
        if last_successful < target_tokens:
            print(f"⚠️  Model appears to have context limit around {last_successful:,} tokens")
        else:
            print(f"🎉 Model successfully handled {target_tokens:,} tokens")
        
        return last_successful
    
    def test_specific_context_length(self, num_tokens=8000):
        """Test a specific context length."""
        provider = get_llm_provider()
        if provider == 'local':
            config = get_local_llm_config()
            model_name = config['model_name']
        else:
            model_name = 'gpt-4o'
        
        success = self._test_specific_length(num_tokens, model_name, provider)
        print(f"Testing {num_tokens:,} tokens: {'✅ SUCCESS' if success else '❌ FAILED'}")
        return success
    
    def _test_specific_length(self, num_tokens, model_name, provider):
        """
        Test a specific context length by sending sequential numbers.
        
        Args:
            num_tokens: Number of tokens to test
            model_name: LLM model name
            provider: LLM provider ('local' or 'openai')
        
        Returns:
            bool: True if test passed, False if failed
        """
        try:
            # Generate sequential numbers (roughly 1 token per number)
            # Format: "1, 2, 3, 4, ..." to make it clear
            numbers = []
            for i in range(1, num_tokens + 1):
                numbers.append(str(i))
            
            # Create the test content
            numbers_text = ", ".join(numbers)
            
            # Create test prompt
            system_prompt = """You are a number analyzer. I will give you a long sequence of numbers. 
Your task is to identify the HIGHEST (largest) number in the sequence.
Respond with ONLY the highest number you see, nothing else."""
            
            user_prompt = f"""Here is a sequence of numbers:
{numbers_text}

What is the HIGHEST number in this sequence? Respond with only that number."""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Call the LLM
            response = query(messages=messages, model=model_name, provider=provider)
            
            # Check if the response contains the highest number
            expected_highest = str(num_tokens)
            response_clean = response.strip()
            
            # The response should be exactly the highest number or contain it
            if expected_highest in response_clean:
                return True
            else:
                # Print what we got vs expected for debugging
                print(f"\n   Expected: {expected_highest}, Got: '{response_clean[:50]}...'")
                return False
                
        except Exception as e:
            print(f"\n   Error during context test: {e}")
            return False

    def test_basic_connectivity(self):
        """Test basic LLM connectivity before running context length tests."""
        provider = get_llm_provider()
        if provider == 'local':
            config = get_local_llm_config()
            model_name = config['model_name']
            print(f"🔍 Testing basic connectivity to local LLM")
            print(f"🌐 Endpoint: {config['base_url']}")
            print(f"🤖 Model: {model_name}")
            print(f"🔐 SSL Verify: {config.get('verify_ssl', False)}")
        else:
            model_name = 'gpt-4o'
            print(f"🔍 Testing basic connectivity to OpenAI")
            print(f"🤖 Model: {model_name}")
        
        # Simple test message
        test_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say exactly: 'Hello, World!'"}
        ]
        
        try:
            start_time = time.perf_counter()
            response = query(messages=test_messages, model=model_name, provider=provider)
            end_time = time.perf_counter()
            wall_clock_time = end_time - start_time
            
            print(f"✅ Connection successful!")
            print(f"⏱️  Response time: {wall_clock_time:.2f} seconds")
            print(f"📝 Response: {response}")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False


def manual_context_test(max_tokens=32000, step_size=4000):
    """
    Manual function to test context length outside of pytest framework.
    Can be called directly for debugging.
    
    Args:
        max_tokens: Maximum tokens to test
        step_size: Increment size for testing
    
    Returns:
        int: Last successful context length
    """
    print("🔍 Manual Context Length Test")
    print("=" * 50)
    
    provider = get_llm_provider()
    if provider == 'local':
        config = get_local_llm_config()
        model_name = config['model_name']
        print(f"🤖 Testing Local LLM: {model_name}")
        print(f"🌐 Endpoint: {config['base_url']}")
    else:
        model_name = 'gpt-4o'
        print(f"🤖 Testing OpenAI: {model_name}")
    
    print(f"🎯 Target tokens to test: {max_tokens:,}")
    print(f"📏 Step size: {step_size:,}")
    print()
    
    tester = TestContextLength()
    current_tokens = step_size
    last_successful = 0
    
    while current_tokens <= max_tokens:
        print(f"Testing {current_tokens:,} tokens...", end=" ")
        
        success = tester._test_specific_length(current_tokens, model_name, provider)
        
        if success:
            last_successful = current_tokens
            print(f"✅ SUCCESS")
        else:
            print(f"❌ FAILED")
            break
            
        current_tokens += step_size
    
    print()
    print("🏁 RESULTS:")
    print("=" * 50)
    print(f"✅ Last successful context length: {last_successful:,} tokens")
    
    if last_successful < max_tokens:
        print(f"⚠️  Model appears to have context limit around {last_successful:,} tokens")
    else:
        print(f"🎉 Model successfully handled {max_tokens:,} tokens")
    
    return last_successful


def quick_context_estimate():
    """
    Quick estimate of context length using common sizes.
    Useful for fast debugging.
    """
    print("🚀 Quick Context Length Estimate")
    print("=" * 40)
    
    tester = TestContextLength()
    return tester.test_context_length_quick()


if __name__ == "__main__":
    import sys
    
    print("LLM Context Length Tester")
    print("=" * 40)
    print()
    
    # Check current configuration
    provider = get_llm_provider()
    print(f"Current LLM Provider: {provider}")
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "quick":
            quick_context_estimate()
        elif sys.argv[1] == "full":
            manual_context_test(32000, 2000)
        elif sys.argv[1] == "test":
            tester = TestContextLength()
            tester.test_basic_connectivity()
        elif sys.argv[1] == "custom":
            try:
                max_tokens = int(sys.argv[2]) if len(sys.argv) > 2 else 16000
                step_size = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
                manual_context_test(max_tokens, step_size)
            except (ValueError, IndexError):
                print("Usage: python test_context_length.py custom <max_tokens> <step_size>")
                sys.exit(1)
        else:
            print("Usage: python test_context_length.py [quick|full|test|custom <max_tokens> <step_size>]")
    else:
        print("Available commands:")
        print("  python test_context_length.py test       # Test basic connectivity")
        print("  python test_context_length.py quick      # Test common lengths with timing")
        print("  python test_context_length.py full       # Test up to 32k tokens with timing")
        print("  python test_context_length.py custom 16000 1000  # Custom test with timing")
        print()
        print("Or run as pytest:")
        print("  pytest proposal_analyzer/test/test_context_length.py::TestContextLength::test_context_length_quick -v -s") 