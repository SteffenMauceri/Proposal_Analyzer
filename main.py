import typer
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import json
import sys
import html

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax

# Service Imports
from services.analysis_service import AnalysisService
from services.pdf_export_service import PDFExportService
from services.spell_checking_service import SpellCheckingService # New import
from services.reviewer_feedback_service import ReviewerFeedbackService # Added for reviewer feedback

# Utility Imports
from utils.file_helpers import find_first_document, read_questions_content # Assuming read_questions_content is needed or was there

# Import for LLM client for summary generation
from proposal_analyzer.llm_client import query as llm_query # Renamed to avoid conflict if query is defined locally

console = Console()
error_console = Console(stderr=True, style="bold red")
info_console = Console(style="blue") # For informational messages

# --- Project Root (ensure it's defined, e.g., if AnalysisService needs it) ---
PROJECT_ROOT = Path(__file__).resolve().parent

# --- Placeholder Services ---
# Removed get_reviewer_feedback_placeholder as it's replaced by the service
# Removed get_nasa_pm_feedback_placeholder 

def generate_consolidated_summary(
    proposal_filename: str, 
    all_findings: Dict[str, List[Dict[str, Any]]],
    services_run: Dict[str, bool],
    model_for_summary: str = "gpt-4.1-nano", # Or make this configurable
    logger_console: Optional[Console] = None # New argument for logging
) -> str:
    """Generates a consolidated summary of all findings using an LLM."""

    services_with_findings_count = 0
    summary_prompt_parts = [
        f"The following automated analyses were performed on the proposal document: '{html.escape(proposal_filename)}'.\n"
    ]

    # Core Proposal Analysis Summary
    if services_run.get("Core Analysis", False):
        analysis_items = all_findings.get("proposal_analysis")
        if analysis_items: # Check if there are actual findings
        num_questions = len(analysis_items)
        summary_prompt_parts.append(
                f"- Core Proposal Q&A: {num_questions} question(s) were addressed. Key insights should be reviewed in the detailed section."
        )
            services_with_findings_count += 1
        else:
            summary_prompt_parts.append("- Core Proposal Q&A: Selected, but no findings were reported or an issue occurred.")

    # Spell Check Summary
    if services_run.get("Spell Check", False):
        spell_issues = all_findings.get("spell_check")
        if spell_issues: # Check if there are actual findings
        if len(spell_issues) == 1 and spell_issues[0].get("type") == "error_extraction":
            summary_prompt_parts.append("- Spell & Grammar Check: Failed to extract text from the document for spell checking.")
        else:
                # Filter out error_extraction type before counting issues for summary part
                actual_issues = [issue for issue in spell_issues if issue.get('type') != "error_extraction" and issue.get("suggestion")]
                num_spell_issues = len(actual_issues)
            if num_spell_issues > 0:
                    issue_types = list(set(issue.get('type', 'unknown') for issue in actual_issues))
                summary_prompt_parts.append(
                        f"- Spell & Grammar Check: Identified {num_spell_issues} potential issue(s). Types included: {(', '.join(issue_types) if issue_types else 'various')}."
                )
                    services_with_findings_count += 1
                else:
                    summary_prompt_parts.append("- Spell & Grammar Check: No actionable spelling or grammar issues were identified (though the service ran).")
            else:
            summary_prompt_parts.append("- Spell & Grammar Check: Selected, but no findings were reported or an issue occurred.")

    # Reviewer Feedback Summary
    if services_run.get("Reviewer Feedback", False):
        reviewer_items = all_findings.get("reviewer_feedback")
        if reviewer_items: # Check if there are actual findings
            is_error = any(item.get("type", "").endswith("_error") for item in reviewer_items)
            has_actual_feedback = any(item.get("suggestion") and not item.get("type", "").endswith("_error") for item in reviewer_items)
            if is_error:
                summary_prompt_parts.append("- Expert Reviewer Feedback: Selected, but an error occurred during feedback generation. Check details.")
            elif has_actual_feedback:
                summary_prompt_parts.append("- Expert Reviewer Feedback: Feedback was generated and is available in the detailed section.")
                services_with_findings_count += 1
            else: 
                summary_prompt_parts.append("- Expert Reviewer Feedback: Selected and ran, but no specific feedback was generated or an error occurred. Check details.")
        else: 
             summary_prompt_parts.append("- Expert Reviewer Feedback: Selected, but could not be run or no findings were reported (e.g., due to prior error like text extraction failure).")

    # Conditional LLM call for summary
    if services_with_findings_count == 0:
        return "No analysis services produced actionable findings. Therefore, no consolidated summary can be generated. Please review the detailed sections for any specific error messages or logs."
    elif services_with_findings_count == 1:
        single_service_ran_name = "an unspecified service"
        if services_run.get("Core Analysis") and any(all_findings.get("proposal_analysis",[])):
            single_service_ran_name = "Core Proposal Q&A"
        elif services_run.get("Spell Check") and any(s.get("suggestion") for s in all_findings.get("spell_check", []) if s.get("type") != "error_extraction"):
            single_service_ran_name = "Spell & Grammar Check"
        elif services_run.get("Reviewer Feedback") and any(r.get("suggestion") for r in all_findings.get("reviewer_feedback", []) if not r.get("type", "").endswith("_error")):
            single_service_ran_name = "Expert Reviewer Feedback"
        
        return f"Only one analysis service ({single_service_ran_name}) produced actionable findings. A consolidated summary is typically generated for multiple services. Please review the detailed results for {single_service_ran_name}."

    # If services_with_findings_count > 1, proceed with LLM summary generation
    user_content = "\n".join(summary_prompt_parts) + "\n\nPlease provide a very brief (2-4 sentences) executive summary of the overall status and key takeaways from these automated checks."
    
    system_prompt = (
        "You are an expert assistant. Your task is to synthesize the provided information about an automated analysis "
        "of a research proposal and generate a concise executive summary. Focus on the high-level status and actionable insights if apparent."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

    if logger_console:
        logger_console.print(f"Generating consolidated summary using model: {model_for_summary}...")
    else: # Fallback to global if not provided (e.g. if called from elsewhere not updated yet)
        info_console.print(f"Generating consolidated summary using model: {model_for_summary}...")
    # info_console.print(f"Summary User Prompt:\\n{user_content}") # For debugging prompt

    try:
        summary_response = llm_query(messages=messages, model=model_for_summary) # Assuming llm_query uses default client
        return summary_response.strip()
    except Exception as e:
        error_console.print(f"Error generating consolidated summary with LLM: {e}")
        return "Failed to generate consolidated summary due to an error."

app = typer.Typer(
    name="proposal_analyzer_cli",
    help="CLI tool to analyze proposals, check spelling, and generate reports.",
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
        elif service_key == "spell_check":
            issues_by_line = {}
            for issue in findings:
                line_num = issue.get('line_number', -1)
                if line_num not in issues_by_line:
                    issues_by_line[line_num] = []
                issues_by_line[line_num].append(issue)

            for line_num in sorted(issues_by_line.keys()):
                line_issues = issues_by_line[line_num]
                line_content = line_issues[0].get('line_with_error', 'N/A (or PDF line)')
                if line_num == -1 and "PDF" in line_content : # Handle PDF case where line_num is -1
                     console.print(f"\n[bold cyan]Page/General Finding (PDF):[/bold cyan]")
                elif line_num != -1 :
                     console.print(f"\n[bold cyan]Line {line_num}:[/bold cyan] [italic]{line_content}[/italic]")
                
                for issue in line_issues:
                    original = issue.get('original_snippet', 'N/A')
                    suggestion = issue.get('suggestion', 'N/A')
                    issue_type = issue.get('type', 'N/A')
                    explanation = issue.get('explanation', '')
                    offset = issue.get('char_offset_start_in_doc', 'N/A')
                    console.print(f"  - [red]'{original}'[/red] (Offset: {offset}) -> [green]'{suggestion}'[/green] ([dim]{issue_type}[/dim])")
                    if explanation and explanation != "N/A":
                        console.print(f"    [dim]Why: {explanation}[/dim]")
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
    model: str = typer.Option("gpt-4.1-mini", "--model", "-m", help="OpenAI model to use for analysis."),
    llm_instructions: Optional[str] = typer.Option(None, "--llm-instructions", "-i", help="Custom instructions for the LLM (for core proposal analysis)."),
    output_format: str = typer.Option("rich", "--output-format", "-of", help="Output format: 'rich' (console) or 'json' or 'pdf'."),
    
    # New options for selective analysis
    analyze_proposal_opt: bool = typer.Option(True, "--analyze-proposal/--no-analyze-proposal", help="Enable/disable core proposal Q&A analysis."),
    spell_check_opt: bool = typer.Option(False, "--spell-check/--no-spell-check", help="Enable/disable spell and grammar checking."),
    reviewer_feedback_opt: bool = typer.Option(False, "--reviewer-feedback/--no-reviewer-feedback", help="Enable/disable expert reviewer feedback (placeholder)."),
    spell_check_model: str = typer.Option("gpt-4.1-nano", "--spell-check-model", help="Model to use specifically for spell checking.")

):
    """
    CLI to analyze research proposals against a call, check spelling, and generate reports.
    Default paths if arguments are not provided:
      Call PDF: First PDF/DOC/DOCX in data/call/
      Proposals Dir: data/proposal/
      Questions File: data/Questions_default.txt
    """
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
        questions_file = data_dir / "Questions_default.txt"
        if questions_file.exists(): effective_info_console.print(f"No questions file specified, using default: {questions_file.name}")
        else: error_console.print("Error: No questions file specified and default Questions_default.txt not found. Please specify with --questions-file."); raise typer.Exit(code=1)
    
    questions_content = read_questions_content(str(questions_file))
    if not questions_content and analyze_proposal_opt: # Only critical if proposal analysis is on
        error_console.print(f"Error: Questions file '{questions_file}' is empty or could not be read."); raise typer.Exit(code=1)

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
    analysis_service = AnalysisService(project_root=PROJECT_ROOT)
    spell_checking_service = SpellCheckingService(model_name=spell_check_model) # Using dedicated model
    reviewer_feedback_service = ReviewerFeedbackService(model_name=model) # Initialize ReviewerFeedbackService
    # PDFExportService is initialized when needed, per proposal.

    # --- Main Processing Loop ---
    for proposal_idx, proposal_pdf_path in enumerate(proposal_paths_to_process):
        effective_rule_console.rule(f"[bold blue]Processing Proposal: {proposal_pdf_path.name}[/bold blue] ({proposal_idx + 1}/{len(proposal_paths_to_process)})", style="blue")
        
        all_results_for_proposal: Dict[str, List[Dict[str, Any]]] = {
            "proposal_analysis": [],
            "spell_check": [],
            "reviewer_feedback": []
        }
        
        effective_llm_instructions = llm_instructions if llm_instructions else questions_content

        # 1. Core Proposal Analysis (Optional)
        if analyze_proposal_opt:
            effective_info_console.print(f"Running core proposal analysis using model: {model}...")
            # Simplified: Always call analyze_proposal_directly for consistency.
            # The output_format='json' will be handled by printing all_results_for_proposal at the end.
            analysis_findings = analysis_service.analyze_proposal_directly(
                call_pdf_path_str=str(call_pdf),
                proposal_pdf_path_str=str(proposal_pdf_path),
                questions_file_path_str=str(questions_file), 
                model_name=model,
                llm_instructions=effective_llm_instructions,
                logger=None # Or pass a logger if you have one configured for CLI
            )
            all_results_for_proposal["proposal_analysis"] = analysis_findings
        else:
            effective_info_console.print("Skipping core proposal analysis.")

        # --- Text Extraction for services that need it ---
        # Extract text from proposal PDF once if spell check or reviewer feedback is enabled
        proposal_text_content: Optional[str] = None
        if spell_check_opt or reviewer_feedback_opt: # Add other services here if they need text
            # Using spell_checking_service's extractor. Could be a global util too.
            effective_info_console.print(f"Extracting text from {proposal_pdf_path.name} for spell check/feedback...")
            proposal_text_content = spell_checking_service._extract_text_from_pdf(proposal_pdf_path)
            if not proposal_text_content:
                effective_info_console.print(f"Warning: Could not extract text from {proposal_pdf_path.name}. Some services may be skipped or report errors.")
        
        call_text_content: Optional[str] = None
        if reviewer_feedback_opt: # Assuming reviewer feedback might use call text
             effective_info_console.print(f"Extracting text from call document {call_pdf.name} for feedback context...")
             # We need a generic PDF text extractor here, assuming call_pdf is PDF
             # Reusing spell_checking_service._extract_text_from_pdf for now
             # This implies call_pdf must be a PDF. If it can be .doc/.docx, this needs more robust extraction.
             if str(call_pdf).lower().endswith('.pdf'):
                call_text_content = spell_checking_service._extract_text_from_pdf(call_pdf)
                if not call_text_content:
                    effective_info_console.print(f"Warning: Could not extract text from call document {call_pdf.name}.")
             else:
                 effective_info_console.print(f"Warning: Call document {call_pdf.name} is not a PDF, cannot extract text for reviewer feedback context.")

        # 2. Spell Checking (Optional)
        if spell_check_opt:
            effective_info_console.print(f"Running spell check using model: {spell_check_model}...")
            if proposal_text_content:
                spell_check_findings = spell_checking_service.check_document_text(proposal_text_content, is_pdf_source=True)
            else:
                # Fallback to original method if text extraction failed above but service tries again
            spell_check_findings = spell_checking_service.check_pdf_document(proposal_pdf_path)
            all_results_for_proposal["spell_check"] = spell_check_findings
        else:
            effective_info_console.print("Skipping spell check.")

        # 3. Reviewer Feedback (Placeholder, Optional)
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
                    "Spell Check": spell_check_opt,
                    "Reviewer Feedback": reviewer_feedback_opt
                },
                models_used={
                    "Core Analysis Model": model if analyze_proposal_opt else "N/A",
                    "Spell Check Model": spell_check_model if spell_check_opt else "N/A"
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

