import pytest
from pathlib import Path
from typing import List, Dict, Any, Callable

@pytest.fixture(scope="session")
def data_dir(tmp_path_factory) -> Path:
    # Using a temporary directory for test data is good practice,
    # but the user specified creating files in proposal_analyzer/test/data.
    # For now, let's assume these files are created manually or by previous steps
    # and provide a fixture that points to this existing relative directory.
    # If these files were truly temporary and created by this fixture, 
    # tmp_path_factory would be used to make them.
    # Since they are now actual files, we just return the path to them.
    return Path(__file__).parent / "data"

@pytest.fixture
def sample_questions_txt_path(data_dir: Path) -> Path:
    return data_dir / "dummy_questions.txt"

@pytest.fixture
def sample_call_content_path(data_dir: Path) -> Path:
    return data_dir / "dummy_call_content.txt"

@pytest.fixture
def sample_proposal_content_path(data_dir: Path) -> Path:
    return data_dir / "dummy_proposal_content.txt"

@pytest.fixture
def sample_template_content_path(data_dir: Path) -> Path:
    return data_dir / "dummy_template_content.txt"


# --- Mocks for LLM Client and Rules Engine --- #

class MockMessage:
    def __init__(self, content: str):
        self.content = content

class MockChoice:
    def __init__(self, content: str):
        self.message = MockMessage(content)

class MockCompletion:
    def __init__(self, choices_content: List[str]):
        self.choices = [MockChoice(c) for c in choices_content]

class MockChatCompletions:
    def __init__(self, deterministic_responses: List[str]):
        self.responses = deterministic_responses
        self.call_count = 0
        self.last_messages_received: List[Dict[str,str]] = []

    def create(self, *, model: str, messages: List[Dict[str, str]], **kwargs):
        self.last_messages_received = messages
        response_content = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return MockCompletion([response_content])

class MockOpenAI:
    def __init__(self, deterministic_responses: List[str]):
        self.chat = self  # To allow client.chat.completions
        self.completions = MockChatCompletions(deterministic_responses)

@pytest.fixture
def mock_llm_responses() -> List[str]:
    return [
        "YES: Mocked: Requirement A is met.",
        "NO: Mocked: Proposal does not mention B adequately.",
        "YES: Mocked: Section C is included as required."
    ]

@pytest.fixture
def mock_openai_client(mock_llm_responses: List[str]):
    return MockOpenAI(deterministic_responses=mock_llm_responses)


# Fixtures for testing rules_engine.evaluate directly

@pytest.fixture
def mock_ask_yes() -> Callable[[List[Dict[str, str]]], str]:
    def _mock_ask(messages: List[Dict[str, str]]) -> str:
        return "YES: This is a positive mocked response for rule engine."
    return _mock_ask

@pytest.fixture
def mock_ask_no() -> Callable[[List[Dict[str, str]]], str]:
    def _mock_ask(messages: List[Dict[str, str]]) -> str:
        return "NO: This is a negative mocked response for rule engine."
    return _mock_ask

@pytest.fixture
def mock_ask_invalid() -> Callable[[List[Dict[str, str]]], str]:
    def _mock_ask(messages: List[Dict[str, str]]) -> str:
        return "GARBAGE_RESPONSE_NO_YES_NO_PREFIX"
    return _mock_ask 