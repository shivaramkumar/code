# LearnSpace AI Template 🎓

Welcome to the **LearnSpace AI Template**, a modern, educational web application designed to demonstrate advanced AI concepts including Semantic Caching, dynamic Tool Registration (MCP), and Multi-Tenant Vector Database partitioning. The entire application is built to be easily understandable, rendering real-time backend execution flows directly in the frontend UI!

## 🚀 Key Features

*   **Dynamic Data Flow Visualization**: The frontend features an "Architecture Explorer" that traces and logs every step the backend takes (Cache Hits, Tool Executions, LLM TTFT) in real-time.
*   **Multi-Tenant Vector Isolation**: ChromaDB is strictly partitioned by `user_id` and `tool_id`, ensuring completely siloed knowledge graphs for different users and active tools.
*   **REST-based Tool Registry**: Say goodbye to hardcoded tool lists! The platform hosts a dynamic REST API (`/api/tools`) backed by SQLite to register, list, and assign modular tools on the fly.
*   **Cloud-Native Serverless**: The backend is powered by **FastAPI** but structurally wrapped to seamlessly deploy directly to **Azure Functions** serverless environments.
*   **Modern Python Tooling**: Dependencies are blisteringly fast, managed entirely by `uv` using a modern `pyproject.toml`. Code quality is strictly enforced via `pre-commit` hooks (Black, Ruff, PyUpgrade).
*   **Zero-Build Frontend**: A beautiful glassmorphism vanilla JS/HTML frontend that requires absolutely no `npm build` steps, perfect for instant tinkering.

---

## 🛠 Tech Stack

*   **Frontend**: Vanilla HTML5, CSS3 (Glassmorphism), JavaScript
*   **Backend**: Python 3.11+, FastAPI, SQLite (`db/models.py`)
*   **Vector Database**: ChromaDB (Persistent File Storage)
*   **AI Integrations**: Native support for local Ollama models (default: `llama3.2:3b`) or Azure Foundry API.
*   **CI/CD**: Fully configured `azure-pipelines.yml` and `pre-commit` workflows.

---

## ⚙️ Getting Started locally

### 1. Prerequisites
You need Python 3.11+ and the blazingly fast `uv` package manager installed.
```bash
# Install uv (macOS / Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Environment Setup
Clone the repository and jump into the `backend/` directory to sync dependencies.
```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -e .
```

*Optional: Initialize code quality git-hooks*
```bash
pre-commit install
```

### 3. Running the Server
Ensure you have an LLM running locally (e.g., `ollama run llama3.2:3b`), then spin up the FastAPI server:
```bash
uvicorn main:app --reload --port 8000
```
**Open your browser to:** `http://localhost:8000`

---

## 🏗 Architecture & Educational Flow

When you send a message via the frontend, watch the **Architecture Explorer** panel! Here is what happens under the hood:
1.  **Frontend**: Captures the prompt, selected User Profile, and chosen Tool Scope.
2.  **Semantic Cache**: Queries `ChromaDB` explicitly bounding the search to the active `user_id`. If a direct contextual match is found (`> 0.9` similarity), the LLM is bypassed entirely (Cache HIT!).
3.  **MCP Tools**: If `use_context` is enabled, the backend searches ChromaDB for uploaded knowledge strictly partitioned to the specific `tool_id` in use.
4.  **LLM Provider**: The isolated context and prompt are streamed to Ollama, measuring Time-To-First-Token (TTFT) metrics.

You can freely register new tools and upload `.txt`/`.pdf` files for different users to test how strictly the Vector Database segregates knowledge!

---

## 🐳 Docker Deployment

You can seamlessly package the entire application (both backend and zero-build frontend) into a unified Docker container.

### 1. Build the Image
To build the image, run the following command at the root of the repository. **Make sure to include the trailing `.`** to specify the current directory as the build context!
```bash
docker build -t learnspace-ai .
```

### 2. Run the Container
Spin up the container and map port 8000:
```bash
docker run -p 8000:8000 learnspace-ai
```
The application will be instantly available at `http://localhost:8000`.

---

## ☁️ Deployment (Azure CI/CD)
The repository includes an `azure-pipelines.yml`. When merged to `main`, Azure DevOps will:
1. Spin up an Ubuntu runner.
2. Quickly resolve your `pyproject.toml` dependencies via `uv`.
3. Compile a frozen `requirements.txt` specifically for the Azure Python Worker environment.
4. Zip the deployment and push it directly to your `AzureFunctionApp` configuration.
