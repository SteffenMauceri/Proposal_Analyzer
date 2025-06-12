from pathlib import Path
import html
from typing import List, Dict, Any, Optional
import re

from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch

class PDFExportService:
    def __init__(self, export_path_str: str):
        self.export_path = Path(export_path_str)
        # Ensure the export directory exists
        self.export_path.parent.mkdir(parents=True, exist_ok=True)
        self.styles = getSampleStyleSheet()

    def _create_styled_paragraph(self, text: str, style_key: str, alignment: Optional[int] = None, text_color: Optional[colors.Color] = None, font_name: Optional[str] = None, font_size: Optional[int] = None, leading: Optional[int] = None):
        style = self.styles[style_key].clone(f"custom_{style_key}") # Clone to avoid modifying global sample styles
        if alignment is not None:
            style.alignment = alignment
        if font_name:
            style.fontName = font_name
        if font_size:
            style.fontSize = font_size
        if leading:
            style.leading = leading # Line spacing
        
        para = Paragraph(text, style)
        if text_color:
            para.textColor = text_color
        return para

    def generate_analysis_pdf(self, analysis_data: List[Dict[str, Any]]) -> str:
        """Generates a PDF report from the analysis data."""
        doc = SimpleDocTemplate(
            str(self.export_path), 
            pagesize=landscape(letter), 
            topMargin=0.5*inch, 
            bottomMargin=0.5*inch, 
            leftMargin=0.5*inch, 
            rightMargin=0.5*inch
        )
        story = []

        # Title
        story.append(self._create_styled_paragraph("Proposal Analysis Results", 'h1', alignment=1))
        story.append(Spacer(1, 0.25*inch))

        body_style = self.styles['Normal']
        body_style.fontSize = 8
        header_style_for_table = self.styles['Normal'].clone('table_header') # Clone to avoid modifying original
        header_style_for_table.fontSize = 9
        header_style_for_table.fontName = 'Helvetica-Bold'

        for proposal_result in analysis_data:
            story.append(self._create_styled_paragraph(f"Results for: {proposal_result.get('proposal_name', 'N/A')}", 'h2'))
            story.append(Spacer(1, 0.1*inch))

            if proposal_result.get('status') == 'error':
                error_msg = f"Error: {proposal_result.get('error_message', 'Unknown error')}"
                if proposal_result.get('details'):
                    error_msg += f" Details: {proposal_result.get('details')}"
                story.append(Paragraph(html.escape(error_msg), body_style))
                story.append(Spacer(1, 0.2*inch))
                continue
            
            table_data = []
            headers = [Paragraph(h, header_style_for_table) for h in ["Question", "Answer", "Reasoning"]]
            table_data.append(headers)

            analysis_items = proposal_result.get('analysis', [])
            if not analysis_items:
                story.append(Paragraph("No analysis items found for this proposal.", body_style))
                story.append(Spacer(1, 0.2*inch))
                continue

            for item in analysis_items:
                question = Paragraph(html.escape(item.get('question', 'N/A')), body_style)
                
                answer_obj = item.get('answer') # Renamed from answer_str to avoid confusion with actual string
                answer_text = "Unsure"
                answer_color = colors.orange
                if answer_obj is True:
                    answer_text = "YES"
                    answer_color = colors.green
                elif answer_obj is False:
                    answer_text = "NO"
                    answer_color = colors.red
                
                answer_paragraph = Paragraph(answer_text, body_style)
                answer_paragraph.textColor = answer_color # Direct color setting
                
                reasoning = Paragraph(html.escape(item.get('reasoning', 'N/A')), body_style)
                table_data.append([question, answer_paragraph, reasoning])
            
            if len(table_data) > 1: 
                col_widths = [2.5*inch, 0.7*inch, 7.3*inch]
                table = Table(table_data, colWidths=col_widths)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.grey),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0,0), (-1,0), 10),
                    # ('BACKGROUND', (0,1), (-1,-1), colors.lightgrey), # Removed alternating background for simplicity for now
                    ('GRID', (0,0), (-1,-1), 1, colors.black)
                ]))
                story.append(table)
            else:
                 story.append(Paragraph("No analysis data to tabulate for this proposal.", body_style))
            story.append(Spacer(1, 0.3*inch))

        doc.build(story)
        return str(self.export_path) 

    def generate_full_report_pdf(
        self, 
        proposal_filename: str,
        all_findings: Dict[str, List[Dict[str, Any]]],
        call_document_name: Optional[str] = None,
        questions_source_name: Optional[str] = None,
        services_run: Optional[Dict[str, bool]] = None,
        models_used: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        Generates a comprehensive PDF report from all collected findings.
        Includes sections for each service run (core analysis, reviewer feedback).
        """
        doc = SimpleDocTemplate(
            str(self.export_path), 
            pagesize=letter, # Changed to portrait for better readability of mixed content
            topMargin=0.75*inch, 
            bottomMargin=0.75*inch, 
            leftMargin=0.75*inch, 
            rightMargin=0.75*inch
        )
        story = []

        # --- PDF Styles Setup ---
        h1_style = self.styles['h1']
        h1_style.alignment = 1 # Center
        h2_style = self.styles['h2']
        h3_style = self.styles['h3']
        normal_style = self.styles['Normal']
        normal_style.fontSize = 10
        normal_style.leading = 12 # Standard line spacing
        
        code_style = self.styles['Code'] # Using ReportLab's built-in Code style
        code_style.fontSize = 9
        code_style.leading = 11
        code_style.backColor = colors.HexColor(0xf0f0f0) # Light grey background for code/snippets
        code_style.textColor = colors.HexColor(0x333333)
        code_style.leftIndent = 10
        code_style.rightIndent = 10
        code_style.firstLineIndent = 0
        code_style.borderPadding = 5
        
        # Custom style for explanations/suggestions
        suggestion_style = self.styles['Normal'].clone('suggestion_style')
        suggestion_style.textColor = colors.darkblue
        suggestion_style.leftIndent = 15 # Indent suggestions
        suggestion_style.spaceBefore = 3
        suggestion_style.spaceAfter = 3

        error_style = self.styles['Normal'].clone('error_style')
        error_style.textColor = colors.red

        placeholder_style = self.styles['Italic'].clone('placeholder_style')
        placeholder_style.textColor = colors.HexColor(0x666666) # Dark grey
        placeholder_style.spaceBefore = 6
        placeholder_style.spaceAfter = 6
        placeholder_style.leftIndent = 10
        placeholder_style.borderPadding = 5
        placeholder_style.borderColor = colors.lightgrey
        placeholder_style.borderWidth = 1


        # --- Report Header ---
        story.append(Paragraph(f"Analysis Report for: {html.escape(proposal_filename)}", h1_style))
        story.append(Spacer(1, 0.25*inch))

        if call_document_name:
            story.append(Paragraph(f"<b>Call Document:</b> {html.escape(call_document_name)}", normal_style))
        if questions_source_name:
            story.append(Paragraph(f"<b>Questions Source:</b> {html.escape(questions_source_name)}", normal_style))
        story.append(Spacer(1, 0.1*inch))
        
        if models_used:
            story.append(Paragraph("<b>Models Utilized:</b>", normal_style))
            for service_name, model_name in models_used.items():
                if model_name and model_name != "N/A":
                     story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;<em>{html.escape(service_name)}:</em> {html.escape(model_name)}", normal_style))
            story.append(Spacer(1, 0.2*inch))

        # --- Sections for each service ---
        for service_key, findings_list in all_findings.items():
            if not findings_list: # Skip if no findings or service was not run effectively
                if services_run and services_run.get(service_key.replace("_", " ").title(), False) and service_key not in ["summary"]: # Check if service was intended to run
                     service_name_display = service_key.replace("_", " ").title()
                     story.append(Paragraph(f"{service_name_display}", h2_style))
                     story.append(Paragraph("<em>No findings reported or service was not applicable for this item.</em>", self.styles['Italic']))
                     story.append(Spacer(1, 0.15*inch))
                continue

            service_name_display = service_key.replace("_", " ").title()
            story.append(Paragraph(f"{service_name_display}", h2_style))
            story.append(Spacer(1, 0.1*inch))

            if service_key == "proposal_analysis":
                # Create a table matching the web UI format
                table_data = [['Question', 'Answer', 'Reasoning']]  # Header row
                
                for item in findings_list:
                    question = html.escape(item.get("question", "N/A"))
                    
                    # Get answer status
                    answer_bool = item.get("answer")
                    if answer_bool is True:
                        answer_text = "YES"
                        answer_color = colors.green
                    elif answer_bool is False:
                        answer_text = "NO"
                        answer_color = colors.red
                    else:
                        answer_text = "Unsure"
                        answer_color = colors.orange
                    
                    # Get reasoning (the detailed explanation)
                    reasoning_text = html.escape(item.get("reasoning", "N/A"))
                    
                    # Create table cells
                    question_para = Paragraph(question, normal_style)
                    answer_para = Paragraph(f'<font color="{answer_color.hexval()}">{answer_text}</font>', normal_style)
                    reasoning_para = Paragraph(reasoning_text, normal_style)
                    
                    table_data.append([question_para, answer_para, reasoning_para])
                
                if len(table_data) > 1:  # Only create table if we have data beyond header
                    # Create table with appropriate column widths
                    col_widths = [2.5*inch, 0.8*inch, 4.2*inch]  # Adjust to fit letter page
                    table = Table(table_data, colWidths=col_widths)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.grey),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                        ('VALIGN', (0,0), (-1,-1), 'TOP'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0,0), (-1,0), 10),
                        ('GRID', (0,0), (-1,-1), 1, colors.black),
                        ('FONTSIZE', (0,0), (-1,-1), 9),  # Smaller font to fit more content
                    ]))
                    story.append(table)
                else:
                    story.append(Paragraph("No analysis data to display.", normal_style))
                story.append(Spacer(1, 0.15*inch))


            
            elif service_key == "reviewer_feedback":
                 for item in findings_list:
                    # Check if it's an error from the service itself
                    if item.get("type", "").endswith("_error"):
                        service_name = html.escape(item.get("service_name", "Feedback Service"))
                        error_explanation = html.escape(item.get("explanation", "An error occurred during feedback generation."))
                        story.append(Paragraph(f"<b>{service_name} Error:</b>", h3_style))
                        story.append(Paragraph(error_explanation, error_style))
                    elif item.get('service_name', '').endswith('(placeholder)'): # Legacy placeholder handling
                        service_name = html.escape(item.get("service_name", "Placeholder Service"))
                        placeholder_explanation = html.escape(item.get("explanation", "N/A"))
                        story.append(Paragraph(f"<b>{service_name}:</b>", h3_style))
                        story.append(Paragraph(f"<em>{placeholder_explanation}</em>", placeholder_style))
                    else: # Actual feedback display
                        service_name = html.escape(item.get("service_name", "Expert Reviewer Feedback"))
                        feedback_content = item.get("suggestion", "N/A")
                        explanation = item.get("explanation", "")
                        
                        story.append(Paragraph(f"<b>{service_name}:</b>", h3_style))
                        story.append(Spacer(1, 0.05*inch))
                        
                        # Handle feedback content similar to proposal analysis answers
                        # The feedback may contain markdown-like formatting from the LLM
                        if isinstance(feedback_content, str) and feedback_content != "N/A":
                            # Basic preprocessing for PDF display
                            feedback_display = html.escape(feedback_content)
                            
                            # Convert common markdown patterns to basic HTML
                            # Bold: **text** -> <b>text</b>
                            feedback_display = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', feedback_display)
                            
                            # Handle newlines for better PDF formatting
                            feedback_display = feedback_display.replace('\n\n', '<br/><br/>')
                            feedback_display = feedback_display.replace('\n', '<br/>')
                            
                            # Handle bullet points that might start with - or •
                            feedback_display = re.sub(r'<br/>[-•]\s*', r'<br/>&nbsp;&nbsp;&nbsp;&nbsp;• ', feedback_display)
                            
                            # Handle numbered lists
                            feedback_display = re.sub(r'<br/>(\d+\.)\s*', r'<br/>&nbsp;&nbsp;&nbsp;&nbsp;\1 ', feedback_display)
                            
                            story.append(Paragraph(feedback_display, normal_style))
                        else:
                            story.append(Paragraph("No feedback content available.", normal_style))
                        
                        # Add explanation if available and meaningful
                        if explanation and explanation != "N/A" and explanation.strip():
                            story.append(Spacer(1, 0.05*inch))
                            story.append(Paragraph(f"<i>{html.escape(explanation)}</i>", suggestion_style))
                        
                        story.append(Spacer(1, 0.15*inch))

            else: # Generic fallback for any other future service types
                story.append(Paragraph(f"<i>Note: Unknown service type '{service_key}'. Displaying raw data:</i>", self.styles['Italic']))
                story.append(Spacer(1, 0.05*inch))
                for item in findings_list:
                    if isinstance(item, dict):
                        # Try to display dictionary items in a more structured way
                        for key, value in item.items():
                            if isinstance(value, str) and len(value) > 100:
                                # For long string values, display them on separate lines
                                story.append(Paragraph(f"<b>{html.escape(str(key))}:</b>", normal_style))
                                story.append(Paragraph(html.escape(str(value)), code_style))
                            else:
                                story.append(Paragraph(f"<b>{html.escape(str(key))}:</b> {html.escape(str(value))}", normal_style))
                        story.append(Spacer(1, 0.05*inch))
                    else:
                        story.append(Paragraph(html.escape(str(item)), normal_style))
                story.append(Spacer(1, 0.15*inch))
        
        # Final note
        story.append(Spacer(1, 0.3*inch))
        end_style = self.styles['Italic'].clone('centered_italic')
        end_style.alignment = 1  # Center alignment
        story.append(Paragraph("<i>End of Report</i>", end_style))

        try:
            doc.build(story)
            return str(self.export_path)
        except Exception as e:
            print(f"Error building PDF for {proposal_filename}: {e}")
            # Consider logging this error more formally
            return None 