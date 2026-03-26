# REST API Reference

The backend utilizes `FastAPI` to expose the following capabilities:

## `GET /api/config`
Fetches the `config.json` deployment rules, enabling the frontend to dynamically brand the UI application template and load the appropriate configuration variables like `app_name` and `theme`.

## `/api/tools` (MCP Toolkit)
- **`GET /api/tools`**: Returns the list of active tools from the SQLite registry. Let's the UI populate available domains.
- **`POST /api/tools`**: Registers a new dynamic tool (`ToolCreate` schema). Requires `name` and `description`, accepts optional `api_endpoint` URL. Returns HTTP 400 if the tool ID already exists.
- **`DELETE /api/tools/{id}`**: Destroys the configured tool from the database.

## `/api/context`
- **`POST /api/context/upload`**: Translates and indexes an uploaded file (`.txt`, `.pdf`) directly into ChromaDB vector embeddings. **Must include `user_id` and `tool_id` in the Form Data** to correctly bind the knowledge to the active semantic partition.

## `/api/ai`
- **`POST /api/ai/chat`**: The primary execution loop simulating the AI interaction. Accepts a JSON payload containing the prompt message, target `user_id`, and targeted `tool_id`. Returns a JSON packet containing the generated `.response`, the execution `.events` timeline, and `.source` tagging indicating cache utilization.
