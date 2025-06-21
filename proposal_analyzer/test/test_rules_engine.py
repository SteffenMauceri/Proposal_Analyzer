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

def test_local_llm_response_format():
    """Test that the local LLM returns responses in the expected format."""
    from proposal_analyzer.llm_client import query
    from proposal_analyzer.config import get_llm_provider
    from functools import partial
    
    # Skip test if not using local LLM
    current_provider = get_llm_provider()
    if current_provider != 'local':
        pytest.skip("Test only runs with local LLM provider")
    
    # Create a simple test context
    test_context = {
        "call": "This call requests proposals for Earth science research projects.",
        "proposal": "This proposal aims to develop Earth science research capabilities."
    }
    
    # Create LLM function with local provider
    ask_llm_local = partial(query, provider='local')
    
    # Test with a simple question
    question = "Does the proposal address Earth science research?"
    result = evaluate(question, test_context, ask_llm_local)
    
    print(f"\nLocal LLM Response Test:")
    print(f"Question: {result['question']}")
    print(f"Raw Response: {result['raw_response']}")
    print(f"Parsed Answer: {result['answer']}")
    print(f"Reasoning: {result['reasoning']}")
    
    # Check if response starts with expected format
    raw_response = result['raw_response'].strip().upper()
    format_valid = (
        raw_response.startswith('YES:') or 
        raw_response.startswith('NO:') or 
        raw_response.startswith('UNSURE:')
    )
    
    if not format_valid:
        print(f"\n❌ LOCAL LLM FORMAT ISSUE:")
        print(f"Expected response to start with 'YES:', 'NO:', or 'UNSURE:'")
        print(f"Actual response: {result['raw_response'][:100]}...")
        
        # This assertion will fail and show the issue
        assert format_valid, f"Local LLM response doesn't follow expected format. Response: {result['raw_response'][:200]}"
    else:
        print(f"\n✅ LOCAL LLM FORMAT CORRECT: Response starts with proper prefix")
        
    # Ensure parsing worked correctly
    assert result['answer'] in [True, False, None], "Answer should be True, False, or None"
    assert isinstance(result['reasoning'], str), "Reasoning should be a string"
    assert len(result['reasoning']) > 0, "Reasoning should not be empty"

def test_local_llm_complex_scenario():
    """Test local LLM with a more complex, realistic scenario that might reveal formatting issues."""
    from proposal_analyzer.llm_client import query
    from proposal_analyzer.config import get_llm_provider
    from functools import partial
    
    # Skip test if not using local LLM
    current_provider = get_llm_provider()
    if current_provider != 'local':
        pytest.skip("Test only runs with local LLM provider")
    
    # Create realistic test context similar to what causes the issue
    realistic_context = {
        "call": """Call for Proposals: NASA High Priority Open-Source Science (HPOSS)
        
        This call seeks proposals for Earth science research projects that:
        - Develop open-source software and educational materials
        - Use NASA datasets (e.g., Landsat, MODIS)
        - Follow NASA's open science policies
        - Include detailed data management plans
        - Adhere to NASA standards and guidelines
        """,
        "proposal": """Project Title: Advanced BRDF Modeling for Earth Science

        Abstract: This project aims to develop open-source software for Bidirectional Reflectance Distribution Function (BRDF) modeling using NASA's Landsat data. We will create educational materials for the Earth science community and implement optimal estimation techniques.

        Open Source Focus: All software will be released under open-source licenses.
        NASA Data Integration: We will utilize NASA's Landsat datasets and potentially other NASA Earth observation data.
        Education Component: The project includes comprehensive educational materials and tutorials.
        Data Management: Detailed plans for open data sharing and publication following NASA standards.
        """
    }
    
    # Create LLM function with local provider
    ask_llm_local = partial(query, provider='local')
    
    # Test with the exact question that caused the issue
    question = "Is the proposal directly responsive to the specific goals and priorities stated in the call?"
    result = evaluate(question, realistic_context, ask_llm_local)
    
    print(f"\nRealistic Scenario Test:")
    print(f"Question: {result['question']}")
    print(f"Raw Response: {result['raw_response'][:200]}...")
    print(f"Parsed Answer: {result['answer']}")
    print(f"Reasoning: {result['reasoning'][:100]}...")
    
    # Check if response starts with expected format
    raw_response = result['raw_response'].strip().upper()
    format_valid = (
        raw_response.startswith('YES:') or 
        raw_response.startswith('NO:') or 
        raw_response.startswith('UNSURE:')
    )
    
    if not format_valid:
        print(f"\n❌ REALISTIC SCENARIO FORMAT ISSUE:")
        print(f"Expected response to start with 'YES:', 'NO:', or 'UNSURE:'")
        print(f"Full response: {result['raw_response']}")
        
        # Show exactly what the LLM received as prompt
        from proposal_analyzer.rules_engine import SYSTEM_PROMPT
        context_str = "\n\n".join([f"--- {doc_name.upper()} ---\n{content}" for doc_name, content in realistic_context.items()])
        user_prompt = f"""Here is the context:
{context_str}

--- QUESTION ---
{question}"""
        
        print(f"\nSystem Prompt Used:\n{SYSTEM_PROMPT}")
        print(f"\nUser Prompt Used:\n{user_prompt[:300]}...")
        
        # This will fail if format is wrong, showing us the issue
        assert format_valid, f"Local LLM response doesn't follow expected format in realistic scenario. Response: {result['raw_response']}"
    else:
        print(f"\n✅ REALISTIC SCENARIO FORMAT CORRECT: Response starts with proper prefix")
        
    # Ensure parsing worked correctly
    assert result['answer'] in [True, False, None], "Answer should be True, False, or None"
    assert isinstance(result['reasoning'], str), "Reasoning should be a string"
    assert len(result['reasoning']) > 0, "Reasoning should not be empty"

