from pathlib import Path
from typing import List, Optional

def get_proposals_from_dir(proposals_dir_str: str) -> list:
    """Gets a list of PDF proposal filenames from a directory."""
    proposals_path_obj = Path(proposals_dir_str)
    if proposals_path_obj.is_dir():
        return sorted([f.name for f in proposals_path_obj.glob('*.pdf')])
    return []

def read_questions_content(questions_file_str: str) -> str:
    """Reads the content of the questions file."""
    q_file = Path(questions_file_str)
    if q_file.is_file():
        with open(q_file, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def get_call_documents(call_files_dir: Path) -> list:
    """Gets a list of call document filenames (.pdf, .doc, .docx) from a directory."""
    if call_files_dir.is_dir():
        patterns = ['*.pdf', '*.doc', '*.docx']
        files = []
        for pattern in patterns:
            files.extend(call_files_dir.glob(pattern))
        return sorted([f.name for f in files])
    return []

def find_first_document(directory: Path, patterns: List[str]) -> Optional[Path]:
    """Finds the first file in the directory matching any of the patterns."""
    if not directory.is_dir():
        return None
    for pattern in patterns:
        try:
            return next(directory.glob(pattern))
        except StopIteration:
            continue
    return None 