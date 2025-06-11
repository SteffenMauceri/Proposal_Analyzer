import pytest
from pathlib import Path
from unittest.mock import MagicMock, mock_open

from proposal_analyzer.loaders import load_pdf, load_docx, load_txt

def test_load_txt(sample_questions_txt_path: Path):
    questions = load_txt(str(sample_questions_txt_path))
    assert len(questions) == 3
    assert questions[0] == "Is requirement A met?"
    assert questions[1] == "Does the proposal mention B?"
    assert questions[2] == "Is section C included?"
    # Test that blank lines are stripped and not included
    with open(sample_questions_txt_path, 'r') as f:
        raw_lines = len(f.readlines())
    assert raw_lines == 4 # Including one blank line

def test_load_pdf(mocker, sample_call_content_path: Path):
    # sample_call_content_path points to a .txt file for this mock test
    # We will mock PyPDF2.PdfReader
    
    mock_pdf_reader_instance = MagicMock()
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Page 1 PDF content."
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Page 2 PDF content."
    mock_pdf_reader_instance.pages = [mock_page1, mock_page2]
    
    # Mock the constructor of PdfReader
    mock_pdf_reader_constructor = mocker.patch('PyPDF2.PdfReader', return_value=mock_pdf_reader_instance)
    
    # Mock open() because load_pdf opens the file in binary mode
    # The actual content of dummy_call_content.txt doesn't matter here as PdfReader is fully mocked.
    mocker.patch('builtins.open', mock_open(read_data=b'dummy binary pdf data'))

    content = load_pdf(str(sample_call_content_path)) # Path can be anything for this test
    
    assert content == "Page 1 PDF content.\nPage 2 PDF content."
    # PyPDF2.PdfReader is called with the file object from open()
    # We can check that open was called with the right path and mode
    builtins_open_mock = mocker.mocks_used[-1] # Get the mock_open instance if needed for assert_called_with
    # For now, just checking PdfReader was constructed suffices
    mock_pdf_reader_constructor.assert_called_once()

def test_load_docx(mocker, sample_template_content_path: Path):
    # sample_template_content_path points to a .txt file for this mock test
    # We will mock docx.Document

    mock_doc_instance = MagicMock()
    mock_para1 = MagicMock()
    mock_para1.text = "DOCX Paragraph 1 from mock."
    mock_para2 = MagicMock()
    mock_para2.text = "DOCX Paragraph 2 from mock."
    mock_doc_instance.paragraphs = [mock_para1, mock_para2]

    # Mock the constructor of Document
    # python-docx's Document() takes the file path directly
    mock_document_constructor = mocker.patch('docx.Document', return_value=mock_doc_instance)

    content = load_docx(str(sample_template_content_path)) # Path is passed to Document()
    
    assert content == "DOCX Paragraph 1 from mock.\nDOCX Paragraph 2 from mock."
    mock_document_constructor.assert_called_once_with(str(sample_template_content_path)) 