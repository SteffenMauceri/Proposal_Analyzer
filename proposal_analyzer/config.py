from pathlib import Path
import os

def get_api_key() -> str:
    # First, try to read from the text file in the project root.
    key_path = Path(__file__).resolve().parent.parent.joinpath("key.txt")
    try:
        if key_path.is_file():
            api_key = key_path.read_text().strip()
            if api_key:
                return api_key
    except OSError:
        # Errors reading file, so we'll try environment variables.
        pass

    # If file isn't found or is empty, try environment variables.
    # User-requested 'openai-key' is checked first.
    api_key = os.getenv("openai-key") or os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key

    raise ValueError(
        "OpenAI API key not found. Please create key.txt in the project root, "
        "or set the 'openai-key' or 'OPENAI_API_KEY' environment variable."
    ) 