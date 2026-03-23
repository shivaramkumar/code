# System Architecture & Multi-Tenant Isolation

The LearnSpace AI Template utilizes a modern, compartmentalized design to demonstrate real-world patterns in LLM-assisted applications.

## Component Breakdown

1. **Frontend Overlay (Architecture Explorer)**:
   The UI includes a specific component that intercepts "Learning Events" emitted by the backend. This allows students and developers to watch HTTP traces, DB queries, and external LLM calls physically animate on screen in real-time as users interact with the main chat.

2. **Semantic Caching Layer (ChromaDB)**:
   - **Performance**: Before hitting an LLM (which is computationally expensive or financially costly), the backend hashes the incoming prompt against a `semantic_cache` vector database.
   - **Isolation**: Search bounds are enforced by a `$eq` filter on `user_id`. A cache hit for User A cannot physically leak into a cache hit for User B, enforcing zero-trust data boundaries.

3. **Dynamic Protocol Tools (MCP)**:
   The default implementation (`retrieve_context`) fetches uploaded documents related to the user's prompt. However, you can register *any* tool dynamically by manipulating the `/api/tools` SQLite REST endpoint. Registered tools get their own dedicated partition within ChromaDB matching the `tool_id` metadata attribute.

4. **Streaming LLM Connector**:
   We utilize `httpx.AsyncClient` to asynchronously stream tokens back from local instances (`Ollama`) or Cloud components (`Azure AI Foundry`). TTFT (Time To First Token) is aggressively measured.
