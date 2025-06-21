from functools import partial
from typing import List, Dict, Any, Optional
import openai # Added for type hint
from tqdm import tqdm # Added tqdm import

# Relative imports for modules within the same package
from .loaders import load_pdf, load_docx, load_txt
from .rules_engine import evaluate
from .llm_client import query as ask_llm # Using 'query' from llm_client as 'ask_llm'

def analyze(
    call_p: str, 
    prop_p: str, 
    q_p: str, 
    model: str = "gpt-4.1-mini-2025-04-14",
    llm_client_instance: Optional[openai.OpenAI] = None,
    instructions: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Analyzes a proposal against a call for proposals and a list of questions.

    Args:
        call_p: Path to the call for proposal document (PDF or DOCX).
        prop_p: Path to the proposal document (PDF or DOCX).
        q_p: Path to the text file containing questions (one per line).
        model: The language model to use for evaluation.
        llm_client_instance: Optional OpenAI client instance for testing.
        instructions: Optional extra instructions for the LLM prompt.

    Returns:
        A list of dictionaries, where each dictionary contains the evaluation result
        for a question (question, answer, reasoning, raw_response).
    """
    ctx: Dict[str, str] = {
        "call": (load_pdf if call_p.lower().endswith(".pdf") else load_docx)(call_p),
        "proposal": (load_pdf if prop_p.lower().endswith(".pdf") else load_docx)(prop_p),
    }
    
    questions: List[str] = load_txt(q_p)
    
    results: List[Dict[str, Any]] = []
    
    # Get the current provider configuration to ensure correct LLM is used
    from .config import get_llm_provider
    current_provider = get_llm_provider()
    llm_call_for_evaluate = partial(ask_llm, model=model, client=llm_client_instance, provider=current_provider)
    
    for q_text in tqdm(questions, desc="Evaluating questions", unit="question"):
        results.append(evaluate(question=q_text, context=ctx, ask=llm_call_for_evaluate, instructions=instructions))
        
    return results

# Example of how it might be called (for understanding, not execution here):
# if __name__ == '__main__':
#     # This is a conceptual example. Paths and API key setup would be needed.
#     # Ensure 'key.txt' is in the correct location relative to config.py or OPENAI_API_KEY is set.
#     
#     # Create dummy files for testing if they don't exist
#     # Create dummy proposal_analyzer/__init__.py if it does not exist
#     # with open("proposal_analyzer/__init__.py", "w") as f:
#     #     pass # Ensure package can be recognized
# 
#     # Create dummy files in a 'test_data' directory
#     # import os
#     # if not os.path.exists("test_data"):
#     #    os.makedirs("test_data")
#     # with open("test_data/dummy_call.pdf", "w") as f: f.write("Dummy PDF for call") # PyPDF2 needs a real PDF
#     # with open("test_data/dummy_proposal.pdf", "w") as f: f.write("Dummy PDF for proposal") # PyPDF2 needs a real PDF
#     # with open("test_data/dummy_template.docx", "w") as f: f.write("Dummy DOCX for template") # python-docx needs a real DOCX
#     # with open("test_data/dummy_questions.txt", "w") as f: f.write("Is the sky blue?\nDoes water flow uphill?")
# 
#     # print("Note: For the example to run, you need valid PDF/DOCX files and an OpenAI API key.")
#     # try:
#     #     # This conceptual call won't run directly without real files and API key setup.
#     #     # analysis_results = analyze(
#     #     #     call_p="test_data/dummy_call.pdf",
#     #     #     prop_p="test_data/dummy_proposal.pdf",
#     #     #     templ_p="test_data/dummy_template.docx",
#     #     #     q_p="test_data/dummy_questions.txt"
#     #     # )
#     #     # for res in analysis_results:
#     #     #     print(f"Q: {res['question']}\nA: {res['answer']}\nR: {res['reasoning']}\n---")
#     #     print("Conceptual example structure. To run, provide valid paths and ensure API key is configured.")
#     # except Exception as e:
#     #     print(f"Error in conceptual example: {e}")
#     #     print("This could be due to missing dummy files, invalid file formats, or API key issues.") 