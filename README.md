# Proposal Analyzer

This is a web-based tool to analyze PDF proposal documents. You can upload a proposal, and the tool will provide several types of analysis using large language models.

## Features

*   **PDF Proposal Upload**: Upload a proposal document in PDF format.
*   **Question Answering**: Ask questions about the content of the proposal.
*   **Spell Checker**: Performs spelling and grammar checking on the proposal text. It is optimized to handle text extracted from PDFs, which may contain artifacts like hyphenation errors.
*   **Expert Reviewer Feedback**: Generates feedback on the proposal from the perspective of an expert reviewer, highlighting strengths and weaknesses.
*   **Export to PDF**: The analysis results can be downloaded as a PDF report.

## Setup and Usage

### Prerequisites

*   Python 3.7+
*   pip

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <repository-folder>
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up your OpenAI API Key:**
    This project uses the OpenAI API. You need to have an API key from OpenAI.

    Create a file named `.env` in the root of the project and add your API key like this:
    ```
    OPENAI_API_KEY="your-openai-api-key"
    ```
    The application uses `python-dotenv` to load this key automatically.

### Running the Application

Once the setup is complete, you can run the application using Flask:

```bash
flask run
```

Or by directly running `app.py`:

```bash
python app.py
```

Open your web browser and go to `http://127.0.0.1:5000` to use the tool. 