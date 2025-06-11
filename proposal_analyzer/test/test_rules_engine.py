import pytest
from proposal_analyzer.rules_engine import evaluate, SYSTEM_PROMPT
from typing import Dict, List

@pytest.fixture
def sample_context() -> Dict[str, str]:
    return {
        "call": "Call for proposal content.",
        "proposal": "Proposal content."
    }

def test_evaluate_yes_response(sample_context: Dict[str, str], mock_ask_yes):
    question = "Is the project compliant?"
    result = evaluate(question, sample_context, mock_ask_yes)

    assert result["question"] == question
    assert result["answer"] is True
    assert result["reasoning"] == "This is a positive mocked response for rule engine."
    assert result["raw_response"] == "YES: This is a positive mocked response for rule engine."

def test_evaluate_no_response(sample_context: Dict[str, str], mock_ask_no):
    question = "Are there any issues?"
    result = evaluate(question, sample_context, mock_ask_no)

    assert result["question"] == question
    assert result["answer"] is False
    assert result["reasoning"] == "This is a negative mocked response for rule engine."
    assert result["raw_response"] == "NO: This is a negative mocked response for rule engine."

def test_evaluate_invalid_response(sample_context: Dict[str, str], mock_ask_invalid):
    question = "What about this?"
    result = evaluate(question, sample_context, mock_ask_invalid)

    assert result["question"] == question
    assert result["answer"] is None
    assert result["reasoning"] == "Unexpected response format: GARBAGE_RESPONSE_NO_YES_NO_PREFIX"
    assert result["raw_response"] == "GARBAGE_RESPONSE_NO_YES_NO_PREFIX"

def test_evaluate_prompt_construction(mocker, sample_context: Dict[str, str]):
    question = "Test question for prompt."
    
    mock_ask_spy = mocker.MagicMock(return_value="YES: Spy success")
    
    evaluate(question, sample_context, mock_ask_spy)
    
    mock_ask_spy.assert_called_once()
    args_list = mock_ask_spy.call_args_list
    
    if 'messages' in args_list[0].kwargs:
        called_messages = args_list[0].kwargs['messages']
    else:
        called_messages = args_list[0].args[0]
        
    assert len(called_messages) == 2
    assert called_messages[0]["role"] == "system"
    assert called_messages[0]["content"] == SYSTEM_PROMPT
    
    assert called_messages[1]["role"] == "user"
    user_prompt = called_messages[1]["content"]
    
    assert f"--- CALL ---\n{sample_context['call']}" in user_prompt
    assert f"--- PROPOSAL ---\n{sample_context['proposal']}" in user_prompt
    assert f"--- QUESTION ---\n{question}" in user_prompt
    assert "Provide your answer in the format \"YES: [explanation]\" or \"NO: [explanation]\"." in user_prompt 