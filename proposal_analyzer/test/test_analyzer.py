import pytest
from pathlib import Path
from typing import List, Dict, Any
from unittest.mock import MagicMock

from proposal_analyzer.analyzer import analyze
# mock_openai_client is from conftest.py and will be injected by pytest

@pytest.fixture
def mock_loaders(mocker, 
                 sample_call_content_path: Path, 
                 sample_proposal_content_path: Path, 
                 sample_questions_txt_path: Path):
    """Mocks all loader functions used by analyzer.py"""
    
    call_content = sample_call_content_path.read_text()
    proposal_content = sample_proposal_content_path.read_text()
    questions_list = [line.strip() for line in sample_questions_txt_path.read_text().splitlines() if line.strip()]

    mocker.patch(
        "proposal_analyzer.analyzer.load_pdf", 
        side_effect=lambda p: proposal_content if "proposal" in str(p).lower() else call_content
    )
    mocker.patch(
        "proposal_analyzer.analyzer.load_docx", 
        side_effect=lambda p: proposal_content if "proposal" in str(p).lower() else "Unexpected DOCX call for testing"
    )
    mocker.patch("proposal_analyzer.analyzer.load_txt", return_value=questions_list)
    
    return {
        "call_content": call_content,
        "proposal_content": proposal_content,
        "questions_list": questions_list
    }

def test_analyze_integration(
    mock_loaders, # This fixture sets up the mocks for loaders
    mock_openai_client, # This fixture provides the mock LLM client
    sample_questions_txt_path: Path, # Used to get paths for analyze function arguments
    sample_call_content_path: Path, # Only path needed, content is mocked
    sample_proposal_content_path: Path, # Only path needed, content is mocked
):
    """
    Tests the full analyze() function using mocked loaders and a mock LLM client.
    (Template comparison removed)
    Ensures the number of results matches the number of questions.
    """
    num_expected_questions = len(mock_loaders["questions_list"])
    
    # The paths passed here are nominal; the content is determined by mock_loaders
    # We use different paths for proposal to test the pdf/docx switch in analyze, 
    # handled by the side_effect in mock_loaders for load_pdf.
    
    # Scenario 1: Proposal is a PDF
    results_pdf_proposal = analyze(
        call_p=str(sample_call_content_path),       # loader mock returns call_content
        prop_p=str(sample_proposal_content_path.with_suffix(".pdf")), # loader mock for pdf returns proposal_content
        q_p=str(sample_questions_txt_path),         # loader mock returns questions_list
        llm_client_instance=mock_openai_client
    )
    
    assert len(results_pdf_proposal) == num_expected_questions
    assert mock_openai_client.completions.call_count == num_expected_questions
    
    # Check content of prompts sent to mock LLM (optional, but good for sanity)
    # The mock_openai_client.completions.last_messages_received will have the messages for the *last* call.
    # To check all, the mock would need to store all messages from all calls.
    # For now, we just check the call count.

    # Reset call count for the next scenario
    mock_openai_client.completions.call_count = 0
    mock_openai_client.completions.last_messages_received = []

    # Scenario 2: Proposal is a DOCX
    results_docx_proposal = analyze(
        call_p=str(sample_call_content_path), # load_pdf -> call_content
        prop_p=str(sample_proposal_content_path.with_suffix(".docx")), # should use load_docx
        q_p=str(sample_questions_txt_path), # load_txt -> questions_list
        llm_client_instance=mock_openai_client
    )

    assert len(results_docx_proposal) == num_expected_questions
    # Call count will be cumulative if not reset, so num_expected_questions * 2 if run after PDF test
    assert mock_openai_client.completions.call_count == num_expected_questions # Since it was reset

    # A more robust test would involve distinct content for proposal.docx and check it in the context
    # sent to the LLM. For now, focusing on call count and result length. 