# YouTube AI Research System (YAIRS)

A production-quality Python system for collecting and analyzing YouTube video metadata using AI.

## Features

- **Collector Agent**: Search YouTube and collect video metadata
- **Pydantic Models**: Type-safe data validation
- **SQLite Database**: Persistent storage with duplicate detection
- **Rich CLI**: Beautiful terminal interface
- **Production Ready**: Logging, error handling, retry logic

## Project Structure

```
src/
├── agents/           # AI agents (Collector, Transcript, Analysis)
├── services/         # External service integrations (YouTube, AI, Database)
├── models/           # Pydantic data models
├── database/         # Database service and migrations
├── utils/            # Utilities (logger, config, helpers)
├── prompts/          # AI prompt templates
└── main.py           # Application entry point

data/
└── database/         # SQLite database files

frontend/             # Frontend app (Next.js)

tests/                # Unit and integration tests
```

## Prerequisites

- Python 3.13 or newer
- Node.js and npm (for frontend)
- SQLite (bundled with Python — no separate server required)

## Installation

```bash
# Clone the repository
git clone https://github.com/manojponnusamy2032-star/youtube-ai-research-system.git
cd youtube-ai-research-system

# Create and activate a Python virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt
```

## Environment Setup

1. Copy the example env file and edit values:

```bash
cp .env.example .env
# or on Windows (PowerShell):
# copy .env.example .env
```

2. Open `.env` and provide real values for:
- `YOUTUBE_API_KEY` — required for collector functionality
- `API_KEY` — optional API key to protect the backend
- `OLLAMA_BASE_URL` / `OLLAMA_MODEL` — if using Ollama for LLMs
- `NEXT_PUBLIC_API_BASE` — frontend API base (e.g. http://localhost:8000)

See `.env.example` for all supported variables and safe placeholders.

## Run Backend

From the project root (with your virtualenv activated):

```bash
# Start the FastAPI backend (development with auto-reload)
python -m uvicorn src.api.app:app --reload
```

API docs will be available at http://127.0.0.1:8000/docs by default.

## Run Frontend

The frontend lives in `frontend/`. Install dependencies and run the dev server:

```bash
cd frontend
npm install
# Development server (if available)
npm run dev
# Build for production
npm run build
```

The frontend uses `NEXT_PUBLIC_API_BASE` to locate the backend API — update it in `.env` if needed.

## Run Tests

Unit and integration tests can be executed with pytest:

```bash
pytest tests/ -v
```

## Additional Notes

- Use `.env.example` as the starting point for environment variables.
- Keep API keys and secrets out of source control — add `.env` to `.gitignore`.
- For backend debugging the project exposes a FastAPI app at `src.api.app:create_app` and can be started with uvicorn as shown above.

## License

MIT License

## Contributing

Contributions are welcome! Please open issues or pull requests and follow the repository's contribution guidelines.
