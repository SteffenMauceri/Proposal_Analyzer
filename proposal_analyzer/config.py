from pathlib import Path
import os
from typing import Optional, Dict, Any

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

def get_local_llm_config() -> Dict[str, Any]:
    """
    Get local LLM configuration from environment variables with sensible defaults.
    API key must be provided via environment variable for security.
    """
    api_key = os.getenv("LOCAL_LLM_API_KEY")
    
    if not api_key:
        raise ValueError(
            "LOCAL_LLM_API_KEY environment variable not found. Please set it to your local LLM API key."
        )
    
    return {
        "base_url": os.getenv("LOCAL_LLM_BASE_URL", "https://chathpc.jpl.nasa.gov/ollama/v1"),
        "api_key": api_key,
        "model_name": os.getenv("LOCAL_LLM_MODEL", "gemma3:27b-32k"),
        "verify_ssl": os.getenv("LOCAL_LLM_VERIFY_SSL", "false").lower() == "true"
    }

def get_llm_provider() -> str:
    """
    Get the preferred LLM provider from environment variable.
    Returns 'openai' or 'local'. Defaults to 'openai'.
    """
    return os.getenv("LLM_PROVIDER", "local").lower() 