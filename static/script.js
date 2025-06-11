document.addEventListener('DOMContentLoaded', function () {
    console.log('DOM fully loaded and parsed'); // Debug: DOM loaded

    // Hidden Path Inputs (updated from visible inputs)
    const callPdfPathInput = document.getElementById('call-pdf-path'); // Hidden
    const proposalFilePathHiddenInput = document.getElementById('proposal-file-path-hidden'); // Hidden
    const questionsFilePathInput = document.getElementById('questions-file-path'); // Hidden

    // Questions Editor
    const questionsContentTextarea = document.getElementById('questions-content');

    // Analysis
    const runAnalysisBtn = document.getElementById('run-analysis-btn');
    const analysisOutputPre = document.getElementById('analysis-output');
    const analysisSpinner = document.getElementById('analysis-spinner');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('analysis-progress-bar');

    // Debug: Check if elements are found
    console.log('callPdfPathInput:', callPdfPathInput);
    console.log('proposalFilePathHiddenInput:', proposalFilePathHiddenInput);
    console.log('questionsFilePathInput:', questionsFilePathInput);
    console.log('questionsContentTextarea:', questionsContentTextarea);
    console.log('runAnalysisBtn:', runAnalysisBtn);
    console.log('analysisOutputPre:', analysisOutputPre);

    // Export related elements (referenced by inline script in index.html, but listed here for context if needed)
    // const exportPdfBtn = document.getElementById('export-pdf-btn');
    // const exportStatusP = document.getElementById('export-status');
    // const downloadLinkContainer = document.getElementById('download-link-container');

    // --- Get Checkbox Elements ---
    const analyzeProposalOptCheckbox = document.getElementById('analyze-proposal-opt');
    const spellCheckOptCheckbox = document.getElementById('spell-check-opt');
    const reviewerFeedbackOptCheckbox = document.getElementById('reviewer-feedback-opt');
    // const nasaPmFeedbackOptCheckbox = document.getElementById('nasa-pm-feedback-opt');

    // This variable will be populated by the 'result' event from SSE
    // It is used by the inline script in index.html for PDF export.
    // To make it accessible, we attach it to window or handle it via custom events if preferred.
    // For simplicity, using window for now, assuming script.js loads before inline script that might use it.
    window.currentAnalysisJsonResultsForExport = null;

    // --- File Input Elements (for getting file objects) ---
    const callPdfFileInput = document.getElementById('call_pdf_upload_input');
    const proposalFileInput = document.getElementById('proposal_file_upload_input');

    // Run Analysis
    if(runAnalysisBtn) {
        runAnalysisBtn.addEventListener('click', async () => {
            console.log('Run Analysis button clicked');

            // --- Get Files and Options ---
            const callPdfFile = callPdfFileInput.files[0];
            const proposalFile = proposalFileInput.files[0];
            const questionsContentToSave = questionsContentTextarea ? questionsContentTextarea.value.trim() : '';

            const analyzeProposalOpt = analyzeProposalOptCheckbox ? analyzeProposalOptCheckbox.checked : false;
            const spellCheckOpt = spellCheckOptCheckbox ? spellCheckOptCheckbox.checked : false;
            const reviewerFeedbackOpt = reviewerFeedbackOptCheckbox ? reviewerFeedbackOptCheckbox.checked : false;

            // --- Validate required files ---
            if (!callPdfFile) {
                alert('Call Document must be uploaded.');
                const statusEl = document.getElementById('call_upload_status');
                if(statusEl) { statusEl.textContent = 'Call Document is required.'; statusEl.style.color = 'red'; }
                return;
            }
            if (!proposalFile) {
                alert('Proposal PDF must be uploaded.');
                const statusEl = document.getElementById('proposal_upload_status');
                if(statusEl) { statusEl.textContent = 'Proposal PDF is required.'; statusEl.style.color = 'red'; }
                return;
            }

            // --- UI Reset for Analysis ---
            if (analysisOutputPre) {
                analysisOutputPre.textContent = 'Starting analysis...';
                analysisOutputPre.style.color = '#333';
            }
            const exportBtn = document.getElementById('export-pdf-btn');
            if(exportBtn) exportBtn.style.display = 'none';
            const dlContainer = document.getElementById('download-link-container');
            if(dlContainer) dlContainer.innerHTML = '';
            const expStatus = document.getElementById('export-status');
            if(expStatus) expStatus.textContent = '';
            window.currentAnalysisJsonResultsForExport = null;

            if(analysisSpinner) analysisSpinner.style.display = 'block';
            if(progressContainer) progressContainer.style.display = 'none';
            if(progressBar) progressBar.value = 0;
            // --- End UI Reset ---

            try {
                // --- Construct FormData ---
                const formData = new FormData();
                formData.append('call_pdf', callPdfFile);
                formData.append('proposal_pdf', proposalFile);
                formData.append('questions_content', questionsContentToSave);
                formData.append('analyze_proposal_opt', analyzeProposalOpt);
                formData.append('spell_check_opt', spellCheckOpt);
                formData.append('reviewer_feedback_opt', reviewerFeedbackOpt);
                
                appendToLog('Initiating analysis request...');
                const response = await fetch('/run_analysis', {
                    method: 'POST',
                    body: formData, // No 'Content-Type' header needed for FormData, browser sets it
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ message: 'Could not parse error response.' }));
                    throw new Error(errorData.message || `Server error: ${response.status}`);
                }
                if (!response.body) throw new Error('Response body is null.');

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                if(analysisSpinner && analysisSpinner.style.display !== 'block') analysisSpinner.style.display = 'block';
                if(progressContainer) progressContainer.style.display = 'none'; 

                async function processStream() {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) {
                            appendToLog('Analysis stream finished.');
                            if(progressBar && progressBar.value < 100) progressBar.value = 100;
                            if(analysisSpinner) analysisSpinner.style.display = 'none';
                            break;
                        }
                        buffer += decoder.decode(value, { stream: true });
                        let boundary = buffer.indexOf('\n\n');
                        while (boundary !== -1) {
                            const messageString = buffer.substring(0, boundary);
                            buffer = buffer.substring(boundary + 2);
                            if (messageString.startsWith('data: ')) {
                                const jsonDataString = messageString.substring(5);
                                try {
                                    const eventData = JSON.parse(jsonDataString);
                                    handleSseEvent(eventData);
                                } catch (e) {
                                    console.error('Error parsing SSE JSON:', e, jsonDataString);
                                    appendToLog(`Error parsing stream data: ${jsonDataString}`);
                                }
                            }
                            boundary = buffer.indexOf('\n\n');
                        }
                    }
                }
                await processStream();
            } catch (error) {
                console.error('Run Analysis Error:', error);
                if (analysisOutputPre) {
                    analysisOutputPre.textContent = `Error: ${error.message}`;
                    analysisOutputPre.style.color = 'red';
                }
                if(analysisSpinner) analysisSpinner.style.display = 'none';
                if(progressContainer) progressContainer.style.display = 'block';
                if(progressBar) progressBar.value = 100;
                appendToLog(`Client-side error during analysis: ${error.message}`);
            }
        });
    } else {
        console.error('Run Analysis button not found!'); // Debug: Button not found
    }

    function appendToLog(message) {
        console.log(`[${new Date().toLocaleTimeString()}] UI_LOG: ${message}`);
    }

    function handleSseEvent(eventData) {
        if (!eventData || !eventData.type) {
            console.warn('Received SSE event without type:', eventData);
            return;
        }
        appendToLog(`SSE Event: ${eventData.type}, Data: ${JSON.stringify(eventData.data || eventData.message || eventData.payload).substring(0,100)}`);

        switch (eventData.type) {
            case 'log': // General log from server
                // appendToLog(`SERVER_LOG: ${eventData.message}`); // Already logged by generic logger
                break;
            case 'progress': 
                if(analysisSpinner && analysisSpinner.style.display !== 'block') {
                    analysisSpinner.style.display = 'block'; 
                }
                if(progressContainer && progressContainer.style.display !== 'none') {
                    progressContainer.style.display = 'none'; 
                }
                break;
            case 'result': 
                if(analysisSpinner) analysisSpinner.style.display = 'none';
                if(progressBar) progressBar.value = 100;
                if (analysisOutputPre) {
                    analysisOutputPre.style.color = '#333';
                    analysisOutputPre.innerHTML = ''; 
                }
                
                console.log('[RESULT EVENT] typeof eventData.payload:', typeof eventData.payload);
                console.log('[RESULT EVENT] eventData.payload (raw):', eventData.payload);

                let proposalResult = eventData.payload;
                if (typeof proposalResult === 'string') {
                    try {
                        proposalResult = JSON.parse(proposalResult);
                        console.log('[RESULT EVENT] eventData.payload (parsed from string):', proposalResult);
                    } catch (e) {
                        console.error('[RESULT EVENT] Error parsing proposalResult from string:', e);
                        if(analysisOutputPre) analysisOutputPre.textContent = 'Error: Could not parse analysis result data (JSON format error).';
                        window.currentAnalysisJsonResultsForExport = null; // Ensure it's null on error
                        return; // Stop processing this event
                    }
                }

                window.currentAnalysisJsonResultsForExport = proposalResult; // Make results available for export
                
                if (proposalResult && typeof proposalResult === 'object') { 
                    const proposalContainer = document.createElement('div');
                    proposalContainer.classList.add('proposal-result-container');
                    const title = document.createElement('h3');
                    const proposalName = proposalFilePathHiddenInput.value.split(/[\/]/).pop() || 'Proposal';
                    title.textContent = `Results for: ${proposalName}`;
                    proposalContainer.appendChild(title);

                    // Flag to check if any results were rendered
                    let resultsRendered = false;

                    // Display Core Proposal Q&A Analysis
                    if (proposalResult.proposal_analysis && Array.isArray(proposalResult.proposal_analysis) && proposalResult.proposal_analysis.length > 0) {
                        const analysisTitle = document.createElement('h4');
                        analysisTitle.textContent = 'Core Proposal Q&A Analysis';
                        proposalContainer.appendChild(analysisTitle);

                        const table = document.createElement('table');
                        table.classList.add('results-table');
                        const thead = document.createElement('thead'); 
                        const headerRow = document.createElement('tr');
                        ['Question', 'Answer', 'Reasoning'].forEach(text => {
                            const th = document.createElement('th');
                            th.textContent = text;
                            headerRow.appendChild(th);
                        });
                        thead.appendChild(headerRow); table.appendChild(thead);
                        const tbody = document.createElement('tbody');
                        // Iterate over proposalResult.proposal_analysis
                        proposalResult.proposal_analysis.forEach(item => { 
                            const row = document.createElement('tr');
                            const qCell = document.createElement('td');
                            qCell.textContent = item.question;
                            row.appendChild(qCell);
                            const aCell = document.createElement('td');
                            let answerStr = item.answer_text || "Unsure";
                            let answerClass = 'answer-unsure';
                            if (item.answer === true || (item.answer_text && item.answer_text.toLowerCase() === 'yes')) {
                                answerStr = item.answer_text || "YES";
                                answerClass = 'answer-yes';
                            } else if (item.answer === false || (item.answer_text && item.answer_text.toLowerCase() === 'no')) {
                                answerStr = item.answer_text || "NO";
                                answerClass = 'answer-no';
                            }
                            aCell.textContent = answerStr;
                            aCell.classList.add(answerClass);
                            row.appendChild(aCell);
                            const rCell = document.createElement('td');
                            rCell.textContent = item.reasoning;
                            row.appendChild(rCell);
                            tbody.appendChild(row); 
                        });
                        table.appendChild(tbody);
                        proposalContainer.appendChild(table);
                        resultsRendered = true;
                    } 

                    // Display Spell Check Results
                    if (proposalResult.spell_check && Array.isArray(proposalResult.spell_check) && proposalResult.spell_check.length > 0) {
                        const spellCheckTitle = document.createElement('h4');
                        spellCheckTitle.textContent = 'Spell & Grammar Check';
                        proposalContainer.appendChild(spellCheckTitle);
                        
                        const spellCheckList = document.createElement('ul');
                        spellCheckList.classList.add('results-list');
                        proposalResult.spell_check.forEach(issue => {
                            const listItem = document.createElement('li');
                            let itemText = ``;
                            if (issue.line_number && issue.line_number !== -1) {
                                itemText += `Line ${issue.line_number} ('${issue.line_with_error || 'N/A'}'): `;
                            }
                            itemText += `'${issue.original_snippet}' → '${issue.suggestion}' (Type: ${issue.type}).`;
                            if (issue.explanation && issue.explanation !== "N/A") {
                                itemText += ` Why: ${issue.explanation}`;
                            }
                            listItem.textContent = itemText;
                            // Add styling for errors vs suggestions if desired
                            if (issue.type && issue.type.includes('error')) {
                                listItem.style.color = 'red';
                            }
                            spellCheckList.appendChild(listItem);
                        });
                        proposalContainer.appendChild(spellCheckList);
                        resultsRendered = true;
                    }

                    // Display Reviewer Feedback Results
                    if (proposalResult.reviewer_feedback && Array.isArray(proposalResult.reviewer_feedback) && proposalResult.reviewer_feedback.length > 0) {
                        const reviewerTitle = document.createElement('h4');
                        reviewerTitle.textContent = 'Expert Reviewer Feedback';
                        proposalContainer.appendChild(reviewerTitle);
                        
                        proposalResult.reviewer_feedback.forEach(item => {
                            const feedbackItemDiv = document.createElement('div');
                            feedbackItemDiv.classList.add('feedback-item');
                            if (item.type && item.type.endsWith('_error')) {
                                feedbackItemDiv.innerHTML = `<p><strong>Error:</strong> ${item.explanation || 'An error occurred.'}</p>`;
                                feedbackItemDiv.style.color = 'red';
                            } else {
                                const feedbackDisplayDiv = document.createElement('div');
                                feedbackDisplayDiv.classList.add('feedback-content'); 
                                const rawMarkdown = item.suggestion || 'N/A';
                                const dirtyHtml = marked.parse(rawMarkdown);
                                feedbackDisplayDiv.innerHTML = DOMPurify.sanitize(dirtyHtml);
                                feedbackItemDiv.appendChild(feedbackDisplayDiv);

                                if (item.explanation && item.explanation !== "N/A") {
                                    const explanationP = document.createElement('p');
                                    explanationP.textContent = `Note: ${item.explanation}`;
                                    explanationP.style.fontStyle = 'italic';
                                    explanationP.style.marginTop = '5px';
                                    feedbackItemDiv.appendChild(explanationP);
                                }
                            }
                            proposalContainer.appendChild(feedbackItemDiv);
                        });
                        resultsRendered = true;
                    }

                    // Display NASA PM Feedback Results (similar to Reviewer Feedback when implemented) -- REMOVED
                    // if (proposalResult.nasa_pm_feedback && Array.isArray(proposalResult.nasa_pm_feedback) && proposalResult.nasa_pm_feedback.length > 0) { ... }

                    // Fallback message if no specific results were rendered
                    if (!resultsRendered) {
                        const noDataMsg = document.createElement('p');
                        noDataMsg.textContent = 'No specific analysis results were generated or available for display from the selected services.';
                        proposalContainer.appendChild(noDataMsg);
                    }

                    if (analysisOutputPre) {
                        analysisOutputPre.appendChild(proposalContainer);
                        const exportBtn = document.getElementById('export-pdf-btn');
                        if(exportBtn) exportBtn.style.display = 'block';
                    }
                } else {
                     if(analysisOutputPre) analysisOutputPre.textContent = 'Received empty results payload.';
                }
                break;
            case 'error':
                if(analysisSpinner) analysisSpinner.style.display = 'none';
                if(progressBar) progressBar.value = 100; 
                const errorDisplayMsg = `Analysis Error: ${eventData.message}`;
                if (analysisOutputPre) {
                    analysisOutputPre.textContent = errorDisplayMsg;
                    if (eventData.details) {
                        analysisOutputPre.textContent += `\n\nDetails: ${eventData.details}`;
                    }
                    analysisOutputPre.style.color = 'red';
                }
                break;
            case 'stream_end': 
                if(analysisSpinner) analysisSpinner.style.display = 'none';
                break;
            default:
                console.warn('Unknown SSE event type:', eventData.type, eventData);
        }
    }
}); 