from pathlib import Path
from typing import List, Dict, Any, Optional
import re
import json # For parsing LLM response
import sys # For sys.path modification in __main__ and sys.stderr

# For PDF text extraction
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

# Import for actual LLM calls
from proposal_analyzer.llm_client import query
import openai # To allow passing an OpenAI client instance

class SpellCheckingService:
    """
    A service dedicated to checking grammar and spelling in documents.
    It processes a document by chunking its text and using an LLM 
    to identify and suggest corrections for errors, including their locations.
    """

    def __init__(self, model_name: str = "gpt-4.1-nano", client: Optional[openai.OpenAI] = None):
        """
        Initializes the SpellCheckingService.

        Args:
            model_name (str): The name of the language model to be used (e.g., "gpt-4.1-nano").
            client (Optional[openai.OpenAI]): An optional pre-configured OpenAI client instance.
                                               If None, the llm_client will create one.
        """
        self.model_name = model_name
        self.client = client # Store the client for use in _call_llm_for_correction
        
        if PyPDF2 is None:
            print("Warning: PyPDF2 library is not installed. PDF processing will not be available.", file=sys.stderr)
            # print("Please install it by running: pip install PyPDF2") # Redundant with llm_client

    def _extract_text_from_pdf(self, pdf_path: Path) -> Optional[str]:
        """
        Extracts text content from a PDF file.
        Args:
            pdf_path (Path): The path to the PDF file.
        Returns:
            Optional[str]: The extracted text, or None if extraction fails or PyPDF2 is not available.
        """
        if PyPDF2 is None:
            return None
        if not pdf_path.is_file():
            return None
        
        try:
            raw_text_parts = []
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    page_text = page.extract_text()
                    if page_text:
                        raw_text_parts.append(page_text)
            
            if not raw_text_parts:
                return None

            full_raw_text = "\n".join(raw_text_parts)
            
            # 1. Normalize Unicode and handle mojibake (basic)
            # This is a complex topic. For now, we assume text is mostly okay or rely on LLM for minor issues.
            # A more robust solution might involve libraries like ftfy.
            # For now, let's focus on structural cleanup.

            # 2. Re-join hyphenated words at line breaks
            # This regex looks for a word character, a hyphen, a newline, and another word character.
            processed_text = re.sub(r'(\w)-(\r\n|\r|\n)(\w)', r'\1\3', full_raw_text)
            
            # 3. Normalize all forms of newlines to a single \n, then handle multiple newlines
            processed_text = re.sub(r'(\r\n|\r|\n)+', '\n', processed_text)
            
            # 4. Normalize other whitespace (multiple spaces/tabs to single space)
            # but preserve newlines for paragraph structure if they are meaningful
            lines = processed_text.split('\n')
            cleaned_lines = [re.sub(r'[ \t\xA0]+', ' ', line).strip() for line in lines]
            # Rejoin lines. If paragraphs are important, consider double newline, but LLM prompt will handle it.
            processed_text = "\n".join(cleaned_lines)
            
            # 5. Remove excessive blank lines (more than 2 consecutive newlines)
            processed_text = re.sub(r'\n{3,}', '\n\n', processed_text)
            
            return processed_text.strip() # Final strip for any leading/trailing whitespace

        except Exception as e:
            # Optionally log the error e
            return None

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 6000,
        overlap: int = 600
    ) -> List[Dict[str, Any]]: 
        if not text:
            return []
        normalized_text = re.sub(r'\r\n|\r', '\n', text)
        chunks_info = []
        current_char_offset = 0
        current_line_number = 1
        text_len = len(normalized_text)
        processed_chars_for_line_counting = 0
        while current_char_offset < text_len:
            end_char_offset = min(current_char_offset + chunk_size, text_len)
            if end_char_offset < text_len:
                potential_break = normalized_text.rfind('. ', current_char_offset, end_char_offset + 1)
                if potential_break != -1 and potential_break > current_char_offset:
                    end_char_offset = potential_break + 1 
                else:
                    potential_break = normalized_text.rfind(' ', current_char_offset, end_char_offset)
                    if potential_break != -1 and potential_break > current_char_offset:
                        end_char_offset = potential_break
            chunk_text_content = normalized_text[current_char_offset:end_char_offset].strip()
            newlines_since_last_chunk = normalized_text[processed_chars_for_line_counting:current_char_offset].count('\n')
            current_line_number += newlines_since_last_chunk
            processed_chars_for_line_counting = current_char_offset
            if chunk_text_content:
                chunks_info.append({
                    'text_content': chunk_text_content,
                    'start_offset_abs': current_char_offset,
                    'start_line_abs': current_line_number 
                })
            if end_char_offset == text_len:
                break
            new_start_offset = end_char_offset - overlap
            current_char_offset = max(new_start_offset, current_char_offset + 1 if new_start_offset <= current_char_offset else new_start_offset)
            if current_char_offset >= text_len:
                break
        return chunks_info

    def _call_llm_for_correction(self, chunk_text_content: str, chunk_index: int) -> List[Dict[str, Any]]:
        """
        Calls an LLM to check grammar and spelling for a given text chunk.
        Returns a list of identified issues with offsets relative to the chunk.
        """
        if not chunk_text_content.strip():
            return [] 

        system_prompt = (
            "You are an expert proofreader. Your task is to analyze the user-provided text chunk for errors. "
            "The text is extracted from a PDF and may contain artifacts such as incorrect word breaks, "
            "unusual spacing, or minor OCR errors. Try to infer the intended meaning. "
            "Focus on clear errors in spelling, grammar, punctuation, contextual appropriateness, and repetition "
            "that are likely not just PDF conversion artifacts if the meaning is still discernible. "
            "Only focus on complete sentences. Ignore formatting errors. Ignore text snippets that are likely extracted from talbes or similar non-body text. "
            "For EACH error you find, you MUST return a JSON object with the following exact keys and value types:\n"
            "  \"original_snippet_text\": string (This MUST be the EXACT, verbatim text substring from the input chunk that contains the error. Do NOT alter it.),\n"
            "  \"suggestion\": string (Your suggested correction for the snippet.),\n"
            "  \"type\": string (Categorize the error, e.g., 'spelling', 'grammar', 'punctuation', 'repetition', 'contextual', 'awkward_phrasing', 'ocr_artifact').,\n"
            "  \"start_offset_in_chunk\": integer (The 0-indexed character start offset of \"original_snippet_text\" within the provided text chunk.),\n"
            "  \"end_offset_in_chunk\": integer (The 0-indexed character end offset of \"original_snippet_text\" within the provided text chunk, such that text_chunk[start_offset_in_chunk:end_offset_in_chunk] == original_snippet_text.),\n"
            "  \"explanation\": string (A brief explanation of the error and your correction.)\n"
            "Respond with a single JSON list containing these objects. Ensure all character offsets are accurate. "
            "CRITICAL: The value for \"original_snippet_text\" MUST be an exact substring of the input text chunk. "
            "For example, if the input chunk is 'Hello teh world' and 'teh' is an error starting at character 6, you would return: "
            "{\"original_snippet_text\": \"teh\", \"suggestion\": \"the\", \"type\": \"spelling\", \"start_offset_in_chunk\": 6, \"end_offset_in_chunk\": 9, \"explanation\": \"Misspelling of 'the'.\"}. "
            "If no errors are found, output an empty JSON list: []."
            "Output ONLY the JSON list of objects, with no other text before or after it."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": chunk_text_content}
        ]

        # print(f"DEBUG: Sending to LLM (model: {self.model_name}, chunk_index: {chunk_index}):\nText Chunk (first 300 chars): '{chunk_text_content[:300]}...'\n") # Commented out

        raw_response = query(messages=messages, model=self.model_name, client=self.client)

        # print(f"DEBUG: LLM raw response (chunk {chunk_index}):\n{raw_response}\n") # Commented out

        try:
            json_str = ""
            # Attempt to extract JSON from typical LLM response patterns
            # 1. Markdown code block ```json ... ```
            match_markdown = re.search(r"```json\s*([\s\S]*?)\s*```", raw_response)
            if match_markdown:
                json_str = match_markdown.group(1).strip()
            else:
                # 2. Raw JSON list or object (find first '[' or '{' and last ']' or '}')
                first_bracket = raw_response.find('[')
                first_curly = raw_response.find('{')

                start_json_pos = -1

                if first_bracket != -1 and (first_curly == -1 or first_bracket < first_curly):
                    # Likely a JSON list is the main content
                    start_json_pos = first_bracket
                    end_json_pos = raw_response.rfind(']')
                elif first_curly != -1 and (first_bracket == -1 or first_curly < first_bracket):
                    # Likely a JSON object is the main content (though we expect a list)
                    start_json_pos = first_curly
                    end_json_pos = raw_response.rfind('}') 
                else:
                    end_json_pos = -1 # Should not happen if LLM returns [] or [{...}]
                
                if start_json_pos != -1 and end_json_pos != -1 and end_json_pos > start_json_pos:
                    json_str = raw_response[start_json_pos : end_json_pos + 1].strip()
                else:
                    print(f"Warning (Chunk {chunk_index}): Could not reliably find JSON start/end markers. Raw response: {raw_response}", file=sys.stderr)
                    return []
            
            if not json_str:
                print(f"Warning (Chunk {chunk_index}): Extracted JSON string is empty. Raw response: {raw_response}", file=sys.stderr)
                return []

            # Pre-process the extracted string to handle common issues like unescaped newlines in string values
            # This is a heuristic. A more robust solution involves complex parsing or stricter LLM output.
            # json_str = json_str.replace("\n", "\\n") # Careful: this might double-escape if already correct.
            # A slightly safer approach might be to only replace newlines not preceded by a backslash, but that's complex with regex.
            # For now, let's assume the main issue is with the extraction boundaries or LLM providing malformed structure.

            findings = json.loads(json_str)
            
            # Validate and normalize findings (basic validation)
            validated_findings = []
            for finding in findings:
                if not all(k in finding for k in ["original_snippet_text", "suggestion", "type", "start_offset_in_chunk", "end_offset_in_chunk"]):
                    print(f"Warning (Chunk {chunk_index}): Skipping malformed finding from LLM: {finding}", file=sys.stderr)
                    continue
                try:
                    llm_start_offset = int(finding['start_offset_in_chunk'])
                    llm_end_offset = int(finding['end_offset_in_chunk'])
                    llm_snippet = finding['original_snippet_text']
                except ValueError:
                    print(f"Warning (Chunk {chunk_index}): Finding has non-integer offsets or missing snippet: {finding}", file=sys.stderr)
                    continue
                
                # Validate and potentially correct offsets
                actual_start_offset = -1
                actual_end_offset = -1

                # 1. First, check if LLM's reported offsets and snippet match directly
                if llm_start_offset >= 0 and llm_end_offset > llm_start_offset and \
                   chunk_text_content[llm_start_offset:llm_end_offset] == llm_snippet:
                    actual_start_offset = llm_start_offset
                    actual_end_offset = llm_end_offset
                else:
                    # 2. LLM's offsets were problematic. Try to find the LLM's snippet text in the chunk.
                    #    Search within a window around the LLM's reported start_offset for better performance,
                    #    or search the whole chunk if necessary.
                    #    Window size can be heuristic (e.g., +/- 50 characters).
                    search_window_delta = 50
                    search_start = max(0, llm_start_offset - search_window_delta)
                    search_end = min(len(chunk_text_content), llm_start_offset + len(llm_snippet) + search_window_delta) # Ensure window is large enough for snippet
                    
                    try_find_pos = chunk_text_content.find(llm_snippet, search_start, search_end)

                    if try_find_pos != -1:
                        actual_start_offset = try_find_pos
                        actual_end_offset = try_find_pos + len(llm_snippet)
                        if actual_start_offset != llm_start_offset:
                             print(f"Info (Chunk {chunk_index}): Corrected LLM offset. Snippet '{llm_snippet}' found at {actual_start_offset} (LLM said {llm_start_offset}).", file=sys.stderr)
                    else:
                        # 3. If not found in window, try searching the entire chunk as a last resort
                        try_find_pos_full_chunk = chunk_text_content.find(llm_snippet)
                        if try_find_pos_full_chunk != -1:
                            actual_start_offset = try_find_pos_full_chunk
                            actual_end_offset = try_find_pos_full_chunk + len(llm_snippet)
                            if actual_start_offset != llm_start_offset:
                                print(f"Info (Chunk {chunk_index}): Corrected LLM offset (full chunk search). Snippet '{llm_snippet}' found at {actual_start_offset} (LLM said {llm_start_offset}).", file=sys.stderr)
                        else:
                            print(f"Warning (Chunk {chunk_index}): LLM-reported snippet '{llm_snippet}' not found in chunk text, even after searching. LLM offsets: {llm_start_offset}-{llm_end_offset}. Skipping this finding.", file=sys.stderr)
                            continue # Skip this finding as we can't reliably locate it

                # Update finding with validated/corrected offsets
                finding['start_offset_in_chunk'] = actual_start_offset
                finding['end_offset_in_chunk'] = actual_end_offset
                validated_findings.append(finding)
            return validated_findings
            
        except json.JSONDecodeError as e:
            print(f"Error (Chunk {chunk_index}): Failed to decode LLM JSON response. Error: {e}. json_str attempted: '{json_str[:500]}...'", file=sys.stderr)
            return [] 
        except Exception as e:
            print(f"Error (Chunk {chunk_index}): Unexpected error processing LLM response: {e}. Response: {raw_response}", file=sys.stderr)
            return []

    def _get_line_content_and_relative_line(self, original_doc_text: str, absolute_char_offset: int) -> (Optional[str], int):
        if absolute_char_offset < 0 or absolute_char_offset > len(original_doc_text):
            return None, -1
        line_start_offset = original_doc_text.rfind('\n', 0, absolute_char_offset) + 1
        line_end_offset = original_doc_text.find('\n', absolute_char_offset)
        if line_end_offset == -1:
            line_end_offset = len(original_doc_text)
        line_content = original_doc_text[line_start_offset:line_end_offset]
        current_line_number = original_doc_text.count('\n', 0, line_start_offset) + 1
        return line_content.strip(), current_line_number

    def check_document_text(
            self, 
            document_text: str, 
            is_pdf_source: bool = False
        ) -> List[Dict[str, Any]]:
        if not document_text: return []
        normalized_full_text = re.sub(r'\r\n|\r', '\n', document_text)
        chunks_info = self._chunk_text(normalized_full_text)
        if not chunks_info: return []
        all_issues_with_locations = []
        for i, chunk_info in enumerate(chunks_info):
            chunk_text_content = chunk_info['text_content']
            chunk_abs_start_offset = chunk_info['start_offset_abs']
            chunk_issues = self._call_llm_for_correction(chunk_text_content, chunk_index=i)
            for issue in chunk_issues:
                abs_start_offset = chunk_abs_start_offset + issue['start_offset_in_chunk']
                abs_end_offset = chunk_abs_start_offset + issue['end_offset_in_chunk']
                line_text = None
                line_num_of_error = -1
                if not is_pdf_source:
                    line_num_of_error = normalized_full_text.count('\n', 0, abs_start_offset) + 1
                    line_start_char = normalized_full_text.rfind('\n', 0, abs_start_offset) + 1
                    line_end_char = normalized_full_text.find('\n', abs_start_offset)
                    if line_end_char == -1: line_end_char = len(normalized_full_text)
                    line_text = normalized_full_text[line_start_char:line_end_char].strip()
                else:
                    line_num_of_error = -1
                all_issues_with_locations.append({
                    'original_snippet': issue['original_snippet_text'],
                    'suggestion': issue['suggestion'],
                    'type': issue['type'],
                    'line_number': line_num_of_error,
                    'line_with_error': line_text,
                    'char_offset_start_in_doc': abs_start_offset,
                    'char_offset_end_in_doc': abs_end_offset,
                    'chunk_index': i,
                    'explanation': issue.get('explanation')
                })
        return all_issues_with_locations

    def check_pdf_document(self, document_path: Path) -> List[Dict[str, Any]]:
        document_text = self._extract_text_from_pdf(document_path)
        if not document_text:
            return [{
                "original_snippet": str(document_path), "suggestion": "N/A", "type": "error_extraction",
                "line_number": -1, "line_with_error": None,
                "char_offset_start_in_doc": 0, "char_offset_end_in_doc": 0,
                "chunk_index": -1, "explanation": "Failed to extract text from PDF or PDF was empty."
            }]
        return self.check_document_text(document_text, is_pdf_source=True)

