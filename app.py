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
    spell_check_opt = data.get('spell_check_opt', False)
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
            stream_iterator = analysis_service.run_analysis_stream(
                call_pdf_path=call_pdf_path,
                proposals_dir_path=proposals_dir_path, # Still needed by service
                questions_file_path=questions_file_path,
                model=model,
                selected_proposal_filenames=selected_proposal_filenames, # List with one item
                logger=app.logger,
                # Pass the new options
                analyze_proposal_opt=analyze_proposal_opt,
                spell_check_opt=spell_check_opt,
                reviewer_feedback_opt=reviewer_feedback_opt
            )
            for event_string in stream_iterator:
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

# --- Chat UI Routes ---

@app.route('/chat')
def chat_index():
    """Serves the main chat UI page and initializes chat session."""
    # Initialize session variables if they don't exist
    if 'conversation_history' not in session:
        session['conversation_history'] = []
    if CHAT_UPLOADED_FILES_SESSION_KEY not in session:
        session[CHAT_UPLOADED_FILES_SESSION_KEY] = {'proposal': None, 'call': None, 'questions': None}
    if CHAT_UNCLASSIFIED_FILES_SESSION_KEY not in session:
        session[CHAT_UNCLASSIFIED_FILES_SESSION_KEY] = {} # Stores {filename: path}
    if 'analysis_results' not in session:
        session['analysis_results'] = None

    # Initial LLM greeting if conversation is new
    if not session['conversation_history']:
        system_prompt = "You are a helpful AI assistant for analyzing proposals. Your goal is to guide the user through uploading a proposal PDF, a call for proposal PDF, and optionally a questions.txt file. If a file is uploaded and its type (proposal, call, questions) cannot be determined from the name, you MUST ask the user to clarify its type. When the user provides a classification (e.g., 'file X is the call document'), acknowledge it and then immediately include an action tag like [ACTION:CLASSIFY_FILE filename='X' type='call'] in your response. Replace 'X' with the actual filename and 'call' with the identified type (proposal, call, or questions). Once all necessary files (proposal and call) are uploaded and classified, explicitly ask the user if they want to proceed with the analysis. If they confirm, respond with 'Okay, I will start the analysis now. [ACTION:RUN_ANALYSIS]' and nothing else. After analysis, you will help them understand the results and export them to PDF. Keep your responses concise and clear. Start by greeting the user and asking for the proposal and call for proposal documents."
        initial_messages = [{"role": "system", "content": system_prompt}]
        
        try:
            llm_response = ask_llm(messages=initial_messages, model='gpt-4.1-nano')
            session['conversation_history'].append({"role": "system", "content": system_prompt}) # Store system prompt for context
            session['conversation_history'].append({"role": "assistant", "content": llm_response})
        except Exception as e:
            app.logger.error(f"Error getting initial LLM greeting: {e}", exc_info=True)
            llm_response = "Hello! I'm having a little trouble connecting to my brain right now. Please try again in a moment."
            # We don't add this error to history, the JS will show the initial greeting if this fails.
            # Or, we can add a non-LLM system message to history:
            session['conversation_history'].append({"role": "assistant", "content": llm_response})

    return render_template('chat_ui/index.html', initial_conversation=session['conversation_history'])

