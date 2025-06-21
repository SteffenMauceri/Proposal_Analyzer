# Proposal Analyzer

This is a web-based tool to analyze PDF proposal documents. You can upload a proposal, and the tool will provide several types of analysis using large language models.

## Features

*   **PDF Proposal Upload**: Upload a proposal document in PDF format.
*   **Question Answering**: Ask questions about the content of the proposal.

*   **Expert Reviewer Feedback**: Generates feedback on the proposal from the perspective of an expert reviewer, highlighting strengths and weaknesses.
*   **Export to PDF**: The analysis results can be downloaded as a PDF report.

## Setup and Usage

### Prerequisites

*   Python 3.7+
*   pip or conda

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <repository-folder>
    ```

2.  **Create and activate a virtual environment:**
    
    **Option A: Using conda (recommended):**
    ```bash
    conda create --name proposal_analyzer python=3.9 -y
    conda activate proposal_analyzer
    ```
    
    **Option B: Using venv:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up your LLM Provider:**
    This project supports both OpenAI and local LLM providers.

    ### Option A: OpenAI (Default)
    You need to have an API key from OpenAI.

    **Environment Variable (recommended for production):**
    ```bash
    export OPENAI_API_KEY="your-openai-api-key"
    ```
    
    **.env file:**
    Create a file named `.env` in the root of the project and add your API key:
    ```
    OPENAI_API_KEY="your-openai-api-key"
    ```
    
    **Text file:**
    Create a file named `key.txt` in the root of the project with your API key.

    ### Option B: Local LLM
    You can use a local LLM server (e.g., Ollama, vLLM, or other OpenAI-compatible API).

    **Environment Variables:**
    ```bash
    export LLM_PROVIDER="local"
    export LOCAL_LLM_BASE_URL="https://your-local-llm-server.com/v1"
    export LOCAL_LLM_API_KEY="your-local-api-key"
    export LOCAL_LLM_MODEL="your-model-name"
    export LOCAL_LLM_VERIFY_SSL="false"  # Set to true if using HTTPS with valid certificates
    ```

    **Command Line Options:**
    You can also specify the provider via command line:
    ```bash
    python main.py --llm-provider=local --local-llm-url="https://your-server.com/v1" --local-llm-model="gemma3:27b-it-qat"
    ```

    **Example: NASA JPL Local LLM Setup:**
    ```bash
    export LLM_PROVIDER="local"
    export LOCAL_LLM_BASE_URL="https://chathpc.jpl.nasa.gov/ollama/v1"
    export LOCAL_LLM_API_KEY="sk-c4c4a140130d4e5881765751f2382191"
    export LOCAL_LLM_MODEL="gemma3:27b-it-qat"
    export LOCAL_LLM_VERIFY_SSL="false"
    ```

    **Testing Local LLM:**
    Use the provided test script to verify your local LLM setup:
    ```bash
    python test_local_llm.py
    ```

    **Command Line Examples:**
    ```bash
    # Use local LLM for analysis
    python main.py --llm-provider=local --analyze-proposal --reviewer-feedback
    
    # Use OpenAI (default)
    python main.py --llm-provider=openai --analyze-proposal --reviewer-feedback
    
    # Override local LLM settings via command line
    python main.py --llm-provider=local \
      --local-llm-url="https://chathpc.jpl.nasa.gov/ollama/v1" \
      --local-llm-model="gemma3:27b-it-qat" \
      --local-llm-api-key="your-key" \
      --analyze-proposal
    ```

### Running the Application

Once the setup is complete, you can run the application:

**Using conda environment:**
```bash
conda activate proposal_analyzer
python app.py
```

**Using Flask directly:**
```bash
flask run
```

Open your web browser and go to `http://127.0.0.1:5000` to use the tool.

## Deployment on Render.com

This application is configured for easy deployment on [Render.com](https://render.com). Render is a cloud platform that provides free hosting for web applications.

### Quick Deploy to Render

1. **Fork or clone this repository** to your GitHub account.

2. **Sign up for Render.com** at [render.com](https://render.com) (free account).

3. **Connect your GitHub account** to Render.

4. **Create a new Web Service:**
   - In your Render dashboard, click "New +" → "Web Service"
   - Connect your repository
   - Configure the service:
     - **Name**: `proposal-analyzer` (or your preferred name)
     - **Language**: Python 3
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `gunicorn app:app`
     - **Plan**: Free (or upgrade as needed)

5. **Set Environment Variables:**
   - In the Render dashboard, go to your service → "Environment" tab
   - Add your environment variables:
     ```
     OPENAI_API_KEY=your-openai-api-key-here
     FLASK_ENV=production
     FLASK_DEBUG=false
     ```

6. **Deploy:**
   - Click "Create Web Service"
   - Render will automatically build and deploy your application
   - Your app will be available at `https://your-service-name.onrender.com`

### Alternative: Deploy using render.yaml

This repository includes a `render.yaml` file for Infrastructure as Code deployment:

1. **Push the `render.yaml` file** to your repository.
2. **In Render dashboard**, click "New +" → "Blueprint"
3. **Connect your repository** and Render will automatically detect the `render.yaml` configuration.
4. **Set the `OPENAI_API_KEY`** environment variable in the dashboard.

### Important Notes for Render Deployment

- **Free Tier Limitations**: Render's free tier puts services to sleep after 15 minutes of inactivity. The first request after sleeping may take 30-60 seconds to respond.
- **Environment Variables**: Never commit your OpenAI API key to the repository. Always set it as an environment variable in the Render dashboard.
- **File Uploads**: Uploaded files are stored temporarily and will be lost when the service restarts. For production use, consider integrating with cloud storage (AWS S3, etc.).
- **Persistent Storage**: The free tier doesn't include persistent storage. Files uploaded during a session will be lost when the service restarts.

### Render Deployment Troubleshooting

If you encounter issues:

1. **Check the build logs** in the Render dashboard
2. **Verify all environment variables** are set correctly
3. **Ensure your `requirements.txt`** includes all dependencies
4. **Check Python version compatibility** (the app uses Python 3.9+)

For support, check the Render documentation at [render.com/docs](https://render.com/docs). 