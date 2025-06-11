import os
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, stream_with_context, session
from pathlib import Path
import subprocess
import json
import html
import secrets
import re

# PDF Generation
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch

# Import helpers
from utils.file_helpers import get_proposals_from_dir, read_questions_content, get_call_documents
from services.pdf_export_service import PDFExportService
from services.analysis_service import AnalysisService # Import the service

# Import the LLM query function
from proposal_analyzer.llm_client import query as ask_llm

# Assuming main.py is in the same directory or accessible in PYTHONPATH
# This might need adjustment based on your project structure if main_cli is not easily importable.
# For now, we will call it as a subprocess.

app = Flask(__name__)

# Secret key for session management
# In a production app, set this from an environment variable or a config file
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(16))

# Define project root for easier path construction
PROJECT_ROOT = Path(__file__).parent

# Defaults for initial page load
app.config['DEFAULT_CALL_FILES_DIR'] = PROJECT_ROOT / 'data' / 'call'
app.config['DEFAULT_PROPOSALS_DIR'] = str(PROJECT_ROOT / 'data' / 'proposal')
app.config['DEFAULT_QUESTIONS_FILE'] = str(PROJECT_ROOT / 'data' / 'Questions.txt')
app.config['DEFAULT_PDF_EXPORT_DIR'] = PROJECT_ROOT / 'exports' 

# Ensure base data directory and subdirectories exist
(PROJECT_ROOT / 'data' / 'call').mkdir(parents=True, exist_ok=True)
(PROJECT_ROOT / 'data' / 'proposal').mkdir(parents=True, exist_ok=True)
app.config['DEFAULT_PDF_EXPORT_DIR'].mkdir(parents=True, exist_ok=True) 

# Ensure chat upload directory exists
CHAT_UPLOADS_DIR = PROJECT_ROOT / 'data' / 'chat_uploads'
CHAT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Directory for uploads from the main UI
MAIN_UPLOADS_DIR = PROJECT_ROOT / 'data' / 'main_uploads'
(MAIN_UPLOADS_DIR / 'call').mkdir(parents=True, exist_ok=True)
(MAIN_UPLOADS_DIR / 'proposal').mkdir(parents=True, exist_ok=True)
(MAIN_UPLOADS_DIR / 'questions').mkdir(parents=True, exist_ok=True)

# Store classified file paths here, distinct from unclassified ones
CHAT_UPLOADED_FILES_SESSION_KEY = 'chat_uploaded_classified_files'
CHAT_UNCLASSIFIED_FILES_SESSION_KEY = 'chat_unclassified_files'

# Initialize services
analysis_service = AnalysisService(project_root=PROJECT_ROOT)

# --- Helper Functions (Simplified) ---
# Moved to utils.file_helpers

# --- Routes ---
@app.route('/')
def index():
    initial_call_pdf_path = ""
    initial_proposal_file_path = "" # Single proposal file path
    initial_questions_file_hidden_path = "" # For the hidden input, initially no file uploaded for questions
    default_export_path = str(app.config['DEFAULT_PDF_EXPORT_DIR'] / 'analysis_results.pdf')

    # Load content from the default Questions.txt file
    default_questions_path = Path(app.config['DEFAULT_QUESTIONS_FILE'])
    questions_content = "" # Default to empty string
    if default_questions_path.is_file():
        try:
            questions_content = read_questions_content(str(default_questions_path))
            # Populate the hidden questions file path as well, as if it were 'uploaded' by default
            # This ensures that if the user modifies and saves, it saves to this default path
            # unless they explicitly upload a different questions file.
            # However, current UI flow: upload sets the hidden path. Initial load should just show content.
            # The /save_questions route will save to a temp file if hidden path is empty.
            # So, we don't set initial_questions_file_hidden_path from default_questions_path here
            # to encourage the upload flow or direct edit->save (which goes to temp).
        except Exception as e:
            app.logger.error(f"Error reading default questions file {default_questions_path}: {e}")
            questions_content = "Could not load default questions. Please check server logs." # Or just empty
        
    return render_template('index.html',
                           questions_content=questions_content, 
                           call_pdf_path=initial_call_pdf_path, 
                           proposal_file_path_hidden=initial_proposal_file_path, 
                           questions_file_path=initial_questions_file_hidden_path, # This remains empty initially
                           default_call_files_dir_str=str(app.config['DEFAULT_CALL_FILES_DIR']), 
                           pdf_export_path_default=default_export_path 
                           )