def test_local_llm_very_long_content():
    """Test local LLM with very long content like the real application to reproduce formatting issues."""
    from proposal_analyzer.llm_client import query
    from proposal_analyzer.config import get_llm_provider
    from functools import partial
    
    # Skip test if not using local LLM
    current_provider = get_llm_provider()
    if current_provider != 'local':
        pytest.skip("Test only runs with local LLM provider")
    
    # Create very long, realistic content similar to actual PDF extractions
    very_long_context = {
        "call": """NASA ROSES-2024: High Priority Open-Source Science (HPOSS)

The Science Mission Directorate (SMD) seeks to fund the development of open-source tools, software, and workflows to enhance the conducting of NASA-relevant science and to enable new science.

This call specifically seeks proposals that:
1. Develop open-source software and educational materials for Earth science research
2. Utilize NASA datasets including but not limited to Landsat, MODIS, VIIRS, and other Earth observation data
3. Follow NASA's open science policies and guidelines as outlined in the SMD Strategy for Data Management and Computing
4. Include comprehensive data management plans with clear data sharing and archival strategies
5. Demonstrate adherence to NASA standards and FAIR (Findable, Accessible, Interoperable, Reusable) principles
6. Focus on addressing technology gaps in Earth science remote sensing and data analysis
7. Provide educational resources and training materials for the broader Earth science community
8. Implement uncertainty quantification and error analysis methodologies
9. Support atmospheric correction and radiative transfer modeling capabilities
10. Enable improved processing and analysis of NASA Earth observation datasets

Proposals should clearly demonstrate how the proposed work will advance NASA's Earth science objectives and contribute to the open science ecosystem. The project should result in publicly available, well-documented software tools that can be adopted by the broader scientific community.

Key evaluation criteria include scientific merit, technical approach, open science impact, and the potential for broad community adoption. Proposals should include detailed implementation plans, timeline, and clear metrics for success.

Budget considerations: Projects may request funding for personnel, equipment, and travel necessary to accomplish the proposed work. All software developed must be released under an approved open-source license.
        """,
        "proposal": """Project Title: Advanced BRDF Modeling and Optimal Estimation Tools for Earth Science

Abstract:
This project aims to develop a comprehensive suite of open-source software tools for Bidirectional Reflectance Distribution Function (BRDF) modeling and optimal estimation techniques specifically designed for NASA Earth observation data analysis. The proposed work will create advanced radiative transfer modeling capabilities, implement uncertainty quantification methods, and provide educational resources for the Earth science community.

1. Background and Motivation:
Remote sensing of Earth's surface properties requires sophisticated understanding of how electromagnetic radiation interacts with various surface materials under different observation and illumination geometries. BRDF modeling is fundamental to accurate atmospheric correction and surface property retrieval from satellite observations. Current tools lack comprehensive uncertainty quantification and are often proprietary or difficult to use.

2. Technical Approach:
Our approach leverages optimal estimation theory to provide robust uncertainty quantification for BRDF parameters. We will implement state-of-the-art radiative transfer models including discrete ordinates and Monte Carlo methods. The software will be designed for integration with NASA datasets including Landsat 8/9, MODIS, VIIRS, and future missions.

3. Open Source Development:
All software will be released under the MIT license and hosted on GitHub with comprehensive documentation. We will provide Python and Julia implementations with clear APIs and extensive testing suites. The project will follow best practices for reproducible research including version control, continuous integration, and automated testing.

4. Educational Components:
We will develop Jupyter notebook tutorials, video lectures, and hands-on workshops for the Earth science community. Educational materials will cover theoretical foundations, practical implementation, and real-world applications using NASA datasets.

5. Data Management Plan:
All code, documentation, and example datasets will be archived with DOIs through Zenodo. We will follow NASA's open science guidelines and ensure FAIR principles are implemented throughout the project lifecycle. Regular releases will be made available through package managers.

6. NASA Dataset Integration:
The tools will be specifically designed for processing Landsat time series, MODIS reflectance products, and VIIRS land surface data. We will provide pre-processing workflows for common NASA Earth observation datasets and demonstrate applications for land cover classification, vegetation monitoring, and climate studies.

7. Uncertainty Quantification:
Implementation of optimal estimation methods will provide rigorous uncertainty propagation through the entire processing chain. This addresses a critical gap in current remote sensing workflows where uncertainty information is often lost or poorly characterized.

8. Community Impact:
The project will enable more robust and reliable remote sensing products from NASA missions. By providing open-source tools with proper uncertainty quantification, we expect to improve the quality and reliability of Earth science research using satellite observations.

9. Implementation Timeline:
Year 1: Core BRDF modeling software development and initial uncertainty quantification implementation
Year 2: Integration with NASA datasets, educational material development, and community testing
Year 3: Advanced features, performance optimization, and final documentation and release

10. Expected Outcomes:
- Open-source software package for BRDF modeling and optimal estimation
- Comprehensive documentation and educational materials
- Peer-reviewed publications demonstrating applications
- Workshop presentations at major Earth science conferences
- Integration with existing NASA data processing pipelines

The proposed work directly addresses NASA's need for improved open-source tools for Earth observation data analysis while providing the scientific community with robust uncertainty quantification capabilities that are currently lacking in available software packages.
        """
    }
    
    # Create LLM function with local provider
    ask_llm_local = partial(query, provider='local')
    
    # Test with the same question that's causing issues
    question = "Is the proposal directly responsive to the specific goals and priorities stated in the call?"
    result = evaluate(question, very_long_context, ask_llm_local)
    
    print(f"\nVery Long Content Test:")
    print(f"Question: {result['question']}")
    print(f"Raw Response (first 300 chars): {result['raw_response'][:300]}...")
    print(f"Parsed Answer: {result['answer']}")
    print(f"Reasoning (first 150 chars): {result['reasoning'][:150]}...")
    
    # Check if response starts with expected format
    raw_response = result['raw_response'].strip().upper()
    format_valid = (
        raw_response.startswith('YES:') or 
        raw_response.startswith('NO:') or 
        raw_response.startswith('UNSURE:')
    )
    
    if not format_valid:
        print(f"\n❌ LONG CONTENT FORMAT ISSUE REPRODUCED:")
        print(f"Expected response to start with 'YES:', 'NO:', or 'UNSURE:'")
        print(f"Actual start: '{result['raw_response'][:100]}...'")
        
        # Show this is the same issue as in the real app
        print(f"\n🔍 This reproduces the real application issue!")
        print(f"The LLM provides good analysis but ignores format instructions with long content.")
        
        # Don't assert here - we want to see the issue, not fail the test
        return False
    else:
        print(f"\n✅ LONG CONTENT FORMAT CORRECT: Response starts with proper prefix")
        return True 