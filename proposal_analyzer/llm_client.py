import os
from typing import List, Dict, Optional
import openai

# Assuming get_api_key is in a module accessible via this path
# Adjust the import path if your project structure is different
from .config import get_api_key, get_local_llm_config, get_llm_provider


def query(
    messages: List[Dict[str, str]], 
    model: str = "gpt-4o-mini", 
    client: Optional[openai.OpenAI] = None,
    provider: Optional[str] = None
) -> str:
    """Sends a query to the specified LLM provider and returns the response.

    Args:
        messages: A list of message dictionaries, e.g., 
                  [{"role": "system", "content": "You are an assistant."},
                   {"role": "user", "content": "Hello!"}].
        model: The model to use for the query. For OpenAI: "gpt-4o-mini", "gpt-4o", etc.
               For local LLM: this will be overridden by the configured local model.
        client: An optional OpenAI client instance. If None, a new client 
                will be initialized based on the provider.
        provider: LLM provider to use ('openai' or 'local'). If None, uses config default.

    Returns:
        The content of the assistant's response as a string.
    """
    # Determine provider
    if provider is None:
        provider = get_llm_provider()
    
    if provider not in ['openai', 'local']:
        raise ValueError(f"Unsupported LLM provider: {provider}. Must be 'openai' or 'local'.")
    
    if client is None:
        if provider == 'openai':
            api_key = get_api_key()
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found. Please set it in your environment or key file.")
            client = openai.OpenAI(api_key=api_key)
        elif provider == 'local':
            local_config = get_local_llm_config()
            client = openai.OpenAI(
                base_url=local_config["base_url"],
                api_key=local_config["api_key"]
            )
            # Override model with local model name
            model = local_config["model_name"]
            
            # Handle SSL verification for local endpoints
            if not local_config["verify_ssl"]:
                import ssl
                import httpx
                # Create custom httpx client with SSL verification disabled
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                http_client = httpx.Client(verify=False)
                client = openai.OpenAI(
                    base_url=local_config["base_url"],
                    api_key=local_config["api_key"],
                    http_client=http_client
                )

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages
        )
        # Assuming the response structure has choices and the first choice is the one we want.
        # Adjust if the API response structure is different or if you need more complex error handling.
        if completion.choices and len(completion.choices) > 0:
            return completion.choices[0].message.content
        else:
            return f"Error: No response received from the {provider} model."
    except Exception as e:
        # Basic error handling, consider more specific handling for production
        return f"Error during {provider} API call: {str(e)}"

# Example usage (optional, for direct testing of this module):
# if __name__ == '__main__':
#     # This example assumes your API key is set up correctly
#     # and the config.py is in the same directory or accessible
#     test_messages = [
#         {"role": "system", "content": "You are a helpful assistant."},
#         {"role": "user", "content": "What is the capital of France?"}
#     ]
#     
#     # Test OpenAI
#     response_openai = query(test_messages, provider='openai')
#     print(f"OpenAI Assistant: {response_openai}")
#     
#     # Test Local LLM
#     response_local = query(test_messages, provider='local')
#     print(f"Local LLM Assistant: {response_local}")

#     # Example with a mock client (for testing)
#     class MockOpenAIClient:
#         def __init__(self, api_key):
#             pass # Mock client doesn't need an API key for this example

#         class MockChatCompletions:
#             def create(self, model, messages):
#                 class MockChoice:
#                     def __init__(self, content):
#                         self.message = self.MockMessage(content)
                    
#                     class MockMessage:
#                         def __init__(self, content):
#                             self.content = content
                
#                 if messages[-1]["content"] == "Hello?":
#                     return self.MockCompletion([MockChoice("Mock response: Hi there!")])
#                 return self.MockCompletion([MockChoice("Mock response: Default mock answer.")])

#         class MockCompletion:
#             def __init__(self, choices):
#                 self.choices = choices

#         @property
#         def chat(self):
#             return self # Simplified for this mock
        
#         @property
#         def completions(self):
#             return self.MockChatCompletions()

#     mock_client_instance = MockOpenAIClient(api_key="mock_key")
#     test_messages_mock = [
#         {"role": "user", "content": "Hello?"}
#     ]
#     mock_response = query(test_messages_mock, client=mock_client_instance)
#     print(f"Mock Assistant: {mock_response}") 