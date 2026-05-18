import os
import re
from dotenv import load_dotenv

load_dotenv()

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier_env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{name} must be a safe PostgreSQL identifier.")
    return value


def _bounded_int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))

# Server configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# CORS Middleware configuration
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") # Placeholder URL for frontend.

# AI Model configuration
MODEL_NAME = os.getenv("MODEL_NAME", "your-model-name-here")
COPILOT_REASONING_EFFORT = os.getenv("COPILOT_REASONING_EFFORT", "medium").strip().lower()
if COPILOT_REASONING_EFFORT not in {"low", "medium", "high", "xhigh"}:
    COPILOT_REASONING_EFFORT = "medium"
COPILOT_REQUEST_TIMEOUT_SECONDS = int(os.getenv("COPILOT_REQUEST_TIMEOUT_SECONDS", "240"))

# Session management configuration
SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "15"))
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "100"))
MAX_HISTORY_PER_SESSION = int(os.getenv("MAX_HISTORY_PER_SESSION", "200"))
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes", "on")

# SQL allowlist -- comma-separated list of PostgreSQL schemas the agent may query.
# Example: SQL_ALLOWED_SCHEMAS=public,your_gis_schema
SQL_ALLOWED_SCHEMAS = os.getenv("SQL_ALLOWED_SCHEMAS", "")

# Buffer search hardening
BUFFER_DISTANCE_MIN_METERS = int(os.getenv("BUFFER_DISTANCE_MIN_METERS", "10"))
BUFFER_DISTANCE_MAX_METERS = int(os.getenv("BUFFER_DISTANCE_MAX_METERS", "50000"))
BUFFER_RESULT_LIMIT = int(os.getenv("BUFFER_RESULT_LIMIT", "200"))

# Matrikkel / EiendomskartTeig configuration
MATR_EIENDOM_SCHEMA = _safe_identifier_env("MATR_EIENDOM_SCHEMA", "matrikkel_eiendomskartteig")
MATR_ADRESSE_SCHEMA = _safe_identifier_env("MATR_ADRESSE_SCHEMA", "matrikkel_adresse")
MATR_BYGNING_SCHEMA = _safe_identifier_env("MATR_BYGNING_SCHEMA", "matrikkel_bygning")
MATR_EIENDOM_MAX_RADIUS_METERS = _bounded_int_env(
    "MATR_EIENDOM_MAX_RADIUS_METERS",
    5000,
    minimum=1,
    maximum=50000,
)
MATR_EIENDOM_MAX_LIMIT = _bounded_int_env(
    "MATR_EIENDOM_MAX_LIMIT",
    100,
    minimum=1,
    maximum=500,
)
MATR_EIENDOM_QUERY_TIMEOUT_MS = _bounded_int_env(
    "MATR_EIENDOM_QUERY_TIMEOUT_MS",
    15000,
    minimum=1000,
    maximum=60000,
)

# System prompt configuration - define the behavior of the AI assistant
SYSTEM_PROMPT = """
Your system prompt here.
""".strip()

# Azure Blob Storage configuration
AZURE_CONNECTION_STRING = os.getenv("AZURE_CONNECTION_STRING")
BLOB_CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME")


# POSTGRESQL DATABASE URL
DATABASE_URL = os.getenv("DATABASE_URL")

# Search / indexing
# INDEXING_ENABLED=true  -- enable index_document and index_all_documents MCP tools
# GITHUB_MODELS_TOKEN=ghp_...  -- GitHub fine-grained token with 'models:read' scope (for semantic search)