@app.route('/chat_message', methods=['POST'])
def chat_message():
    """Handles incoming chat messages from the user and gets LLM response."""
    data = request.json
    user_message_content = data.get('message')

    if not user_message_content:
        return jsonify(success=False, message="No message content."), 400

    # Ensure session is initialized (it should be by /chat, but as a fallback)
    if 'conversation_history' not in session:
        session['conversation_history'] = []
        # Potentially add a default system prompt here if starting fresh

    session['conversation_history'].append({"role": "user", "content": user_message_content})

    # Prepare messages for LLM (system prompt + history)
    # The system prompt can be dynamic based on state, or a general one.
    # For now, the initial system prompt is already in history.
    current_classified_files = session.get(CHAT_UPLOADED_FILES_SESSION_KEY, {})
    current_unclassified_files = session.get(CHAT_UNCLASSIFIED_FILES_SESSION_KEY, {})

    files_status_prompt = "Current classified files: Proposal: {proposal_status}, Call: {call_status}, Questions: {questions_status}. ".format(
        proposal_status="Uploaded" if current_classified_files.get('proposal') else "Missing",
        call_status="Uploaded" if current_classified_files.get('call') else "Missing",
        questions_status="Uploaded" if current_classified_files.get('questions') else "Missing/Default"
    )
    if current_unclassified_files:
        files_status_prompt += f"Unclassified files: {list(current_unclassified_files.keys())}. You need to ask the user to classify these. Example: 'What type of document is {list(current_unclassified_files.keys())[0]}? Is it a Call, Proposal, or Questions file?' "

    # Construct the messages for the LLM call
    # We prepend a system message that gives current context, then the history
    # The very first message in history should be the main system prompt for the LLM's persona.
    messages_for_llm = []
    if session['conversation_history'] and session['conversation_history'][0]['role'] == 'system':
        messages_for_llm.append(session['conversation_history'][0]) # Main system prompt
    else:
        # Fallback if main system prompt is missing (should not happen)
        messages_for_llm.append({"role": "system", "content": "You are a helpful AI assistant for analyzing proposals. Your goal is to guide the user through uploading a proposal PDF, a call for proposal PDF, and optionally a questions.txt file. If a file is uploaded and its type (proposal, call, questions) cannot be determined from the name, you MUST ask the user to clarify its type. When the user provides a classification (e.g., 'file X is the call document'), acknowledge it and then immediately include an action tag like [ACTION:CLASSIFY_FILE filename='X' type='call'] in your response. Replace 'X' with the actual filename and 'call' with the identified type (proposal, call, or questions). Once all necessary files (proposal and call) are uploaded and classified, explicitly ask the user if they want to proceed with the analysis. If they confirm, respond with 'Okay, I will start the analysis now. [ACTION:RUN_ANALYSIS]' and nothing else. After analysis, you will help them understand the results and export them to PDF."})
    
    # Add a contextual system message about current file status and next steps
    contextual_system_message_content = files_status_prompt + " Guide the user. If there are unclassified files, ask for their type. If the user provides a classification, acknowledge it and use the [ACTION:CLASSIFY_FILE filename='actual_filename.pdf' type='detected_type'] tag. If all files (proposal and call) are classified and present and you haven't asked to run analysis yet, ask if they want to run it. If they confirm, use the [ACTION:RUN_ANALYSIS] tag. If analysis was run, discuss results or ask if they want a PDF."
    messages_for_llm.append({"role": "system", "content": contextual_system_message_content})

    # Add actual conversation history (excluding the main system prompt which is already added)
    history_to_add = session['conversation_history'][1:] if session['conversation_history'] and session['conversation_history'][0]['role'] == 'system' else session['conversation_history']
    messages_for_llm.extend(history_to_add)
    # The user_message_content is already the last item in session['conversation_history'] at this point
    # So, messages_for_llm now contains: [main_system_prompt, contextual_system_prompt, actual_history_including_last_user_message]

    try:
        llm_response_content = ask_llm(messages=messages_for_llm, model='gpt-4.1-nano')
        session['conversation_history'].append({"role": "assistant", "content": llm_response_content})
        session.modified = True 

        # --- Handle [ACTION:CLASSIFY_FILE] --- 
        # Example: [ACTION:CLASSIFY_FILE filename='F.14+HPOSS.pdf' type='call']
        classify_action_match = re.search(r"\[ACTION:CLASSIFY_FILE filename='(.*?)' type='(.*?)'\]", llm_response_content)
        if classify_action_match:
            classified_filename = classify_action_match.group(1)
            classified_type = classify_action_match.group(2)
            
            app.logger.info(f"LLM indicated classification: Filename: {classified_filename}, Type: {classified_type}")

            unclassified_files = session.get(CHAT_UNCLASSIFIED_FILES_SESSION_KEY, {})
            classified_files_dict = session.get(CHAT_UPLOADED_FILES_SESSION_KEY, {})

            if classified_filename in unclassified_files and classified_type in ['proposal', 'call', 'questions']:
                file_path_to_classify = unclassified_files.pop(classified_filename) # Remove from unclassified
                classified_files_dict[classified_type] = file_path_to_classify # Add to classified
                
                session[CHAT_UNCLASSIFIED_FILES_SESSION_KEY] = unclassified_files
                session[CHAT_UPLOADED_FILES_SESSION_KEY] = classified_files_dict
                session.modified = True
                app.logger.info(f"Successfully classified {classified_filename} as {classified_type} and updated session.")
                
                # The LLM's response already contains the user-facing acknowledgement.
                # We just clean the tag for the user to see.
                llm_response_content_cleaned = llm_response_content.replace(classify_action_match.group(0), "").strip()
                # Update conversation history with the cleaned response
                session['conversation_history'][-1]['content'] = llm_response_content_cleaned
                session.modified = True
                # Return the cleaned response. The next turn will have updated file status for the LLM.
                return jsonify(success=True, response=llm_response_content_cleaned)
            else:
                app.logger.warning(f"Could not classify {classified_filename} as {classified_type}. File not in unclassified list or invalid type.")
                # Let LLM response pass through, it might be handling the error conversationally.

        # --- Handle [ACTION:RUN_ANALYSIS] --- 
        if "[ACTION:RUN_ANALYSIS]" in llm_response_content:
            # Verify necessary files
            classified_files_check = session.get(CHAT_UPLOADED_FILES_SESSION_KEY, {})
            call_pdf_check = classified_files_check.get('call')
            proposal_pdf_check = classified_files_check.get('proposal')
            session.modified = True # Ensure session is saved before redirecting to stream
            
            if not call_pdf_check or not proposal_pdf_check:
                no_files_msg = "It seems we are missing either the call or proposal PDF. Please upload both before we can start the analysis."
                session['conversation_history'].append({"role": "assistant", "content": no_files_msg}) # Add a follow-up LLM message
                session.modified = True
                # LLM said it would run, but we interrupt with this correction, clean the original LLM response tag.
                cleaned_llm_response = llm_response_content.replace("[ACTION:RUN_ANALYSIS]", "").strip()
                session['conversation_history'][-1]['content'] = cleaned_llm_response # Update the history for the tag-cleaned original message
                return jsonify(success=True, response=no_files_msg) 

            # Clear previous analysis results before starting a new one
            session['analysis_results'] = None
            session.modified = True

            # Respond to client to initiate stream connection
            # The LLM's message "Okay, I will start the analysis now..." will be shown, 
            # and then the client will connect to /stream_analysis_results
            cleaned_llm_response_for_stream_action = llm_response_content.replace("[ACTION:RUN_ANALYSIS]", "").strip()
            session['conversation_history'][-1]['content'] = cleaned_llm_response_for_stream_action # Update history with cleaned message
            return jsonify(success=True, response=cleaned_llm_response_for_stream_action, action="start_analysis_stream")

        return jsonify(success=True, response=llm_response_content)
    except Exception as e:
        app.logger.error(f"Error in /chat_message calling LLM: {e}", exc_info=True)
        error_response = "I encountered an issue trying to process that. Please try rephrasing or wait a moment."
        # Add LLM's error placeholder to history so user sees it
        session['conversation_history'].append({"role": "assistant", "content": error_response})
        session.modified = True
        return jsonify(success=False, message="LLM API call failed.", response=error_response), 500

