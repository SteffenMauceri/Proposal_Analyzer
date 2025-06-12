import sys
import os

# Add parent directory to path for relative imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.text_extraction import extract_text_from_document

def load_pdf(path: str) -> str:
    """Loads text content from a PDF file using the enhanced text extraction utility.

    Args:
        path: The path to the PDF file.

    Returns:
        A string containing the text content of the PDF.
    """
    text = extract_text_from_document(path)
    return text if text else ""


def load_docx(path: str) -> str:
    """Loads text content from a DOCX file using the enhanced text extraction utility.

    Args:
        path: The path to the DOCX file.

    Returns:
        A string containing the text content of the DOCX.
    """
    text = extract_text_from_document(path)
    return text if text else ""


def load_txt(path: str) -> list[str]:
    """Loads questions from a text file, one question per line, stripping blank lines.

    Args:
        path: The path to the text file.

    Returns:
        A list of strings, where each string is a question.
    """
    with open(path, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines 