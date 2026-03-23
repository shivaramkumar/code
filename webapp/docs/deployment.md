# Cloud CI/CD & Dependencies

## Tooling Migration with `uv`
The application dependencies are exclusively managed by [uv](https://github.com/astral-sh/uv), an extremely fast Python package and project manager written in Rust.

- **Files**: The canonical definition lives in `backend/pyproject.toml`.
- **Syncing**: To sync your local `.venv`, execute `uv pip install -e .` from within the `./backend` directory.
- **Linters**: Format checking (`black`), syntax linting (`ruff`), and code modernization (`pyupgrade`) are enforced via local git scripts defined in `.pre-commit-config.yaml`.

## Azure Pipelines
The project root contains `azure-pipelines.yml`. 

### Pipeline Behavior:
1. Evaluates your repository on every push to `main`.
2. Downloads and installs the latest stable release of `uv`.
3. Validates the Python dependency graphs inside an ephemeral virtual environment by processing `backend/pyproject.toml`.
4. Executes `uv pip compile pyproject.toml -o requirements.txt`. This step is crucial because the underlying Azure Functions Python Worker engine inherently looks for a `requirements.txt` file when spinning up cloud instances via Serverless ZipDeploy APIs.
5. Archives the result, and signals an `AzureFunctionApp@2` resource connection to mount your zipped artifact live to Azure!
