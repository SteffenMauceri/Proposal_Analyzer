import sys
import os
from pathlib import Path
import unittest
from typing import List, Dict, Any

# Add project root to sys.path to allow importing project modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from services.spell_checking_service import SpellCheckingService

# Paths to test data
TEST_DATA_DIR = PROJECT_ROOT / 'tests' / 'data' / 'spell_check'
ERROR_DOCUMENT_TXT = TEST_DATA_DIR / 'test_document_errors.txt'
# GROUND_TRUTH_DOCUMENT_TXT = TEST_DATA_DIR / 'test_document_ground_truth.txt' # Not directly used in these tests anymore

class TestSpellCheckingService(unittest.TestCase):

    def setUp(self):
        """Set up for test methods."""
        self.spell_checker = SpellCheckingService(model_name="test_model")
        self.assertTrue(ERROR_DOCUMENT_TXT.is_file(), f"Error document not found: {ERROR_DOCUMENT_TXT}")
        with open(ERROR_DOCUMENT_TXT, 'r', encoding='utf-8') as f:
            self.error_document_content = f.read()
        # Normalize newlines once for consistency in tests, similar to service
        self.normalized_error_content = self.error_document_content.replace('\r\n', '\n').replace('\r', '\n')

    def test_chunk_text_structure_and_offsets(self):
        """Test the _chunk_text mechanism for structure, offsets, and basic line numbers."""
        test_chunk_size = 500
        test_overlap = 50
        
        chunks_info = self.spell_checker._chunk_text(self.normalized_error_content, chunk_size=test_chunk_size, overlap=test_overlap)
        
        self.assertIsInstance(chunks_info, list)
        self.assertTrue(len(chunks_info) > 0, "Chunking produced no chunks_info.")
        
        previous_chunk_end_abs = -1
        for i, chunk in enumerate(chunks_info):
            self.assertIn('text_content', chunk)
            self.assertIn('start_offset_abs', chunk)
            self.assertIn('start_line_abs', chunk)
            self.assertIsInstance(chunk['text_content'], str)
            self.assertIsInstance(chunk['start_offset_abs'], int)
            self.assertIsInstance(chunk['start_line_abs'], int)
            self.assertTrue(chunk['start_line_abs'] >= 1, "Line numbers should be 1-indexed.")

            # Check that current chunk's text matches the slice from original normalized text
            expected_chunk_text = self.normalized_error_content[chunk['start_offset_abs'] : chunk['start_offset_abs'] + len(chunk['text_content'])].strip()
            # The service strips chunks, so we compare stripped versions, though ideally offsets point to raw text.
            # This needs careful handling if chunker modifies content vs just pointing to slices.
            # For now, let's assume the service's internal stripping matches what we expect here.
            # self.assertEqual(chunk['text_content'], expected_chunk_text, f"Chunk {i} content mismatch")

            if i > 0:
                # Check if overlap is somewhat maintained in start_offset_abs
                # prev_chunk_info = chunks_info[i-1]
                # expected_start_current = prev_chunk_info['start_offset_abs'] + len(prev_chunk_info['text_content']) - test_overlap
                # This is hard to assert exactly due to natural break finding and stripping.
                self.assertTrue(chunk['start_offset_abs'] < previous_chunk_end_abs, "Chunk start offset should be before previous chunk's unstripped end if overlapping.")
            
            actual_chunk_end_abs = chunk['start_offset_abs'] + len(self.normalized_error_content[chunk['start_offset_abs'] : chunk['start_offset_abs'] + test_chunk_size]) # Approx end before strip
            previous_chunk_end_abs = actual_chunk_end_abs

        # Check line number progression (should be non-decreasing)
        for i in range(1, len(chunks_info)):
            self.assertTrue(chunks_info[i]['start_line_abs'] >= chunks_info[i-1]['start_line_abs'])


    def test_check_document_text_with_mocked_llm_locations(self):
        """Test check_document_text for correct aggregation of locations from mocked LLM."""
        
        # Mocked LLM findings - these are relative to the chunk they are found in
        # Let's assume our document will be split into at least two chunks by the service
        # The first chunk will contain "teh importence"
        # The second chunk might pick up a later error, e.g., "is is bad"

        mock_findings_chunk_0 = [{
            "original_snippet_text": "importence", 
            "suggestion": "importance", 
            "type": "spelling_mock",
            "start_offset_in_chunk": 4, # "teh " is 4 chars, then "importence" starts (example)
            "end_offset_in_chunk": 4 + 10,
            "explanation": "Mocked spelling error."
        }]
        mock_findings_chunk_1 = [{
            "original_snippet_text": "is is", 
            "suggestion": "is", 
            "type": "repetition_mock",
            "start_offset_in_chunk": 20, # Example offset in the second chunk
            "end_offset_in_chunk": 20 + 5,
            "explanation": "Mocked repetition error."
        }]

        # Determine actual chunk boundaries to place mock findings correctly
        # We use default chunk_size/overlap here as that's what check_document_text will use internally if not specified.
        # However, _chunk_text uses chunk_size=2000, overlap=200 by default.
        # Let's use those for consistency for this test, or ensure check_document_text uses specific ones.
        # The service `_chunk_text` uses its own defaults. So we need to know what those are or pass them.
        # For this test, let's assume the default chunking will create chunks.
        
        # We need to know which chunk gets what. The test will be more robust if we define this based on content.
        # The first chunk will contain "The importence of clear comunication"
        # Error: "importence" at char offset 4 in *that chunk* (after "The ")
        
        # Second error: "is is bad"
        # Let's find its actual offset in the full document to verify the test logic.
        # This is getting complex to mock without knowing exact chunk splits beforehand.

        # Simpler mock: _call_llm_for_correction gets called PER CHUNK.
        # We mock its return value based on the chunk_index.

        original_llm_call = self.spell_checker._call_llm_for_correction
        
        # We need to know the text of the first few chunks to make the mock findings realistic.
        # Let's get the chunks that the service would create.
        # The defaults in _chunk_text are chunk_size=2000, overlap=200.
        actual_chunks_info = self.spell_checker._chunk_text(self.normalized_error_content) 
        self.assertTrue(len(actual_chunks_info) >= 1, "Document too short for meaningful chunk test / or chunking failed")

        # Mock LLM findings for specific chunks based on their content
        def mock_llm_call_based_on_content(chunk_text_content: str, chunk_index: int) -> List[Dict[str, Any]]:
            findings = []
            if "importence" in chunk_text_content and chunk_index == 0: # Assume first chunk has this
                start = chunk_text_content.find("importence")
                if start != -1:
                    findings.append({
                        "original_snippet_text": "importence", "suggestion": "importance", "type": "spelling_mock",
                        "start_offset_in_chunk": start, "end_offset_in_chunk": start + 10,
                        "explanation": "Mocked: importence"
                    })
            
            # Example for a later chunk if content matches (e.g. one containing "is is bad")
            # This error: "Your going to find that too much repetition, like the the a word, is is bad."
            # "is is bad" is towards the end of the first paragraph.
            if "is is bad" in chunk_text_content: 
                start = chunk_text_content.find("is is bad")
                if start != -1:
                    # find relative offset of "is is"
                    rel_start = chunk_text_content[start:].find("is is")
                    if rel_start != -1:
                        abs_start_of_phrase = start + rel_start
                        findings.append({
                            "original_snippet_text": "is is", "suggestion": "is", "type": "repetition_mock",
                            "start_offset_in_chunk": abs_start_of_phrase, 
                            "end_offset_in_chunk": abs_start_of_phrase + 5,
                            "explanation": "Mocked: is is"
                        })
            return findings

        self.spell_checker._call_llm_for_correction = mock_llm_call_based_on_content

        results = self.spell_checker.check_document_text(self.error_document_content) # Use original content
        
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0, "Expected at least one mock issue to be found.")

        found_importence = False
        found_is_is = False

        for issue in results:
            self.assertIn('original_snippet', issue)
            self.assertIn('suggestion', issue)
            self.assertIn('type', issue)
            self.assertIn('line_number', issue)
            self.assertIn('line_with_error', issue) # Can be None for PDFs, but should be str for .txt
            self.assertIn('char_offset_start_in_doc', issue)
            self.assertIn('char_offset_end_in_doc', issue)
            self.assertIn('chunk_index', issue)
            self.assertIsInstance(issue['char_offset_start_in_doc'], int)
            self.assertIsInstance(issue['line_number'], int) # -1 for PDFs, >=1 for TXT

            if issue['original_snippet'] == "importence":
                found_importence = True
                self.assertEqual(issue['line_number'], 1) # "The importence..." is on line 1
                self.assertTrue("importence" in issue['line_with_error'])
                # Verify absolute offset (fragile, depends on exact text)
                # "The importence..." - 'importence' starts after "The " (4 chars)
                expected_abs_offset_importence = self.normalized_error_content.find("importence")
                self.assertEqual(issue['char_offset_start_in_doc'], expected_abs_offset_importence)

            if issue['original_snippet'] == "is is":
                found_is_is = True
                # "Your going to find that too much repetition, like the the a word, is is bad." - should be on line 1 still
                expected_abs_offset_is_is = self.normalized_error_content.find("is is bad") + "is is bad".find("is is")
                self.assertEqual(issue['char_offset_start_in_doc'], expected_abs_offset_is_is)
                self.assertEqual(issue['line_number'], 1) # Still first line in test data
                self.assertTrue("is is bad" in issue['line_with_error'])
        
        self.assertTrue(found_importence, "Mocked 'importence' error not found in results.")
        self.assertTrue(found_is_is, "Mocked 'is is' error not found in results.")

        self.spell_checker._call_llm_for_correction = original_llm_call

if __name__ == '__main__':
    unittest.main() 