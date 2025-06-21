import typer
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import json
import sys

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax

# Service Imports
from services.analysis_service import AnalysisService
from services.pdf_export_service import PDFExportService

from services.reviewer_feedback_service import ReviewerFeedbackService # Added for reviewer feedback

# Utility Imports
from utils.file_helpers import find_first_document, read_questions_content # Assuming read_questions_content is needed or was there
from utils.text_extraction import extract_text_from_document



console = Console()
error_console = Console(stderr=True, style="bold red")
info_console = Console(style="blue") # For informational messages

# --- Project Root (ensure it's defined, e.g., if AnalysisService needs it) ---
PROJECT_ROOT = Path(__file__).resolve().parent

# --- Placeholder Services ---
# Removed get_reviewer_feedback_placeholder as it's replaced by the service
# Removed get_nasa_pm_feedback_placeholder 



app = typer.Typer(
    name="proposal_analyzer_cli",
    help="CLI tool to analyze proposals and generate reports.",
    add_completion=False,
    no_args_is_help=True
)

def _display_rich_results(all_results: Dict[str, List[Dict[str, Any]]], llm_instructions: Optional[str] = None):
    """Displays all collected results in a structured rich format on the console."""
    console.rule("[bold green]Proposal Processing Results[/bold green]", style="green")

    if llm_instructions:
        console.print(Panel(Text(llm_instructions, style="italic cyan"), title="[bold]LLM Instructions Used[/bold]", border_style="blue", expand=False))

    for service_key, findings in all_results.items():
        if not findings: # Skip if no findings for this service
            continue

        service_name_display = service_key.replace("_", " ").title()
        console.rule(f"[bold magenta]{service_name_display}[/bold magenta]", style="magenta")

        if not findings:
            console.print("No findings or not applicable for this service.", style="italic dim")
            continue

        # Custom display for each service type
        if service_key == "proposal_analysis":
            for item in findings: # Assuming proposal_analysis results are structured like Q&A
                question = item.get("question", "N/A")
                answer = item.get("answer", "N/A").strip()
                console.print(f"[bold]Q: {question}[/bold]")
                # Use Syntax for potentially multi-line answers with code blocks
                if "\n" in answer or "```" in answer:
                     console.print(Syntax(answer, "markdown", theme="dracula", line_numbers=False, word_wrap=True))
                else:
                    console.print(Text(answer, style="white"))
                console.print("-" * 20)

        elif service_key in ["reviewer_feedback"]: # Removed "nasa_pm_feedback"
            for item in findings:
                # Check if it's an error from the service itself
                if item.get("type", "").endswith("_error"):
                    console.print(Panel(
                        Text(f"Error: {item.get('explanation', 'An error occurred.')}", style="italic red"), 
                        title=f"[bold red]{item.get('service_name', 'Service Error')}[/bold red]", 
                        border_style="red"
                    ))
                elif item.get('service_name', '').endswith('(placeholder)'): # Original placeholder display
                    console.print(Panel(
                        Text(item.get("explanation", "N/A"), style="italic yellow"),
                        title=f"[bold yellow]{item.get('service_name', 'Placeholder Service')}[/bold yellow]",
                        border_style="yellow"
                    ))
                else: # Actual feedback display
                    console.print(Panel(
                            Text(item.get("suggestion", "N/A"), style="white"),
                            title=f"[bold green]{item.get('service_name', 'Feedback Service')}[/bold green]",
                            subtitle=f"[italic dim]{item.get('original_snippet', '')} - {item.get('explanation', '')}[/italic dim]",
                            border_style="green"
                    ))
        else: # Generic fallback for other result types
            for item in findings:
                console.print(item)
        console.line()
    console.rule("[bold green]End of Results[/bold green]", style="green")


