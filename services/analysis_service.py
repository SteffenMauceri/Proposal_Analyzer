from pathlib import Path
import subprocess
import json
from typing import List, Dict, Any, Optional, Callable, Iterator, Tuple
import html



# Assuming main.py CLI is the primary way to trigger the core analysis for now.
# We will adapt this if direct Python calls to analyzer.analyze become preferred
# over subprocess for the web app.

class AnalysisService:
    def __init__(self, project_root: Path, model_name: str = "gpt-4.1-mini"):
        self.project_root = project_root
        self.model_name = model_name

    def _build_analysis_command(
        self,
        call_pdf_path: Optional[Path],  # Now optional
        proposals_dir_path: Path, # This might become optional or change if only --proposal-pdf is used
        questions_file_path: Optional[Path],
        selected_proposal_filenames: Optional[List[str]] = None,
        analyze_proposal_opt: bool = True,
        reviewer_feedback_opt: bool = False
    ) -> List[str]:
        base_command = [
            'python', str(self.project_root / 'main.py'),
            '--output-format', 'json'  # Essential for service to parse results
        ]
        
        # Only add call-pdf if provided
        if call_pdf_path:
            base_command.extend(['--call-pdf', str(call_pdf_path.resolve())])

        # Prioritize --proposal-pdf if a single proposal is selected, as per main.py hint
        if selected_proposal_filenames and len(selected_proposal_filenames) == 1:
            # Assuming proposals_dir_path is the directory where this selected file resides
            proposal_file_path = proposals_dir_path / selected_proposal_filenames[0]
            base_command.extend(['--proposal-pdf', str(proposal_file_path.resolve())])
            # If --proposal-pdf is used, --proposals-dir might be redundant or conflict.
            # Depending on main.py's exact behavior, we might remove --proposals-dir here.
            # For now, let's assume main.py handles it or ignores --proposals-dir if --proposal-pdf is given.
            # If not, we might need to remove: base_command.extend(['--proposals-dir', str(proposals_dir_path.resolve())])
            # and only add it if not using --proposal-pdf.
            # Let's add proposals_dir_path for now, assuming it might still be needed for context or if main.py is flexible.
            base_command.extend(['--proposals-dir', str(proposals_dir_path.resolve())])

        elif proposals_dir_path: # Fallback or if multiple files (not current chat UI case)
            base_command.extend(['--proposals-dir', str(proposals_dir_path.resolve())])
            if selected_proposal_filenames: # If multiple selected (not used by chat UI currently)
                for p_filename in selected_proposal_filenames:
                    # This was the problematic part. If main.py doesn't support selecting from a dir this way, 
                    # this whole block for multiple selections might need rethinking based on main.py capability.
                    # For now, commenting out the erroneous --selected-proposal for multiple files.
                    # base_command.extend(['--selected-proposal', p_filename])
                    pass # Placeholder: how does main.py handle multiple selections from a dir?
        
        if questions_file_path:
            base_command.extend(['--questions-file', str(questions_file_path.resolve())])
        
        # Add flags for selective services based on options
        if not analyze_proposal_opt: # Typer uses --no-analyze-proposal to disable
            base_command.append('--no-analyze-proposal')
        


        if reviewer_feedback_opt:
            base_command.append('--reviewer-feedback')
        # else: base_command.append('--no-reviewer-feedback')
        
        # Add LLM provider configuration to the command
        from proposal_analyzer.config import get_llm_provider, get_local_llm_config
        current_provider = get_llm_provider()
        base_command.extend(['--llm-provider', current_provider])
        
        if current_provider == 'local':
            local_config = get_local_llm_config()
            base_command.extend(['--local-llm-url', local_config['base_url']])
            base_command.extend(['--local-llm-model', local_config['model_name']])
            base_command.extend(['--local-llm-api-key', local_config['api_key']])
        
        # Removed the old --selected-proposal logic that caused the error.
        # if selected_proposal_filenames and not ('--proposal-pdf' in base_command):
        #     for p_filename in selected_proposal_filenames:
        #         base_command.extend(['--selected-proposal', p_filename]) # This was the error source

        return base_command

    def run_analysis_stream(
        self,
        call_pdf_path: Optional[Path],  # Now optional
        proposals_dir_path: Path,
        questions_file_path: Optional[Path],
        selected_proposal_filenames: Optional[List[str]] = None,
        logger: Optional[Any] = None, # Pass Flask app.logger or any logger
        analyze_proposal_opt: bool = True,
        reviewer_feedback_opt: bool = False
    ) -> Iterator[str]:
        """
        Runs the analysis by calling main.py as a subprocess and streams progress/results.
        Yields Server-Sent Event (SSE) formatted strings.
        """
        command = self._build_analysis_command(
            call_pdf_path,
            proposals_dir_path,
            questions_file_path,
            selected_proposal_filenames,
            analyze_proposal_opt,
            reviewer_feedback_opt
        )

        if logger:
            logger.info(f"AnalysisService: Starting analysis with command: {' '.join(command)}")
        yield f"data: {json.dumps({'type': 'log', 'message': 'Analysis process starting via AnalysisService...'})}\n\n"

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            bufsize=1  # Line buffered
        )

        # Stream stderr for logs and progress
        if process.stderr:
            for line in iter(process.stderr.readline, ''):
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                if logger:
                    # Promote to ERROR so messages appear even when app logger is INFO on Render
                    logger.error(f"AnalysisService (stderr from main.py): {line_stripped}")
                
                event_data = {}
                if line_stripped.startswith("PROGRESS:"):
                    progress_content = line_stripped[len("PROGRESS:"):].strip()
                    try:
                        progress_json = json.loads(progress_content)
                        event_data = {"type": "progress", "data": progress_json}
                    except json.JSONDecodeError:
                        event_data = {"type": "progress", "data": {"message": html.escape(progress_content)}}
                else:
                    event_data = {"type": "log", "message": html.escape(line_stripped)}
                yield f"data: {json.dumps(event_data)}\n\n"
            process.stderr.close()

        stdout_data, stderr_data_after_wait = process.communicate()

        if logger:
            logger.info(f"AnalysisService: main.py process finished with return code: {process.returncode}")

        if stderr_data_after_wait:
            for line in stderr_data_after_wait.strip().split('\n'):
                if line.strip() and logger:
                    # Promote to ERROR so messages appear even when app logger is INFO on Render
                    logger.error(f"AnalysisService (Remaining stderr from main.py): {html.escape(line.strip())}")
                    yield f"data: {json.dumps({'type': 'log', 'message': f'Post-stream stderr: {html.escape(line.strip())}'})}\n\n"

        if process.returncode != 0:
            error_message = f"Analysis script failed (exit code {process.returncode})."
            if logger:
                logger.error(error_message)
                # Dump captured stdout/stderr to help debugging on Render
                if stdout_data:
                    logger.error(f"main.py stdout:\n{stdout_data.strip()}")
                if stderr_data_after_wait:
                    logger.error(f"main.py stderr:\n{stderr_data_after_wait.strip()}")
            details = html.escape(stdout_data.strip()) if stdout_data else ''
            if stderr_data_after_wait: # Append any crucial error output from stderr if not already in stdout
                 details += f" Stderr: {html.escape(stderr_data_after_wait.strip())}"

            yield f"data: {json.dumps({'type': 'error', 'message': error_message, 'details': details})}\n\n"
        else:
            if stdout_data:
                try:
                    analysis_results = json.loads(stdout_data)
                    yield f"data: {json.dumps({'type': 'result', 'payload': analysis_results})}\n\n"
                    if logger:
                        logger.info("AnalysisService: Successfully parsed and sent analysis results.")
                except json.JSONDecodeError as e:
                    if logger:
                        logger.error(f"AnalysisService: Failed to parse JSON result from main.py: {e}", exc_info=True)
                        logger.error(f"AnalysisService: Raw stdout from main.py: {stdout_data}")
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to parse analysis results from script (not valid JSON).', 'details': html.escape(stdout_data)})}\n\n"
            else:
                if logger:
                    logger.warning("AnalysisService: Analysis script succeeded but produced no stdout data.")
                yield f"data: {json.dumps({'type': 'log', 'message': 'Analysis script completed but returned no data.'})}\n\n"
        
        yield f"data: {json.dumps({'type': 'stream_end', 'message': 'Stream ended from AnalysisService.'})}\n\n"


    def run_analysis_blocking(
        self,
        call_pdf_path: Optional[Path],  # Now optional
        proposals_dir_path: Path,
        questions_file_path: Path,
        selected_proposal_filenames: Optional[List[str]] = None,
        logger: Optional[Any] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        analyze_proposal_opt: bool = True,
        reviewer_feedback_opt: bool = False
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Runs the analysis by calling main.py as a subprocess and waits for completion.
        Returns the parsed JSON result or an error message.
        This version is more suitable for CLI or non-streaming backend tasks.
        """
        command = self._build_analysis_command(
            call_pdf_path,
            proposals_dir_path,
            questions_file_path,
            selected_proposal_filenames,
            analyze_proposal_opt,
            reviewer_feedback_opt
        )

        if logger:
            logger.info(f"AnalysisService (blocking): Starting analysis with command: {' '.join(command)}")
        
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )

        # Capture stdout and stderr
        stdout_data, stderr_data = process.communicate()

        if logger:
            logger.info(f"AnalysisService (blocking): main.py process finished with return code: {process.returncode}")
            if stderr_data:
                for line in stderr_data.strip().split('\n'):
                    if line.strip():
                        # If a progress callback is provided, try to parse and send progress
                        if progress_callback and line.strip().startswith("PROGRESS:"):
                            progress_content = line.strip()[len("PROGRESS:"):].strip()
                            try:
                                progress_json = json.loads(progress_content)
                                progress_callback({"type": "progress", "data": progress_json})
                            except json.JSONDecodeError:
                                progress_callback({"type": "progress", "data": {"message": progress_content}}) # send as plain message
                        else: # Otherwise log as normal stderr
                             logger.debug(f"AnalysisService (blocking) (stderr from main.py): {line.strip()}")


        if process.returncode != 0:
            error_message = f"Analysis script failed (exit code {process.returncode})."
            if stdout_data: # Include stdout if available
                 error_message += f" Script stdout: {stdout_data.strip()}"
            if stderr_data: # Include stderr if available
                 error_message += f" Script stderr: {stderr_data.strip()}"
            if logger:
                logger.error(error_message)
            return None, error_message
        else:
            if stdout_data:
                try:
                    analysis_results = json.loads(stdout_data)
                    if logger:
                        logger.info("AnalysisService (blocking): Successfully parsed analysis results.")
                    return analysis_results, None
                except json.JSONDecodeError as e:
                    error_msg = f"Failed to parse analysis results from script: {e}. Raw output: {stdout_data}"
                    if logger:
                        logger.error(error_msg, exc_info=True)
                    return None, error_msg
            else:
                # This case should ideally not happen if output_format is json and script succeeds
                warn_msg = "Analysis script succeeded but produced no stdout data."
                if logger:
                    logger.warning(warn_msg)
                # It's not an error per se, but no data was returned.
                return [], warn_msg # Return empty list and the warning 

    def analyze_proposal_with_text(
        self,
        call_text: str,
        proposal_text: str,
        questions_content: str,
        llm_instructions: Optional[str] = None,
        logger: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Performs analysis for a single proposal using pre-extracted text.
        This method directly uses the analyzer with extracted text, avoiding file I/O.
        Uses the model specified during service initialization.
        """
        if logger:
            logger.info(f"AnalysisService (text-based): Analyzing proposal with model {self.model_name}")

        try:
            # Import here to avoid circular imports
            from proposal_analyzer.rules_engine import evaluate
            from proposal_analyzer.llm_client import query as ask_llm
            from functools import partial
            
            # Parse questions content into a list
            questions = [line.strip() for line in questions_content.split('\n') if line.strip()]
            
            # Create context dictionary like the analyzer does
            context = {
                "call": call_text,
                "proposal": proposal_text
            }
            
            results: List[Dict[str, Any]] = []
            # Get the current provider configuration
            from proposal_analyzer.config import get_llm_provider
            current_provider = get_llm_provider()
            llm_call_for_evaluate = partial(ask_llm, model=self.model_name, client=None, provider=current_provider)
            
            # Process each question
            for q_text in questions:
                if logger:
                    logger.debug(f"AnalysisService (text-based): Processing question: {q_text[:50]}...")
                result = evaluate(question=q_text, context=context, ask=llm_call_for_evaluate, instructions=llm_instructions)
                results.append(result)
            
            if logger:
                logger.info(f"AnalysisService (text-based): Successfully analyzed {len(questions)} questions")
            return results
        except Exception as e:
            if logger:
                logger.error(f"AnalysisService (text-based): Error during analysis: {e}", exc_info=True)
            # Re-raise the exception so the caller (main.py) can handle it
            raise

 