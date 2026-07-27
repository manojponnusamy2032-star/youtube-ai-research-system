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
└── main.py          # Application entry point

data/
└── database/        # SQLite database files

tests/               # Unit and integration tests
```

## Installation

```bash
# Clone the repository
git clone https://github.com/manojponnusamy2032-star/youtube-ai-research-system.git
cd youtube-ai-research-system

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Set the required environment variable:

```bash
# Windows (PowerShell)
$env:YOUTUBE_API_KEY = "your-api-key-here"

# Windows (CMD)
set YOUTUBE_API_KEY=your-api-key-here

# Linux/Mac
export YOUTUBE_API_KEY=your-api-key-here
```

Or create a `.env` file in the project root:

```
YOUTUBE_API_KEY=your-api-key-here
DATABASE_PATH=data/database/youtube.db
DEFAULT_MAX_RESULTS=50
LOG_LEVEL=INFO
```

## Usage

### Run the Collector Agent

```bash
python src/main.py
```

This will start an interactive CLI menu where you can:
1. Collect videos for a single keyword
2. Collect videos for multiple keywords (batch mode)
3. View database statistics
4. Exit the application

### Example Output

```
-------------------------------------
YAIRS Collector Agent
-------------------------------------

Searching keyword:
psychology

Found:
50 videos

New:
48

Skipped:
2 duplicates

Database updated successfully.
```

## Architecture

### Video Model (`src/models/video.py`)
Pydantic model representing YouTube video metadata with validation.

### YouTube Service (`src/services/youtube_service.py`)
- Handles YouTube Data API v3 interactions
- Implements retry logic with exponential backoff
- Parses API responses into Video models

### Database Service (`src/database/database_service.py`)
- SQLite database management
- Automatic schema creation
- Duplicate detection based on video_id
- Batch insertion support

### Collector Agent (`src/agents/collector_agent.py`)
- Orchestrates the collection workflow
- Dependency injection for services
- Rich terminal output
- Comprehensive error handling

## Development

### Run Tests

```bash
pytest tests/ -v
```

### Code Formatting

```bash
black src/ tests/
```

### Type Checking

```bash
mypy src/
```

### Linting

```bash
flake8 src/ tests/
```

## Requirements

- Python 3.13+
- YouTube Data API v3 key ([Get one here](https://console.cloud.google.com/apis/credentials))

## License

MIT License

## Contributing

Contributions are welcome! Please read the contributing guidelines before submitting PRs.