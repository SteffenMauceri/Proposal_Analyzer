from pathlib import Path
import os

def get_api_key() -> str:
    # First try to read from text file
    key_file_path = Path(__file__).resolve().parent.parent.parent.joinpath("key.txt")
    try:
        if key_file_path.exists():
            api_key = key_file_path.read_text().strip()
            if api_key:  # Check if file is not empty
                return api_key
    except (OSError, IOError):
        pass  # File read failed, continue to environment variable
    
    # Fallback to environment variable
    env_api_key = os.getenv("OPENAI_API_KEY")
    if env_api_key:
        return env_api_key
    
    # If both methods fail, raise an error
    raise ValueError(
        "OpenAI API key not found. Please either:\n"
        "1. Create a 'key.txt' file in the project root with your API key, or\n"
        "2. Set the 'OPENAI_API_KEY' environment variable"
    ) 