@app.route('/chat_upload', methods=['POST'])
def chat_upload():
    """Handles file uploads from the chat UI, updates session, and gets LLM response."""
    if 'file' not in request.files:
        return jsonify(success=False, message="No file part in the request."), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify(success=False, message="No selected file."), 400
        
    if file:
        filename = file.filename # In a real app, sanitize this!
        save_path = CHAT_UPLOADS_DIR / filename
        try:
            file.save(save_path)
            app.logger.info(f"File '{filename}' uploaded to {save_path}")

            # Initialize session keys if they don't exist (important for first upload)
            if CHAT_UPLOADED_FILES_SESSION_KEY not in session:
                session[CHAT_UPLOADED_FILES_SESSION_KEY] = {'proposal': None, 'call': None, 'questions': None}
            if CHAT_UNCLASSIFIED_FILES_SESSION_KEY not in session:
                session[CHAT_UNCLASSIFIED_FILES_SESSION_KEY] = {}

            file_type_guess = "unknown"
            fn_lower = filename.lower()
            if "proposal" in fn_lower:
                file_type_guess = "proposal"
            elif "call" in fn_lower or "solicitation" in fn_lower or "rfi" in fn_lower or "rfp" in fn_lower: # Broader terms for call
                file_type_guess = "call"
            elif "question" in fn_lower:
                file_type_guess = "questions"
            
            upload_acknowledged_message_for_llm = f"File '{html.escape(filename)}' was uploaded by the user. "

            if file_type_guess != "unknown":
                session[CHAT_UPLOADED_FILES_SESSION_KEY][file_type_guess] = str(save_path)
                # If this filename was previously unclassified, remove it from there
                if filename in session[CHAT_UNCLASSIFIED_FILES_SESSION_KEY]:
                    del session[CHAT_UNCLASSIFIED_FILES_SESSION_KEY][filename]
                upload_acknowledged_message_for_llm += f"It has been automatically classified as a '{file_type_guess}' document."
            else:
                session[CHAT_UNCLASSIFIED_FILES_SESSION_KEY][filename] = str(save_path)
                upload_acknowledged_message_for_llm += "Its type could not be automatically determined. You need to ask the user to classify it (e.g., 'Is this a Call, Proposal, or Questions file?')."
            
            session.modified = True

            # This message is for the LLM's context, not directly for the user from this endpoint.
            # The LLM will formulate the user-facing message based on this and the overall context.
            session['conversation_history'].append({"role": "system", "content": upload_acknowledged_message_for_llm})

            # Construct messages for LLM to respond to the upload
            messages_for_llm = []
            if session['conversation_history'] and session['conversation_history'][0]['role'] == 'system':
                 messages_for_llm.append(session['conversation_history'][0]) # Main system prompt
            else: messages_for_llm.append({"role": "system", "content": "You are a helpful AI assistant for analyzing proposals."})
            
            current_classified_files = session.get(CHAT_UPLOADED_FILES_SESSION_KEY, {})
            current_unclassified_files = session.get(CHAT_UNCLASSIFIED_FILES_SESSION_KEY, {})

            files_status_prompt_after_upload = "Current classified files: Proposal: {proposal_status}, Call: {call_status}, Questions: {questions_status}. ".format(
                proposal_status="Uploaded" if current_classified_files.get('proposal') else "Missing",
                call_status="Uploaded" if current_classified_files.get('call') else "Missing",
                questions_status="Uploaded" if current_classified_files.get('questions') else "Missing/Default"
            )
            if current_unclassified_files:
                 files_status_prompt_after_upload += f"Unclassified files: {list(current_unclassified_files.keys())}. Remember to ask the user to classify these if you haven't already. "

            system_context_for_upload = files_status_prompt_after_upload + "Acknowledge the upload of '" + html.escape(filename) + "'. Then guide the user on next steps. If there are unclassified files, ask about them. If all files (proposal and call) are classified and present, ask if they want to run analysis."
            
            # Add relevant history for the LLM to form its response to the upload
            # The most recent history items are most relevant here.
            messages_for_llm.append({"role": "system", "content": system_context_for_upload})
            # We take the main system prompt (added above) and the last few turns of conversation history
            # The `upload_acknowledged_message_for_llm` is the latest in history.
            history_to_add_for_upload = session['conversation_history'][1:] 
            messages_for_llm.extend(history_to_add_for_upload)

            llm_response_content = ask_llm(messages=messages_for_llm, model='gpt-4.1-nano')
            session['conversation_history'].append({"role": "assistant", "content": llm_response_content})
            session.modified = True

            return jsonify(success=True, message=f"File '{filename}' stored.", llm_response=llm_response_content, filename=filename)
        except Exception as e:
            app.logger.error(f"Error processing uploaded file {filename} or calling LLM: {e}", exc_info=True)
            error_response = f"Could not save file '{html.escape(filename)}' or process its upload. Please try again."
            session['conversation_history'].append({"role": "assistant", "content": error_response})
            session.modified = True
            return jsonify(success=False, message=f"Could not save file or process upload: {str(e)}", llm_response=error_response), 500
            
    return jsonify(success=False, message="File upload failed for an unknown reason."), 500

