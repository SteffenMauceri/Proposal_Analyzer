from typing import Callable, Dict, Any, Optional

SYSTEM_PROMPT = """You are an expert compliance checker. Based on the provided context (call for proposal and proposal document), answer the given question with exactly one of these three formats:

"YES: [explanation]" - if the proposal clearly meets the requirement
"NO: [explanation]" - if the proposal clearly does not meet the requirement  
"UNSURE: [explanation]" - if the information is unclear, missing, or ambiguous in the call or proposal document

CRITICAL INSTRUCTION: You MUST start your response with exactly one of these prefixes: "YES:", "NO:", or "UNSURE:"

DO NOT START WITH ANY OTHER WORDS. Examples of WRONG formats:
❌ "The proposal appears..."
❌ "Based on the document..."
❌ "Yes, the proposal..."
❌ "The proposal does not..."
❌ "This proposal..."

CORRECT FORMAT EXAMPLES:
✅ "YES: The proposal explicitly states..."
✅ "NO: The proposal does not mention..."
✅ "UNSURE: The proposal mentions alignment but..."

MANDATORY: Your first word must be either "YES:", "NO:", or "UNSURE:" followed by a colon and space.

If a question is about comparing the proposal to the call, it is ok to be unsure if the information is not provided in the call or proposal document.

REMINDER: Always start your response with exactly one of: YES:, NO:, or UNSURE:
Never start with any other phrase. This format is REQUIRED and NON-NEGOTIABLE.

FORMAT CHECK: Before responding, verify your answer starts with "YES:", "NO:", or "UNSURE:" - no exceptions allowed."""

def evaluate(question: str, context: Dict[str, str], ask: Callable[[Dict[str, Any]], str], instructions: Optional[str] = None) -> Dict[str, Any]:
    """
    Evaluates a given question against a context using an LLM.

    The LLM is prompted to answer with exactly "YES:", "NO:", or "UNSURE:" followed by an explanation.

    Args:
        question: The question to evaluate.
        context: A dictionary where keys are document types (e.g., "call", "proposal")
                 and values are the text content of these documents.
        ask: A callable (e.g., a partial function of llm_client.query) that takes a list of 
             message dictionaries and returns the LLM's response string.
        instructions: Optional extra instructions to append to the user prompt.

    Returns:
        A dictionary with keys:
            "question": The original question.
            "answer": Boolean (True if response starts with "YES:", False if "NO:", None if "Unsure:" or invalid).
            "reasoning": The explanation provided by the LLM after the prefix.
            "raw_response": The raw response from the LLM.
    """
    context_str = "\n\n".join([f"--- {doc_name.upper()} ---\n{content}" for doc_name, content in context.items()])
    
    user_prompt_content = f"""Here is the context:
{context_str}

--- QUESTION ---
{question}

IMPORTANT: Start your response with exactly "YES:", "NO:", or "UNSURE:" - no other format is acceptable."""
    if instructions:
        user_prompt_content += f"\nAdditional instructions: {instructions}\n"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt_content},
    ]

    raw_response = ask(messages=messages) # type: ignore 

    answer = None
    reasoning = ""

    response_strip = raw_response.strip()
    response_upper = response_strip.upper()
    if response_upper.startswith("YES:"):
        answer = True
        reasoning = response_strip[4:].strip()
    elif response_upper.startswith("NO:"):
        answer = False
        reasoning = response_strip[3:].strip()
    elif response_upper.startswith("UNSURE:"):
        answer = None
        reasoning = response_strip[7:].strip()
    else:
        # If the response doesn't match the expected format,
        # we capture the whole response as reasoning and set answer to None.
        answer = None 
        reasoning = f"Unexpected response format: {response_strip}"

    return {
        "question": question,
        "answer": answer,  # True for YES, False for NO, None for Unsure or invalid
        "reasoning": reasoning,
        "raw_response": raw_response
    } 