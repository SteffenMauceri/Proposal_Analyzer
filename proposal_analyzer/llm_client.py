import os
from typing import List, Dict, Optional
import openai

# Assuming get_api_key is in a module accessible via this path
# Adjust the import path if your project structure is different
from .config import get_api_key


def query(
    messages: List[Dict[str, str]], 
    model: str = "gpt-4.1-mini", 
    client: Optional[openai.OpenAI] = None
) -> str:
    """Sends a query to the OpenAI API and returns the response.

    Args:
        messages: A list of message dictionaries, e.g., 
                  [{"role": "system", "content": "You are an assistant."},
                   {"role": "user", "content": "Hello!"}].
        model: The model to use for the query (e.g., "gpt-4.1-mini-2025-04-14").
        client: An optional OpenAI client instance. If None, a new client 
                will be initialized using the API key from config.

    Returns:
        The content of the assistant's response as a string.
    """
    if client is None:
        api_key = get_api_key()
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found. Please set it in your environment or key file.")
        client = openai.OpenAI(api_key=api_key)

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
            return "Error: No response received from the model."
    except Exception as e:
        # Basic error handling, consider more specific handling for production
        return f"Error during API call: {str(e)}"

# Example usage (optional, for direct testing of this module):
# if __name__ == '__main__':
#     # This example assumes your API key is set up correctly
#     # and the config.py is in the same directory or accessible
#     test_messages = [
#         {"role": "system", "content": "You are a helpful assistant."},
#         {"role": "user", "content": "What is the capital of France?"}
#     ]
#     response = query(test_messages)
#     print(f"Assistant: {response}")

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