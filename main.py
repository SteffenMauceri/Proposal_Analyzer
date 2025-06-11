import typer
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import sys
import logging
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table

# --- Service Imports ---
from services.proposal_qa_service import ProposalQAService
from services.reviewer_feedback_service import ReviewerFeedbackService
from services.pdf_export_service import PDFExportService
from services.summary_service import SummaryService
from utils.file_helpers import read_text_from_pdf, get_proposal_files

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Event-based output for streaming ---
def log_event(type: str, message: str, data: Optional[Dict] = None):
    """Logs an event to stdout in a structured format for streaming."""
    event = {
        "type": type,
        "message": message,
        "data": data or {}
    }
    sys.stdout.write(f"data: {json.dumps(event)}\n\n")
    sys.stdout.flush()

# --- Main Application Logic ---
def main(
    call_pdf_path: Path = typer.Option(..., "--call-pdf", "-c", help="Path to the Call for Proposals PDF."),
    proposals_dir: Path = typer.Option(..., "--proposals-dir", "-p", help="Directory containing proposal PDFs."),
    questions_file: Optional[Path] = typer.Option(None, "--questions-file", "-q", help="Path to a text file with questions."),
    output_dir: Path = typer.Option(Path("./output"), "--output-dir", "-o", help="Directory to save analysis results."),
    model: str = typer.Option("gpt-4.1-mini", "--model", "-m", help="OpenAI model to use for analysis."),
    selected_proposals: Optional[List[str]] = typer.Option(None, "--selected-proposals", help="A list of specific proposal filenames to analyze."),
    log_file: Path = typer.Option(Path("app.log"), "--log-file", help="Path to the log file."),
    
    # Feature flags
    analyze_proposal_opt: bool = typer.Option(True, "--analyze-proposal/--no-analyze-proposal", help="Enable/disable core proposal Q&A analysis."),
    # spell_check_opt: bool = typer.Option(False, "--spell-check/--no-spell-check", help="Enable/disable spell and grammar checking."),
    reviewer_feedback_opt: bool = typer.Option(False, "--reviewer-feedback/--no-reviewer-feedback", help="Enable/disable expert reviewer feedback (placeholder)."),
    # spell_check_model: str = typer.Option("gpt-4.1-nano", "--spell-check-model", help="Model to use specifically for spell checking."),

    # Control flags
    display_results: bool = typer.Option(True, "--display-results/--no-display-results", help="Display results in the console."),
    export_to_pdf: bool = typer.Option(True, "--export-pdf/--no-export-pdf", help="Export full report to PDF."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
    llm_instructions: Optional[str] = typer.Option(None, "--llm-instructions", "-i", help="Custom instructions for the LLM (for core proposal analysis)."),
    output_format: str = typer.Option("rich", "--output-format", "-of", help="Output format: 'rich' (console) or 'json' or 'pdf'."),
):
    """
    Analyzes research proposals based on a call for proposals, providing Q&A,
    and expert feedback. Results can be displayed or exported.
    """
    # --- Setup Logging ---
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    if verbose:
        logger.setLevel(logging.DEBUG)

    log_event("log", "Starting analysis process.")

    # --- Service Initialization ---
    qa_service = None
    if analyze_proposal_opt:
        qa_service = ProposalQAService(model=model, verbose=verbose)

    reviewer_feedback_service = None
    if reviewer_feedback_opt:
        reviewer_feedback_service = ReviewerFeedbackService(model=model, verbose=verbose)

    pdf_export_service = None
    if export_to_pdf:
        pdf_export_service = PDFExportService()

    all_results_for_proposal = {}
    
    # --- Text Extraction from Call PDF (once) ---
    call_text = ""
    if reviewer_feedback_opt:
        log_event("progress", f"Extracting text from call document: {call_pdf_path.name}...")
        try:
            call_text = read_text_from_pdf(call_pdf_path)
            log_event("progress", "Call document text extracted successfully.")
        except Exception as e:
            logger.error(f"Failed to extract text from call PDF {call_pdf_path}: {e}")
            log_event("error", f"Could not read call document {call_pdf_path.name}. Services requiring it may fail.")

    # --- Proposal Processing Loop ---
    proposals_to_process = get_proposal_files(proposals_dir, selected_proposals)
    if not proposals_to_process:
        log_event("error", "No proposal files found or selected to analyze.")
        return

    for proposal_path in proposals_to_process:
        proposal_filename = proposal_path.name
        log_event("progress", f"Processing proposal: {proposal_filename}...")
        
        proposal_results: Dict[str, Any] = {
            'qa_results': [],
            'reviewer_feedback': None,
        }

        # --- Text Extraction from Proposal PDF (once per proposal) ---
        proposal_text = ""
        # Extract text if any service needs it
        if analyze_proposal_opt or reviewer_feedback_opt:
            log_event("progress", f"[{proposal_filename}] Extracting text...")
            try:
                proposal_text = read_text_from_pdf(proposal_path)
                log_event("progress", f"[{proposal_filename}] Text extracted.")
            except Exception as e:
                logger.error(f"Failed to read or extract text from {proposal_filename}: {e}")
                log_event("error", f"Could not read {proposal_filename}. It will be skipped.")
                continue # Skip to the next proposal

        # --- Q&A Service ---
        if qa_service and proposal_text:
            log_event("progress", f"[{proposal_filename}] Running Q&A analysis...")
            try:
                # Assuming questions are read from the file inside the service or passed directly
                # For simplicity, let's assume service handles questions_file path
                qa_results = qa_service.answer_questions_from_text(
                    proposal_text=proposal_text,
                    questions_file_path=questions_file
                )
                proposal_results['qa_results'] = qa_results
                log_event("progress", f"[{proposal_filename}] Q&A analysis complete.")
            except Exception as e:
                logger.error(f"Error during Q&A analysis for {proposal_filename}: {e}")
                log_event("error", f"Q&A analysis failed for {proposal_filename}: {e}")

        # --- Reviewer Feedback Service ---
        if reviewer_feedback_service:
            log_event("progress", f"[{proposal_filename}] Generating expert reviewer feedback...")
            try:
                feedback = reviewer_feedback_service.get_feedback(
                    proposal_text=proposal_text, 
                    call_text=call_text
                )
                proposal_results['reviewer_feedback'] = feedback
                log_event("progress", f"[{proposal_filename}] Expert reviewer feedback generated.")
            except Exception as e:
                logger.error(f"Error getting reviewer feedback for {proposal_filename}: {e}")
                log_event("error", f"Error generating reviewer feedback for {proposal_filename}: {e}")
                proposal_results['reviewer_feedback'] = f"Error: Could not generate reviewer feedback. {e}"
        
        all_results_for_proposal[proposal_filename] = proposal_results
    
    # --- Consolidated Summary ---
    consolidated_summary = None
    if len(proposals_to_process) > 0:
        # We only generate summary if there was at least one proposal processed
        log_event("progress", "Generating consolidated summary...")
        try:
            summary_generator = SummaryService(model=model, verbose=verbose)
            consolidated_summary = summary_generator.generate_consolidated_summary(all_results_for_proposal)
            log_event("progress", "Consolidated summary generated.")
        except Exception as e:
            logger.error(f"Error generating consolidated summary: {e}")
            log_event("error", f"Error generating consolidated summary: {e}")
            consolidated_summary = f"Error generating summary: {e}"

    final_results_payload = {
        **all_results_for_proposal,
        "consolidated_summary": consolidated_summary
    }

    # --- Final Output ---
    if display_results:
        _display_rich_results(final_results_payload, logger)

    if export_to_pdf and pdf_export_service:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Assuming one PDF for all results for simplicity, or loop if one per proposal
        pdf_export_path = output_dir / "analysis_report.pdf"
        log_event("progress", f"Exporting full report to {pdf_export_path}...")
        try:
            pdf_export_service.generate_full_report_pdf(
                all_results=final_results_payload,
                export_path=pdf_export_path,
                # Include which services were run
                services_run={
                    "Core Analysis": analyze_proposal_opt,
                    # "Spell Check": spell_check_opt,
                    "Reviewer Feedback": reviewer_feedback_opt
                },
                models_used={
                    "Core Analysis Model": model if analyze_proposal_opt else "N/A",
                    # "Spell Check Model": spell_check_model if spell_check_opt else "N/A"
                }
            )
            final_results_payload["pdf_export_path"] = str(pdf_export_path)
            log_event("progress", f"PDF report generated: {pdf_export_path}")
        except Exception as e:
            logger.error(f"Failed to export PDF report: {e}")
            log_event("error", f"Failed to generate PDF report: {e}")

    # Final result event for streaming consumer
    log_event("result", "Analysis complete.", final_results_payload)


def _display_rich_results(results: Dict, logger: logging.Logger):
    """Displays the analysis results in a rich format in the console."""
    console = Console()
    console.print("[bold green]===== Analysis Results =====[/bold green]")

    for proposal_filename, proposal_data in results.items():
        if proposal_filename == "consolidated_summary": continue

        console.print(f"\n[bold magenta]>>> Proposal: {proposal_filename} <<<[/bold magenta]")

        # Q&A Results
        if 'qa_results' in proposal_data and proposal_data['qa_results']:
            console.print("\n[bold cyan]--- Question & Answer Analysis ---[/bold cyan]")
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Question", style="dim", width=40)
            table.add_column("Answer", width=60)
            table.add_column("Page", justify="right")
            for item in proposal_data['qa_results']:
                table.add_row(item['question'], item['answer'], str(item.get('page_number', 'N/A')))
            console.print(table)
        
        # Reviewer Feedback
        if 'reviewer_feedback' in proposal_data and proposal_data['reviewer_feedback']:
            console.print("\n[bold cyan]--- Expert Reviewer Feedback ---[/bold cyan]")
            console.print(Panel(
                Markdown(proposal_data['reviewer_feedback']),
                title="Feedback",
                border_style="cyan"
            ))

    # Consolidated Summary
    if "consolidated_summary" in results and results["consolidated_summary"]:
        console.print("\n[bold green]--- Consolidated Summary ---[/bold green]")
        console.print(Panel(
            Markdown(results["consolidated_summary"]),
            title="Executive Summary",
            border_style="green"
        ))

if __name__ == "__main__":
    typer.run(main)