if __name__ == '__main__':
    # The following sys.path modification is no longer strictly necessary 
    # if running with `python -m services.spell_checking_service` from project root,
    # which is the recommended way for direct execution of package sub-modules.
    # Keeping it commented out for reference or if someone attempts direct path execution.
    # SCRIPT_DIR = Path(__file__).resolve().parent
    # PROJECT_ROOT = SCRIPT_DIR.parent 
    # if str(PROJECT_ROOT) not in sys.path:
    #     sys.path.append(str(PROJECT_ROOT))

    print("Testing SpellCheckingService with ACTUAL LLM (ensure API key is set)...")
    # Test with a short text that has deliberate errors
    test_text_for_llm = (
        "This is teh first sentance. It has a speling mistke.\n"
        "Seccond line here. Their are two many errors too count for you're own good. "
        "The affect of these errors is is significant. We must act quick."
    )

    # Initialize with your desired model, e.g., "gpt-4.1-nano" or "gpt-4.1-mini-2025-04-14"
    # Ensure your OPENAI_API_KEY environment variable is set, or your config.py provides it.
    try:
        # This import should ideally be at the top, but for __main__ direct run, 
        # ensure it can be found after sys.path modification if it couldn't before.
        # If the global one worked, this is just for clarity or fallback.
        from proposal_analyzer.llm_client import query # Already at top, fine.
        import openai # Already at top, fine.

        checker = SpellCheckingService(model_name="gpt-4.1-nano") 
        # Example of how to pass a client explicitly if needed:
        # from proposal_analyzer.config import get_api_key 
        # api_key = get_api_key()
        # if api_key:
        #     my_client = openai.OpenAI(api_key=api_key)
        #     checker = SpellCheckingService(model_name="gpt-4.1-nano", client=my_client)
        # else:
        #     print("OPENAI_API_KEY not found, cannot run live LLM test in __main__.")
        #     sys.exit(1)

    except ModuleNotFoundError as e:
        print(f"Failed to import necessary modules for __main__ execution: {e}")
        print("Ensure that 'proposal_analyzer' is in the project root and this script is in a subdirectory like 'services'.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred during setup for __main__: {e}")
        sys.exit(1)


    print(f"\n--- Checking content with {checker.model_name} ---")
    issues = checker.check_document_text(test_text_for_llm)
    
    if issues:
        print(f"Found {len(issues)} issues:")
        issues_by_line = {}
        for issue in issues:
            line_num = issue['line_number']
            if line_num not in issues_by_line:
                issues_by_line[line_num] = []
            issues_by_line[line_num].append(issue)

        for line_num in sorted(issues_by_line.keys()):
            line_issues = issues_by_line[line_num]
            print(f"\n  Line {line_num}: '{line_issues[0].get('line_with_error', 'N/A')}'")
            for issue in line_issues:
                print(f"    - Snippet: '{issue['original_snippet']}' (Offset: {issue['char_offset_start_in_doc']}) -> '{issue['suggestion']}' (Type: {issue['type']})")
                if issue.get('explanation'):
                    print(f"      Why: {issue['explanation']}")
    else:
        print("No issues found by the LLM.")

    print("\nSpellCheckingService LLM test finished.") 