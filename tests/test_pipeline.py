import sys
import os
from pathlib import Path
import json
import tempfile

# Add project root to sys.path to allow importing project modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from services.analysis_service import AnalysisService
from services.pdf_export_service import PDFExportService
from utils.file_helpers import read_questions_content

# --- Configuration for the test ---
# Using absolute paths as per your request
CALL_PDF_PATH = Path("/Users/smauceri/Projects/GPT/proposal_scan/code/data/call/F.14+HPOSS.pdf")
PROPOSAL_PDF_PATH = Path("/Users/smauceri/Projects/GPT/proposal_scan/code/data/proposal/Proposal_CCSDS_interfaces_as-code-20250428e.pdf")
DEFAULT_QUESTIONS_FILE_PATH = Path("/Users/smauceri/Projects/GPT/proposal_scan/code/data/Questions_default.txt")
TEST_MODEL = "gpt-4.1-nano" # Using gpt-4.1-nano as requested (assuming "4o-nano" was a typo for this model family)
OUTPUT_PDF_DIR = PROJECT_ROOT / "exports" / "test_outputs"
OUTPUT_PDF_NAME = "test_pipeline_analysis_results.pdf"
# --- End Configuration ---

def main():
    print("Starting E2E pipeline test...")

    # Ensure output directory exists
    OUTPUT_PDF_DIR.mkdir(parents=True, exist_ok=True)
    output_pdf_path = OUTPUT_PDF_DIR / OUTPUT_PDF_NAME

    # 1. Prepare a single question
    print(f"Reading questions from: {DEFAULT_QUESTIONS_FILE_PATH}")
    if not DEFAULT_QUESTIONS_FILE_PATH.is_file():
        print(f"Error: Default questions file not found at {DEFAULT_QUESTIONS_FILE_PATH}")
        return
    
    all_questions = read_questions_content(str(DEFAULT_QUESTIONS_FILE_PATH))
    if not all_questions:
        print(f"Error: Could not read questions from {DEFAULT_QUESTIONS_FILE_PATH}")
        return
        
    first_question = all_questions.splitlines()[0]
    if not first_question:
        print("Error: No questions found in the default questions file.")
        return

    # Create a temporary file for the single question
    temp_questions_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt", encoding='utf-8') as f:
            f.write(first_question)
            temp_questions_file_path = Path(f.name)
        print(f"Using temporary questions file: {temp_questions_file_path} with question: \"{first_question}\"")

        # 2. Initialize Services
        analysis_service = AnalysisService(project_root=PROJECT_ROOT)
        pdf_export_service = PDFExportService(export_path_str=str(output_pdf_path))

        # 3. Run Analysis
        print(f"Running analysis with model: {TEST_MODEL}")
        print(f"  Call PDF: {CALL_PDF_PATH}")
        print(f"  Proposal PDF: {PROPOSAL_PDF_PATH.name}") # Just name for brevity in log
        
        # For the service, selected_proposals expects filenames relative to proposals_dir, or absolute paths.
        # Since PROPOSAL_PDF_PATH is already an absolute path, we can pass its name,
        # and the proposals_dir can be its parent.
        # Or, more simply, pass the absolute path string directly in a list.
        # The `_build_analysis_command` in AnalysisService will use `str(path.resolve())`
        # and `selected_proposal` is just appended to the command.
        # Let's ensure main.py can handle absolute paths for --selected-proposal too.
        # A quick check of main.py shows `resolve_path=True` for `selected_proposals`,
        # so passing the absolute path string should be fine.

        analysis_results, error_message = analysis_service.run_analysis_blocking(
            call_pdf_path=CALL_PDF_PATH,
            proposals_dir_path=PROPOSAL_PDF_PATH.parent, # Provide parent dir for context
            questions_file_path=temp_questions_file_path,
            model=TEST_MODEL,
            selected_proposal_filenames=[str(PROPOSAL_PDF_PATH)], # Pass as a list of strings
            logger=None # Or configure a simple logger here if needed
        )

        if error_message:
            print(f"Error during analysis: {error_message}")
            return
        
        if not analysis_results:
            print("Analysis completed but returned no results.")
            return

        print("Analysis successful. Results:")
        print(json.dumps(analysis_results, indent=2))

        # 4. Export to PDF
        print(f"Exporting results to PDF: {output_pdf_path}")
        
        # Adapt the analysis_results to the structure expected by generate_analysis_pdf
        # It expects a list of dictionaries, where each dictionary has 'proposal_name' and 'analysis' keys.
        if analysis_results and 'proposal_analysis' in analysis_results:
            adapted_results_for_pdf = [{
                "proposal_name": PROPOSAL_PDF_PATH.name, # Use the proposal filename
                "analysis": analysis_results['proposal_analysis'], # This is the list of Q/A items
                "status": "success" # Assuming success if we have proposal_analysis
            }]
            generated_pdf = pdf_export_service.generate_analysis_pdf(adapted_results_for_pdf)
        else:
            print("Error: 'proposal_analysis' key not found in analysis_results or results are empty.")
            generated_pdf = None

        if generated_pdf and Path(generated_pdf).is_file():
            print(f"PDF generated successfully: {generated_pdf}")
        else:
            print(f"Error: PDF file was not generated at {generated_pdf}")
            return
            
        print("\n--- Test Summary ---")
        if Path(generated_pdf).is_file() and not error_message and analysis_results:
            print("Pipeline Test: PASSED")
            print(f"Output PDF: {generated_pdf}")
        else:
            print("Pipeline Test: FAILED")


    except Exception as e:
        print(f"An unexpected error occurred during the test: {e}")
    finally:
        # 5. Cleanup
        if temp_questions_file_path and temp_questions_file_path.exists():
            print(f"Cleaning up temporary questions file: {temp_questions_file_path}")
            os.remove(temp_questions_file_path)
        
    print("E2E pipeline test finished.")

if __name__ == "__main__":
    main() 