from pathlib import Path
from typing import List, Dict, Any, Optional
import openai

# Import for actual LLM calls
from proposal_analyzer.llm_client import query # Assuming this is the correct path

class ReviewerFeedbackService:
    """
    A service to generate expert reviewer-style feedback on a proposal.
    """

    def __init__(self, model_name: str = "gpt-4.1-nano", client: Optional[openai.OpenAI] = None, reviewer_name: str = "Senior Scientist (Technical Rigor Focus)"):
        """
        Initializes the ReviewerFeedbackService.

        Args:
            model_name (str): The name of the language model to be used.
            client (Optional[openai.OpenAI]): An optional pre-configured OpenAI client instance.
        """
        self.model_name = model_name
        self.client = client
        self.reviewer_name = reviewer_name
        if reviewer_name == "Senior Scientist (Technical Rigor Focus)":
            self.system_prompt = (
                """You are a senior NASA ROSES reviewer evaluating a research proposal under Dual-Anonymous Peer Review. 

                IMPORTANT: You are reviewing the PROPOSAL document, not the call for proposals. The call document is provided for context only.
                
                1. Use neutral language focused on the work (e.g., "the proposed investigation will…").  
                2. Provide a score (1–5) for each of the following criteria based on the PROPOSAL:  
                a. Scientific/Technical Merit  
                b. Relevance to NASA Objectives  
                c. Cost Reasonableness  
                3. For each score, give a concise justification (1–2 sentences each) referencing specific methodological, theoretical, or technical aspects from the PROPOSAL.  
                4. Summarize major strengths (no more than 5 bullet points) related to scientific rigor, technical approach, innovation, and analysis methods found in the PROPOSAL.  
                5. Summarize major weaknesses (no more than 5 bullet points) related to potential methodological flaws, inadequate uncertainty analysis, incomplete validation, or technical risks in the PROPOSAL.  
                6. Provide 1–2 minor suggestions (e.g., clarifying assumptions, refining methodologies, addressing technical gaps) to improve the PROPOSAL.    """)
            
        elif reviewer_name == "Early‑Career Researcher (Innovation & Feasibility Focus)":
            self.system_prompt = (
                """You are an early-career researcher reviewing a research proposal for NASA's ROSES program under Dual-Anonymous Peer Review. Your focus is on innovation and practical feasibility across NASA's diverse science and technology domains.
                
                IMPORTANT: You are reviewing the PROPOSAL document, not the call for proposals. The call document is provided for context only.
                
                1. Employ neutral language (e.g., "the proposed investigation will…").  
                2. Assign a score (1–5) for each criterion based on the PROPOSAL:  
                a. Scientific/Technical Merit (emphasis on novelty and interdisciplinary integration)  
                b. Relevance to NASA Objectives (emphasis on advancing NASA's scientific and technological priorities)  
                c. Cost Reasonableness (emphasis on efficient resource use)  
                3. For each criterion, provide a brief rationale (1–2 sentences) focusing on creativity, integration of novel methods, technological innovation, and risk mitigation as presented in the PROPOSAL.  
                4. List up to 5 major strengths related to innovative aspects, potential for significant scientific or technological breakthroughs, creative approaches, or novel applications found in the PROPOSAL.  
                5. List up to 5 major weaknesses focused on feasibility concerns, unclear methodologies, technical risks, or overlooked challenges in the PROPOSAL.  
                6. Offer 1–2 minor recommendations for improving clarity of objectives, reducing technical risk, or enhancing feasibility in the PROPOSAL.  
            """)

        elif reviewer_name == "Program Manager (Programmatic Fit Focus)":
            self.system_prompt = (
                """You are a NASA program manager reviewing a research proposal under Dual-Anonymous Peer Review for your program. Your focus is on programmatic relevance, and strategic fit.
                
                IMPORTANT: You are reviewing the PROPOSAL document, not the call for proposals. The call document is provided for context only.
                
                1. Use neutral language (e.g., "the proposed investigation will…").  
                2. Provide a numeric score (1–5) for each criterion based on the PROPOSAL:  
                a. Scientific/Technical Merit (briefly, from a programmatic standpoint)  
                b. Relevance to NASA Objectives (emphasis on alignment with NASA's strategic goals and mission priorities)  
                3. For each criterion, give a concise explanation (1–2 sentences) focusing on budget structure, timeline feasibility, resource allocation, and strategic alignment as presented in the PROPOSAL.  
                4. Identify up to 5 major strengths related to realistic work plans, justified budget items, clear milestones, appropriate team composition, or strong institutional capabilities in the PROPOSAL.  
                5. Identify up to 5 major weaknesses such as budget overestimations, unsupported resource requests, unrealistic timelines, inadequate team expertise, or misaligned objectives in the PROPOSAL.
            """)
        else:
            raise ValueError(f"Invalid reviewer name: {reviewer_name}")
        
        self.system_prompt += (
            """
            REMINDER: Focus your review entirely on the PROPOSAL document. The call document is only provided for context to understand what the proposal is responding to.
            
            If you can't answer a question based on the provided proposal, just say "N/A". Don't make up information.

            **Output Format**:  
            1. Scientific/Technical Merit Score: X/5  
            - Explanation…  
            2. Relevance to NASA Score: Y/5  
            - Explanation…  
            3. Cost Reasonableness Score: Z/5  
            - Explanation…  
            **Major Strengths**:  
            – …  
            **Major Weaknesses**:  
            – …  
            **Expertise & Resources Category**: [Category]  
            - Justification…  
        """
        )

    def _call_llm_for_feedback(self, proposal_text: str, call_text: Optional[str] = None) -> str:
        """
        Calls the LLM to generate reviewer feedback.
        """
        user_content_parts = []
        user_content_parts.append(f"--- PROPOSAL TEXT TO REVIEW ---\n{proposal_text}")
        if call_text:
            user_content_parts.append(f"\n\n--- CALL FOR PROPOSAL TEXT (FOR CONTEXT ONLY) ---\n{call_text}")
        
        user_content = "\n".join(user_content_parts)
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content}
        ]

        # Get the current provider configuration
        from proposal_analyzer.config import get_llm_provider
        current_provider = get_llm_provider()
        
        raw_response = query(messages=messages, model=self.model_name, client=self.client, provider=current_provider)
        
        return raw_response.strip()

    def generate_feedback(
        self, 
        proposal_text: str, 
        proposal_filename: str, # Added to include in the output
        call_text: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates reviewer feedback for the given proposal text.

        Args:
            proposal_text (str): The text content of the proposal.
            proposal_filename (str): The filename of the proposal document (for context in output).
            call_text (Optional[str]): The text content of the call for proposal (optional).

        Returns:
            A list containing a dictionary with the feedback.
            This structure is to align with how other findings are processed in main.py.
        """
        if not proposal_text.strip():
            return [{
                "type": "reviewer_feedback_error",
                "service_name": "Expert Reviewer Feedback",
                "original_snippet": proposal_filename,
                "suggestion": "N/A",
                "explanation": "Proposal text was empty or contained only whitespace.",
                "line_number": -1,
                "char_offset_start_in_doc": 0,
                "line_with_error": None
            }]

        feedback_text = self._call_llm_for_feedback(proposal_text, call_text)

        if not feedback_text or feedback_text.startswith("Error:"):
            return [{
                "type": "reviewer_feedback_error",
                "service_name": "Expert Reviewer Feedback",
                "original_snippet": proposal_filename,
                "suggestion": "N/A",
                "explanation": f"Failed to get feedback from LLM. Response: {feedback_text}",
                "line_number": -1,
                "char_offset_start_in_doc": 0,
                "line_with_error": None
            }]

        # For now, we return the entire feedback as a single item.
        # "suggestion" can hold the main feedback content.
        # "explanation" can be used if we further differentiate parts of the feedback, or be brief.
        return [{
            "type": "reviewer_feedback", # More specific type
            "service_name": "Expert Reviewer Feedback",
            "original_snippet": f"Overall feedback for {proposal_filename}", # Contextual snippet
            "suggestion": feedback_text, # The main feedback from LLM
            "explanation": "The feedback above was generated by an AI expert reviewer model.", # General explanation
            "line_number": -1, # Not applicable for overall feedback
            "char_offset_start_in_doc": 0, # Not applicable
            "line_with_error": None # Not applicable
        }]

if __name__ == '__main__':
    # This section is for basic testing of the service.
    # Ensure OPENAI_API_KEY is set in your environment or accessible via config.
    
    # Create a dummy proposal text
    dummy_proposal = """
    Project Title: Advanced Quantum Entanglement for Secure Communications

    Abstract: This project aims to explore novel techniques for generating and
    maintaining quantum entanglement over extended distances. We propose a new
    method based on photonic crystal fibers that promises higher stability and
    lower decoherence rates. The successful completion of this project will 
    pave the way for ultra-secure communication networks.

    Objectives:
    1. Design and simulate the proposed photonic crystal fiber structure.
    2. Fabricate and experimentally validate the fiber's entanglement properties.
    3. Demonstrate entanglement distribution over a 10km fiber link.

    Methodology: We will use COMSOL for simulations, standard fiber drawing techniques
    for fabrication, and a state-of-the-art quantum optics lab for experimental validation.
    The team has extensive experience in all these areas.

    Expected Impact: A breakthrough in secure communications, with potential
    applications in defense, finance, and critical infrastructure.
    """
    
    dummy_call_text = """
    Call for Proposals: Next-Generation Communication Technologies

    We seek innovative research proposals focusing on groundbreaking technologies
    that can redefine communication in the next decade. Proposals should address
    scalability, security, and energy efficiency. 
    Particular interest in quantum communication, advanced optical networking, 
    and AI-driven network management. Max budget $500k. Duration 2 years.
    """

    print("Testing ReviewerFeedbackService with ACTUAL LLM...")
    
    try:
        # Initialize the service (replace with your desired model if needed)
        reviewer_service = ReviewerFeedbackService(model_name="gpt-4.1-nano")
        
        print(f"--- Generating feedback for dummy proposal (model: {reviewer_service.model_name}) ---")
        # feedback_results = reviewer_service.generate_feedback(dummy_proposal, "dummy_proposal.pdf")
        feedback_results_with_call = reviewer_service.generate_feedback(
            dummy_proposal, 
            "dummy_proposal.pdf", 
            dummy_call_text
        )

        print("\n--- Feedback (Proposal + Call Text) ---")
        if feedback_results_with_call:
            for item in feedback_results_with_call:
                print(f"Type: {item['type']}")
                print(f"Service: {item['service_name']}")
                print(f"Snippet: {item['original_snippet']}")
                print(f"Feedback/Suggestion:\n{item['suggestion']}")
                print(f"Explanation: {item['explanation']}")
                print("-" * 20)
        else:
            print("No feedback generated (with call text).")

    except Exception as e:
        print(f"An error occurred during the test: {e}")

    print("\nReviewerFeedbackService test finished.") 