import os
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, stream_with_context
from pathlib import Path
import subprocess
import json
import html
import secrets
import re
import tempfile

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

# Define project root for easier path construction
PROJECT_ROOT = Path(__file__).parent

app = Flask(__name__,
            static_folder=str(PROJECT_ROOT / 'static'),
            template_folder=str(PROJECT_ROOT / 'templates'))

# Defaults for initial page load
app.config['DEFAULT_CALL_FILES_DIR'] = PROJECT_ROOT / 'data' / 'call'
app.config['DEFAULT_PROPOSALS_DIR'] = str(PROJECT_ROOT / 'data' / 'proposal')
app.config['DEFAULT_QUESTIONS_FILE'] = str(PROJECT_ROOT / 'data' / 'Questions.txt')
app.config['DEFAULT_PDF_EXPORT_DIR'] = PROJECT_ROOT / 'exports' 

# Ensure base data directory and subdirectories exist
(PROJECT_ROOT / 'data' / 'call').mkdir(parents=True, exist_ok=True)
(PROJECT_ROOT / 'data' / 'proposal').mkdir(parents=True, exist_ok=True)
app.config['DEFAULT_PDF_EXPORT_DIR'].mkdir(parents=True, exist_ok=True) 

# Directory for uploads from the main UI
MAIN_UPLOADS_DIR = PROJECT_ROOT / 'data' / 'main_uploads'
(MAIN_UPLOADS_DIR / 'call').mkdir(parents=True, exist_ok=True)
(MAIN_UPLOADS_DIR / 'proposal').mkdir(parents=True, exist_ok=True)
(MAIN_UPLOADS_DIR / 'questions').mkdir(parents=True, exist_ok=True)

# Initialize services
analysis_service = AnalysisService(project_root=PROJECT_ROOT)

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

@app.route('/test', methods=['POST'])
def test_endpoint():
    return jsonify(success=True, message="Test endpoint working!")

@app.route('/run_analysis', methods=['POST'])
def run_analysis():
    if 'proposal_pdf' not in request.files or 'call_pdf' not in request.files:
        return jsonify(success=False, message="Call PDF and Proposal PDF files are required."), 400

    proposal_file = request.files['proposal_pdf']
    call_file = request.files['call_pdf']

    if proposal_file.filename == '' or call_file.filename == '':
        return jsonify(success=False, message="File names cannot be empty."), 400

    # Get checkbox states from the form
    analyze_proposal_opt = request.form.get('analyze_proposal_opt', 'false').lower() == 'true'
    spell_check_opt = request.form.get('spell_check_opt', 'false').lower() == 'true'
    reviewer_feedback_opt = request.form.get('reviewer_feedback_opt', 'false').lower() == 'true'
    questions_content = request.form.get('questions_content', '')

    try:
        # Create a temporary directory to store uploaded files for this request
        temp_dir = tempfile.TemporaryDirectory()
        temp_dir_path = Path(temp_dir.name)

        # Save files to the temporary directory
        proposal_file_path = temp_dir_path / proposal_file.filename
        proposal_file.save(proposal_file_path)

        call_pdf_path = temp_dir_path / call_file.filename
        call_file.save(call_pdf_path)

        questions_file_path = None
        if questions_content:
            questions_file_path = temp_dir_path / "questions.txt"
            questions_file_path.write_text(questions_content, encoding='utf-8')

        # For AnalysisService, proposals_dir_path is parent of proposal_file_path
        proposals_dir_path = proposal_file_path.parent
        selected_proposal_filenames = [proposal_file_path.name]
        model = "gpt-4.1-mini" # Hardcoded model

        def generate_stream_from_service():
            try:
                stream_iterator = analysis_service.run_analysis_stream(
                    call_pdf_path=call_pdf_path,
                    proposals_dir_path=proposals_dir_path,
                    questions_file_path=questions_file_path,
                    model=model,
                    selected_proposal_filenames=selected_proposal_filenames,
                    logger=app.logger,
                    analyze_proposal_opt=analyze_proposal_opt,
                    spell_check_opt=spell_check_opt,
                    reviewer_feedback_opt=reviewer_feedback_opt
                )
                for event_string in stream_iterator:
                    yield event_string
            except Exception as e:
                app.logger.error(f"Error during analysis stream: {e}", exc_info=True)
                error_event = {"type": "error", "message": f"Stream generation failed: {html.escape(str(e))}"}
                yield f"data: {json.dumps(error_event)}\n\n"
            finally:
                # IMPORTANT: Clean up the temporary directory
                temp_dir.cleanup()
                final_message = {"type": "stream_end", "message": "Stream ended."}
                yield f"data: {json.dumps(final_message)}\n\n"
        
        return Response(stream_with_context(generate_stream_from_service()), mimetype='text/event-stream')

    except Exception as e:
        app.logger.error(f"Error setting up analysis: {e}", exc_info=True)
        return jsonify(success=False, message=f"Server error setting up analysis: {e}"), 500

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

            return jsonify(response_data)
        except Exception as e:
            app.logger.error(f"Error saving uploaded file from main UI: {filename} - {e}", exc_info=True)
            return jsonify(success=False, message=f"Could not save file: {str(e)}"), 500
            
    return jsonify(success=False, message="File upload failed for an unknown reason."), 500

if __name__ == "__main__":
    # This block is for local development.
    # When deployed on Render, a Gunicorn command from render.yaml is used instead.
    port = int(os.environ.get("PORT", 5000))
    # Enable debug mode locally unless FLASK_ENV is set to 'production'
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug) 