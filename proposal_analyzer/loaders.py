import PyPDF2
from docx import Document

def load_pdf(path: str) -> str:
    """Loads text content from a PDF file.

    Args:
        path: The path to the PDF file.

    Returns:
        A string containing the text content of the PDF, with pages joined by newline characters.
    """
    text_content = []
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            page_text = page.extract_text()
            # PyPDF2.extract_text() can return None for pages with no extractable text.
            # Replace None with empty string to avoid TypeError during join.
            text_content.append(page_text if page_text is not None else "")
    return "\n".join(text_content)


def load_docx(path: str) -> str:
    """Loads text content from a DOCX file.

    Args:
        path: The path to the DOCX file.

    Returns:
        A string containing the text content of the DOCX.
    """
    doc = Document(path)
    return "\n".join([paragraph.text for paragraph in doc.paragraphs])


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