@app.route('/save_questions', methods=['POST'])
def save_questions():
    try:
        data = request.json
        content = data.get('content')
        questions_file_path_str = data.get('questions_file_path') # This will come from hidden input

        if not questions_file_path_str: # If no file was uploaded, user might be editing directly
            # Save to a default temporary location if no path is specified by an upload
            # Or decide if this feature is still needed if questions are always uploaded or directly edited
            temp_questions_dir = MAIN_UPLOADS_DIR / 'questions'
            temp_questions_dir.mkdir(parents=True, exist_ok=True)
            questions_file = temp_questions_dir / "runtime_questions.txt"
            questions_file_path_str = str(questions_file)
        else:
            questions_file = Path(questions_file_path_str)
        
        if content is None: 
             return jsonify(success=False, message="Content for questions file is required."), 400

        questions_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(questions_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify(success=True, message=f"Questions saved to {questions_file_path_str} successfully!", filepath=str(questions_file))
    except Exception as e:
        app.logger.error(f"Error in /save_questions: {e}", exc_info=True)
        return jsonify(success=False, message=str(e)), 500

@app.route('/load_path_data', methods=['POST'])
def load_path_data_route():
    try:
        data = request.json
        path_type = data.get('path_type') 
        path_value = data.get('path_value')

        if not path_type or not path_value:
            return jsonify(success=False, message="Path type and value are required."), 400

        path_obj = Path(path_value)
        resolved_path_value_str = str(path_obj.resolve() if path_obj.exists() else path_obj)
        response_data = {"path_type": path_type, "path_value": resolved_path_value_str}

        # This route is now mainly for loading questions content into textarea after upload
        if path_type == 'questions_file':
            if not path_obj.is_file():
                return jsonify(success=False, message=f"Questions file not found: {path_value}", questions_content='', path_value=path_value), 400
            response_data['questions_content'] = read_questions_content(str(path_obj))
            response_data['message'] = f"Questions content loaded from {resolved_path_value_str}."
        elif path_type == 'call_pdf' or path_type == 'proposal_file': # Simplified validation for single files
            if not path_obj.is_file():
                return jsonify(success=False, message=f"File not found or is not a file: {path_value}", path_value=path_value), 400
            response_data['message'] = f"File path validated: {resolved_path_value_str}."
        else:
            return jsonify(success=False, message=f"Invalid path_type for this simplified UI: {path_type}"), 400

        return jsonify(success=True, **response_data)
    except Exception as e:
        app.logger.error(f"Error in /load_path_data: {e}", exc_info=True)
        return jsonify(success=False, message=str(e)), 500

@app.route('/run_analysis', methods=['POST'])
def run_analysis():
    data = request.json
    call_pdf_path_str = data.get('call_pdf_path')
    proposal_file_path_str = data.get('proposal_file_path') # Changed from proposals_dir_path
    questions_file_path_str = data.get('questions_file_path')
    # selected_proposal_filenames is no longer needed as we process one proposal at a time
    model = "gpt-4.1-mini" # Hardcoded model

    # Get checkbox states from the request
    analyze_proposal_opt = data.get('analyze_proposal_opt', False)
    reviewer_feedback_opt = data.get('reviewer_feedback_opt', False)

    if not call_pdf_path_str or not proposal_file_path_str:
        return jsonify(success=False, message="Call PDF and Proposal PDF paths are required."), 400
        
    call_pdf_path = Path(call_pdf_path_str)
    proposal_file_path = Path(proposal_file_path_str)
    questions_file_path = Path(questions_file_path_str) if questions_file_path_str else None # Questions are optional

    path_errors = []
    if not call_pdf_path.is_file():
        path_errors.append(f"Call PDF not found: {call_pdf_path_str}")
    if not proposal_file_path.is_file():
        path_errors.append(f"Proposal PDF not found: {proposal_file_path_str}")
    if questions_file_path and not questions_file_path.is_file(): # Only error if path is given but file not found
        path_errors.append(f"Questions file not found: {questions_file_path_str}")
    
    if path_errors:
        return jsonify(success=False, message="; ".join(path_errors)), 400

    # For AnalysisService, proposals_dir_path is parent of proposal_file_path
    # and selected_proposal_filenames is just the name of the proposal_file_path
    proposals_dir_path = proposal_file_path.parent
    selected_proposal_filenames = [proposal_file_path.name]

    def generate_stream_from_service():
        try:
            # Note: For streaming, we are calling the service with boolean flags.
            # The service translates these to the appropriate CLI flags for main.py.
            stream_iterator = analysis_service.run_analysis_stream(
                call_pdf_path=call_pdf_path,
                proposals_dir_path=proposals_dir_path, 
                questions_file_path=questions_file_path,
                model=model, 
                selected_proposal_filenames=selected_proposal_filenames,
                logger=app.logger,
                analyze_proposal_opt=analyze_proposal_opt,
                reviewer_feedback_opt=reviewer_feedback_opt
            )
            for event_string in stream_iterator:
                # The event_string is already in SSE format with "data: ...\n\n"
                yield event_string
        except Exception as e:
            app.logger.error(f"Error during analysis stream generation in app.py: {e}", exc_info=True)
            error_event = {"type": "error", "message": f"An unexpected error occurred in app.py before stream could start: {html.escape(str(e))}"}
            yield f"data: {json.dumps(error_event)}\n\n"
            final_message = {"type": "stream_end", "message": "Stream ended due to pre-stream error."}
            yield f"data: {json.dumps(final_message)}\n\n"

    return Response(stream_with_context(generate_stream_from_service()), mimetype='text/event-stream')


@app.route('/export_pdf', methods=['POST'])
def export_pdf():
    try:
        data = request.json
        analysis_data_from_client = data.get('analysis_data') # This is the comprehensive result object with all services
        proposal_filename_original = data.get('proposal_filename', 'report')

        if not analysis_data_from_client or not isinstance(analysis_data_from_client, dict):
            app.logger.error(f"Invalid or missing analysis_data for PDF export. Type: {type(analysis_data_from_client)}")
            return jsonify(success=False, message="No valid analysis data provided for PDF export."), 400

        # Use the comprehensive analysis data directly - it should contain keys like:
        # proposal_analysis, spell_check, reviewer_feedback, etc.
        all_findings = analysis_data_from_client

        base_name = Path(proposal_filename_original).stem
        export_dir = Path(app.config['DEFAULT_PDF_EXPORT_DIR'])
        export_dir.mkdir(parents=True, exist_ok=True) # Ensure export dir exists
        
        # Create a somewhat unique filename on the server
        timestamp = secrets.token_hex(4) # Short timestamp/random part
        server_pdf_filename = f"{base_name}_analysis_{timestamp}.pdf"
        server_pdf_full_path = export_dir / server_pdf_filename

        pdf_exporter = PDFExportService(export_path_str=str(server_pdf_full_path))
        
        # Determine which services were run based on the presence of data
        services_run = {
            "Core Analysis": bool(all_findings.get("proposal_analysis")),
            "Spell Check": bool(all_findings.get("spell_check")),
            "Reviewer Feedback": bool(all_findings.get("reviewer_feedback"))
        }
        
        # Basic model information (we don't have detailed model info from the client)
        models_used = {
            "Analysis Model": "gpt-4.1-mini" if services_run["Core Analysis"] else "N/A",
            "Spell Check Model": "gpt-4.1-nano" if services_run["Spell Check"] else "N/A",
            "Reviewer Feedback Model": "gpt-4.1-mini" if services_run["Reviewer Feedback"] else "N/A"
        }

        generated_pdf_path = pdf_exporter.generate_full_report_pdf(
            proposal_filename=proposal_filename_original,
            all_findings=all_findings,
            call_document_name="Uploaded Call Document", # We don't have the original call filename from client
            questions_source_name="Analysis Questions", # We don't have the original questions filename from client
            services_run=services_run,
            models_used=models_used
        )
        
        if generated_pdf_path:
            app.logger.info(f"Comprehensive PDF exported successfully to {generated_pdf_path}")
            return jsonify(success=True, message=f"PDF exported successfully to {server_pdf_filename}", filename_server=server_pdf_filename)
        else:
            app.logger.error(f"Failed to generate PDF for {proposal_filename_original}")
            return jsonify(success=False, message="Failed to generate PDF report."), 500

    except Exception as e:
        app.logger.error(f"Error exporting PDF: {e}", exc_info=True)
        return jsonify(success=False, message=f"Error exporting PDF: {str(e)}"), 500

@app.route('/download_export/<filename>', methods=['GET'])
def download_export(filename):
    try:
        directory = Path(app.config['DEFAULT_PDF_EXPORT_DIR'])
        app.logger.info(f"Attempting to send file: {filename} from directory: {directory}")
        return send_from_directory(directory, filename, as_attachment=True)
    except FileNotFoundError:
        app.logger.error(f"File not found for download: {filename} in {directory}")
        return jsonify(success=False, message="File not found."), 404
    except Exception as e:
        app.logger.error(f"Error downloading file {filename}: {e}", exc_info=True)
        return jsonify(success=False, message=f"Error downloading file: {str(e)}"), 500


@app.route('/upload_main_document', methods=['POST'])
def upload_main_document():
    if 'file' not in request.files:
        return jsonify(success=False, message="No file part in the request."), 400
    
    file = request.files['file']
    doctype = request.form.get('doctype')

    if file.filename == '':
        return jsonify(success=False, message="No selected file."), 400
    
    if not doctype or doctype not in ['call', 'proposal', 'questions']:
        return jsonify(success=False, message="Doctype (call, proposal, questions) is required and must be valid."), 400
        
    if file:
        filename = file.filename 
        save_dir = MAIN_UPLOADS_DIR / doctype
        save_path = save_dir / filename
        
        try:
            file.save(save_path)
            app.logger.info(f"Main UI: File '{filename}' uploaded to {save_path} as type '{doctype}'")
            
            response_data = {
                "success": True,
                "message": f"File '{filename}' uploaded successfully as {doctype}.",
                "filepath": str(save_path),
                "filename": filename,
                "doctype": doctype
            }
            # No longer need to return proposals_dir_path as we handle single proposal file path

            return jsonify(response_data)
        except Exception as e:
            app.logger.error(f"Error saving uploaded file from main UI: {filename} - {e}", exc_info=True)
            return jsonify(success=False, message=f"Could not save file: {str(e)}"), 500
            
    return jsonify(success=False, message="File upload failed for an unknown reason."), 500

if __name__ == '__main__':
    # Make sure to create a 'templates' and 'static' directory in the same level as app.py
    # For development, debug=True is useful.
    # For production, use environment variables
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    app.run(debug=debug_mode, host=host, port=port) 