@app.command()
def main_cli(
    call_pdf: Optional[Path] = typer.Option(None, "--call-pdf", "-c", help="Path to the call PDF. Optional.", exists=False, dir_okay=False, resolve_path=True),
    proposals_dir: Optional[Path] = typer.Option(None, "--proposals-dir", "-p", help="Directory containing proposal PDFs. Optional.", file_okay=False, resolve_path=True),
    questions_file: Optional[Path] = typer.Option(None, "--questions-file", "-q", help="Path to the questions text file. Optional.", dir_okay=False, resolve_path=True),
    single_proposal_pdf: Optional[Path] = typer.Option(None, "--proposal-pdf", "-f", help="Path to a single proposal PDF to analyze. Overrides --proposals-dir.", exists=True, dir_okay=False, resolve_path=True),
    output_dir: Path = typer.Option(Path("exports/"), "--output-dir", "-o", help="Directory to save exported PDF reports.", file_okay=False, resolve_path=True),
    llm_instructions: Optional[str] = typer.Option(None, "--llm-instructions", "-i", help="Custom instructions for the LLM (for core proposal analysis)."),
    output_format: str = typer.Option("rich", "--output-format", "-of", help="Output format: 'rich' (console) or 'json' or 'pdf'."),
    
    # LLM Provider options
    llm_provider: str = typer.Option("openai", "--llm-provider", help="LLM provider to use: 'openai' or 'local'. Overrides environment variable."),
    local_llm_url: Optional[str] = typer.Option(None, "--local-llm-url", help="Base URL for local LLM API (e.g., https://localhost:8000/v1). Overrides environment variable."),
    local_llm_model: Optional[str] = typer.Option(None, "--local-llm-model", help="Model name for local LLM. Overrides environment variable."),
    local_llm_api_key: Optional[str] = typer.Option(None, "--local-llm-api-key", help="API key for local LLM. Overrides environment variable."),
    
    # New options for selective analysis
    analyze_proposal_opt: bool = typer.Option(True, "--analyze-proposal/--no-analyze-proposal", help="Enable/disable core proposal Q&A analysis."),
    reviewer_feedback_opt: bool = typer.Option(False, "--reviewer-feedback/--no-reviewer-feedback", help="Enable/disable expert reviewer feedback (placeholder)."),
):
    """
    CLI to analyze research proposals against a call and generate reports.
    Default paths if arguments are not provided:
      Call PDF: First PDF/DOC/DOCX in data/call/
      Proposals Dir: data/proposal/
      Questions File: data/Questions.txt
    """
    # --- Setup LLM Provider Configuration ---
    import os
    # Set environment variables if CLI options are provided
    if llm_provider:
        os.environ["LLM_PROVIDER"] = llm_provider
    if local_llm_url:
        os.environ["LOCAL_LLM_BASE_URL"] = local_llm_url
    if local_llm_model:
        os.environ["LOCAL_LLM_MODEL"] = local_llm_model
    if local_llm_api_key:
        os.environ["LOCAL_LLM_API_KEY"] = local_llm_api_key
    
    # --- Setup effective consoles based on output_format ---
    # If output_format is json, all non-data console output goes to stderr.
    # Otherwise, it goes to stdout via the global console objects.
    effective_info_console: Console
    effective_rule_console: Console

    if output_format == "json":
        effective_info_console = Console(file=sys.stderr, style="blue")
        effective_rule_console = Console(file=sys.stderr)
    else:
        effective_info_console = info_console # Use global info_console (stdout)
        effective_rule_console = console     # Use global console (stdout)

    # --- Path and File Setup ---
    data_dir = PROJECT_ROOT / "data"
    if not call_pdf:
        call_pdf = find_first_document(data_dir / "call", ["*.pdf", "*.doc", "*.docx"])
        if call_pdf: effective_info_console.print(f"No call PDF specified, using found: {call_pdf.name}")
        else: error_console.print("Error: No call PDF specified and none found in data/call/. Please specify with --call-pdf."); raise typer.Exit(code=1)

    if not questions_file:
        questions_file = data_dir / "Questions.txt"
        if questions_file.exists(): effective_info_console.print(f"No questions file specified, using default: {questions_file.name}")
        else: error_console.print("Error: No questions file specified and default Questions.txt not found. Please specify with --questions-file."); raise typer.Exit(code=1)
    


    proposal_paths_to_process: List[Path] = []
    if single_proposal_pdf:
        proposal_paths_to_process = [single_proposal_pdf]
    elif proposals_dir and proposals_dir.is_dir():
        proposal_paths_to_process = sorted([f for f in proposals_dir.glob("*.pdf")])
        if not proposal_paths_to_process:
            error_console.print(f"No PDF proposals found in directory: {proposals_dir}"); raise typer.Exit(code=1)
    else: # Default to data/proposal if nothing else specified
        default_proposals_dir = data_dir / "proposal"
        if default_proposals_dir.is_dir():
            proposal_paths_to_process = sorted([f for f in default_proposals_dir.glob("*.pdf")])
            if proposal_paths_to_process: effective_info_console.print(f"No proposal source specified, using PDFs from: {default_proposals_dir}")
            else: error_console.print(f"No proposals specified and none found in default directory: {default_proposals_dir}. Use --proposals-dir or --proposal-pdf."); raise typer.Exit(code=1)
        else: error_console.print(f"Default proposal directory {default_proposals_dir} not found and no proposals specified."); raise typer.Exit(code=1)

    if not proposal_paths_to_process:
        error_console.print("No proposal PDF files to process."); raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Initialize Services ---
    from proposal_analyzer.config import get_llm_provider, get_local_llm_config
    
    # Get actual provider configuration
    current_provider = get_llm_provider()
    
    # Determine model names based on provider
    if current_provider == 'local':
        local_config = get_local_llm_config()
        analysis_model = local_config["model_name"]
        reviewer_model = local_config["model_name"]
        effective_info_console.print(f"Using Local LLM: {local_config['model_name']} at {local_config['base_url']}")
    else:
        analysis_model = 'gpt-4o'
        reviewer_model = 'gpt-4o'
        effective_info_console.print(f"Using OpenAI models: {analysis_model}")
    
    analysis_service = AnalysisService(project_root=PROJECT_ROOT, model_name=analysis_model)
    reviewer_feedback_service = ReviewerFeedbackService(model_name=reviewer_model) # Initialize ReviewerFeedbackService
    # PDFExportService is initialized when needed, per proposal.

    # --- Main Processing Loop ---
    for proposal_idx, proposal_pdf_path in enumerate(proposal_paths_to_process):
        effective_rule_console.rule(f"[bold blue]Processing Proposal: {proposal_pdf_path.name}[/bold blue] ({proposal_idx + 1}/{len(proposal_paths_to_process)})", style="blue")
        
        all_results_for_proposal: Dict[str, List[Dict[str, Any]]] = {
            "proposal_analysis": [],
            "reviewer_feedback": []
        }
        
        effective_llm_instructions = llm_instructions if llm_instructions else None

        # --- Text Extraction for all services ---
        # Extract text from documents once upfront for all services that need it
        effective_info_console.print(f"Extracting text from {proposal_pdf_path.name}...")
        proposal_text_content: Optional[str] = extract_text_from_document(proposal_pdf_path)
        if not proposal_text_content:
            effective_info_console.print(f"Warning: Could not extract text from {proposal_pdf_path.name}. Some services may be skipped or report errors.")
        
        effective_info_console.print(f"Extracting text from call document {call_pdf.name}...")
        call_text_content: Optional[str] = extract_text_from_document(call_pdf)
        if not call_text_content:
            effective_info_console.print(f"Warning: Could not extract text from call document {call_pdf.name}. Some services may be affected.")
        
        effective_info_console.print(f"Reading questions from {questions_file.name}...")
        questions_content = read_questions_content(str(questions_file))
        if not questions_content and analyze_proposal_opt:
            error_console.print(f"Error: Questions file '{questions_file}' is empty or could not be read."); raise typer.Exit(code=1)

        # 1. Core Proposal Analysis (Optional)
        if analyze_proposal_opt:
            effective_info_console.print(f"Running core proposal analysis using model: {analysis_service.model_name}...")
            if proposal_text_content and call_text_content and questions_content:
                # Use pre-extracted text for analysis
                try:
                    analysis_findings = analysis_service.analyze_proposal_with_text(
                        call_text=call_text_content,
                        proposal_text=proposal_text_content,
                        questions_content=questions_content,
                        llm_instructions=effective_llm_instructions,
                        logger=None
                    )
                    all_results_for_proposal["proposal_analysis"] = analysis_findings
                except Exception as e:
                    error_console.print(f"Error during proposal analysis: {e}")
                    all_results_for_proposal["proposal_analysis"] = [{
                        "question": "Analysis Error",
                        "answer": False,
                        "reasoning": f"Failed to analyze proposal due to error: {str(e)}",
                        "raw_response": str(e)
                    }]
            else:
                # Handle case where text extraction failed
                error_console.print("Error: Cannot perform analysis - text extraction failed for one or more documents.")
                missing_docs = []
                if not proposal_text_content:
                    missing_docs.append(f"proposal ({proposal_pdf_path.name})")
                if not call_text_content:
                    missing_docs.append(f"call document ({call_pdf.name})")
                if not questions_content:
                    missing_docs.append(f"questions file ({questions_file.name})")
                
                all_results_for_proposal["proposal_analysis"] = [{
                    "question": "Text Extraction Error",
                    "answer": False,
                    "reasoning": f"Could not extract text from: {', '.join(missing_docs)}. Analysis cannot proceed without readable text content.",
                    "raw_response": "Text extraction failed"
                }]
        else:
            effective_info_console.print("Skipping core proposal analysis.")

        # 2. Reviewer Feedback (Optional)
        if reviewer_feedback_opt:
            effective_info_console.print(f"Requesting expert reviewer feedback (model: {reviewer_feedback_service.model_name})...")
            if proposal_text_content:
                reviewer_findings = reviewer_feedback_service.generate_feedback(
                    proposal_text=proposal_text_content, 
                    proposal_filename=proposal_pdf_path.name,
                    call_text=call_text_content # Pass extracted call text
                )
                all_results_for_proposal["reviewer_feedback"] = reviewer_findings
            else:
                all_results_for_proposal["reviewer_feedback"] = [{
                    "type": "reviewer_feedback_error",
                    "service_name": "Expert Reviewer Feedback",
                    "original_snippet": proposal_pdf_path.name,
                    "suggestion": "N/A",
                    "explanation": "Skipped reviewer feedback because text could not be extracted from the proposal PDF.",
                    "line_number": -1, "char_offset_start_in_doc": 0, "line_with_error": None
                }]
        else:
            effective_info_console.print("Skipping expert reviewer feedback.")

        # --- Output Generation ---
        # For JSON output, we need a strategy to combine all selected results.
        # The current JSON stream for `analyze_proposal_opt` is separate.
        # For simplicity in this refactor, if `output_format == 'json'`, we might only output
        # the `analyze_proposal_opt` stream for now, or error if multiple things are selected.
        # A better JSON output would be a single JSON with keys for each service's results.

        if output_format == "rich":
            _display_rich_results(all_results_for_proposal, effective_llm_instructions if analyze_proposal_opt else None)
        elif output_format == "pdf":
            pdf_file_name = f"{proposal_pdf_path.stem}_analysis_report.pdf"
            pdf_export_path = output_dir / pdf_file_name
            effective_info_console.print(f"Generating PDF report: {pdf_export_path}...")
            pdf_exporter = PDFExportService(export_path_str=str(pdf_export_path))
            # generate_analysis_report_pdf needs to be updated to handle all_results_for_proposal
            # For now, it might only handle the 'proposal_analysis' part or need a new method
            # Let's assume a new or modified method:
            generated_path = pdf_exporter.generate_full_report_pdf(
                proposal_filename=proposal_pdf_path.name,
                all_findings=all_results_for_proposal,
                # We might also want to pass the call_pdf name, questions used, models used, etc. for the PDF header
                call_document_name=call_pdf.name,
                questions_source_name=questions_file.name,
                # Include which services were run
                services_run={
                    "Core Analysis": analyze_proposal_opt,
                    "Reviewer Feedback": reviewer_feedback_opt
                },
                models_used={
                    "Core Analysis Model": analysis_service.model_name if analyze_proposal_opt else "N/A",
                    "Reviewer Feedback Model": reviewer_feedback_service.model_name if reviewer_feedback_opt else "N/A"
                }
            )
            if generated_path:
                effective_info_console.print(f"PDF report generated successfully: {generated_path}")
            else:
                error_console.print(f"Failed to generate PDF report for {proposal_pdf_path.name}")
        elif output_format == "json":
            # Output the entire collected results as a single JSON object to stdout
            # This is what AnalysisService from app.py expects.
            # Ensure this goes to sys.stdout directly and nothing else does.
            sys.stdout.write(json.dumps(all_results_for_proposal, indent=2) + "\n")
            sys.stdout.flush()
        
        # Add a visual separator in non-JSON modes
        if output_format != "json":
            effective_rule_console.line(2)

    if output_format != "json":
        effective_info_console.print("CLI processing finished.")

if __name__ == "__main__":
    app()