@app.route('/stream_analysis_results')
def stream_analysis_results():
    """Streams analysis results using SSE."""
    # session.sid is not available for SecureCookieSession, remove or find alternative if needed for logging.
    app.logger.info(f"Entering /stream_analysis_results. Current session keys: {list(session.keys())}")
    app.logger.info(f"Session contents for {CHAT_UPLOADED_FILES_SESSION_KEY}: {session.get(CHAT_UPLOADED_FILES_SESSION_KEY)}")
    app.logger.info(f"Session contents for {CHAT_UNCLASSIFIED_FILES_SESSION_KEY}: {session.get(CHAT_UNCLASSIFIED_FILES_SESSION_KEY)}")

    try:
        classified_files = session.get(CHAT_UPLOADED_FILES_SESSION_KEY, {})
        call_pdf_path_str = classified_files.get('call')
        proposal_pdf_path_str = classified_files.get('proposal')

        if not call_pdf_path_str or not proposal_pdf_path_str:
            def error_stream_missing_files():
                app.logger.error(f"Missing call/proposal PDF path in session for stream. Call: {call_pdf_path_str}, Proposal: {proposal_pdf_path_str}")
                yield f"data: {json.dumps({'type': 'error', 'message': 'Missing call or proposal file in session for analysis. Ensure files are uploaded and correctly classified.'})}\n\n"
                yield f"data: {json.dumps({'type': 'stream_end', 'message': 'Stream ended due to missing files.'})}\n\n"
            return Response(stream_with_context(error_stream_missing_files()), mimetype='text/event-stream')

        call_pdf_path = Path(call_pdf_path_str)
        proposal_pdf_file_path = Path(proposal_pdf_path_str)
        proposals_dir_path = proposal_pdf_file_path.parent
        selected_proposal_filenames = [proposal_pdf_file_path.name]
        
        questions_file_path_str = classified_files.get('questions')
        questions_file_path = Path(questions_file_path_str) if questions_file_path_str else None
        
        model_for_analysis = 'gpt-4.1-mini'

    except Exception as e_setup:
        app.logger.error(f"Error during setup in /stream_analysis_results: {e_setup}", exc_info=True)
        def error_stream_setup_failure():
            yield f"data: {json.dumps({'type': 'error', 'message': f'Server error during analysis setup: {html.escape(str(e_setup))}'})}\n\n"
            yield f"data: {json.dumps({'type': 'stream_end', 'message': 'Stream ended due to server setup error.'})}\n\n"
        return Response(stream_with_context(error_stream_setup_failure()), mimetype='text/event-stream')

    # This inner function is what gets streamed
    def generate_stream_wrapper():
        try:
            app.logger.info(f"generate_stream_wrapper: Starting analysis with call_pdf={call_pdf_path}, proposals_dir={proposals_dir_path}, questions={questions_file_path}, model={model_for_analysis}, selected={selected_proposal_filenames}")
            stream_iterator = analysis_service.run_analysis_stream(
                call_pdf_path=call_pdf_path,
                proposals_dir_path=proposals_dir_path, 
                questions_file_path=questions_file_path,
                model=model_for_analysis, 
                selected_proposal_filenames=selected_proposal_filenames,
                logger=app.logger
            )
            for event_string in stream_iterator:
                if event_string.startswith("data:"):
                    try:
                        data_json_str = event_string[len("data:"):].strip()
                        event_data = json.loads(data_json_str)
                        if event_data.get("type") == "result" and "payload" in event_data:
                            session['analysis_results'] = event_data["payload"]
                            session.modified = True
                            app.logger.info("Analysis results stored in session.")
                    except json.JSONDecodeError as je:
                        app.logger.error(f"JSONDecodeError in stream_analysis_results while checking for result: {je}")
                    except Exception as ex:
                        app.logger.error(f"Error in stream_analysis_results while checking for result: {ex}")    
                yield event_string
        except Exception as e_service_call:
            app.logger.error(f"Error during analysis_service.run_analysis_stream call: {e_service_call}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'Error calling analysis service: {html.escape(str(e_service_call))}'})}\n\n"
            yield f"data: {json.dumps({'type': 'stream_end', 'message': 'Stream ended due to analysis service error.'})}\n\n"

    return Response(stream_with_context(generate_stream_wrapper()), mimetype='text/event-stream')

if __name__ == '__main__':
    # Make sure to create a 'templates' and 'static' directory in the same level as app.py
    # For development, debug=True is useful.
    # For production, use environment variables
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    app.run(debug=debug_mode, host=host, port=port) 