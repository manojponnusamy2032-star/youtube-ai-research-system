# Knowledge Brain (Obsidian Vault)

The Knowledge Brain is an Obsidian-compatible knowledge layer that stores structured Markdown notes in a configurable vault directory. It provides a human-readable long-term knowledge interface while the application owns generation, indexing, and automation logic.

## Architecture

```
Database (SQLite)          Obsidian Vault (Markdown)
=================          ==========================
- job status               - knowledge
- IDs                      - explanations
- queues                   - research
- render state             - insights
- execution state          - decisions
                           - lessons
                           - architecture understanding
```

The database remains the source of truth for transactional application state. The Obsidian vault is the human-readable knowledge layer.

## Vault Structure

```
obsidian_vault/
├── 00_Inbox/
├── 01_Projects/
├── 02_Knowledge/
├── 03_Research/
├── 04_Insights/
├── 05_Decisions/
├── 06_Lessons/
├── 07_Sources/
└── 99_Index/
```

## Configuration

Set the vault path via environment variable:

```env
KNOWLEDGE_VAULT_PATH="data/obsidian_vault"
```

If not set, the default is `data/obsidian_vault` relative to the project root. The vault is created automatically on first use.

## Note Types

| Type | Folder | Description |
|------|--------|-------------|
| `concept` | `02_Knowledge` | Reusable concepts and ideas |
| `project` | `01_Projects` | Project overviews with status, architecture, decisions |
| `research` | `03_Research` | Research findings with topic, source, confidence |
| `insight` | `04_Insights` | Reusable insights and patterns |
| `decision` | `05_Decisions` | Architecture/technical decisions with context and rationale |
| `lesson` | `06_Lessons` | Lessons learned with problem, root cause, solution |
| `source` | `07_Sources` | External sources and references |

## Note Format

Every note uses YAML frontmatter and standard Markdown:

```markdown
---
id: knowledge-rag-001
type: concept
title: Retrieval Augmented Generation
created_at: 2026-08-18T00:00:00
updated_at: 2026-08-18T00:00:00
tags:
  - ai
  - llm
  - rag
source: generated
---

# Retrieval Augmented Generation

...

## Related

- [[Embeddings]]
- [[Vector Databases]]
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/knowledge/notes` | Create a knowledge note |
| GET | `/api/knowledge/notes/{id}` | Get a note by ID |
| PUT | `/api/knowledge/notes/{id}` | Update a note |
| DELETE | `/api/knowledge/notes/{id}` | Delete a note |
| GET | `/api/knowledge/search` | Search notes (title, content, tags, type, project) |
| POST | `/api/knowledge/index` | Build vault index (types, tags, links, backlinks, graph) |
| POST | `/api/knowledge/insights` | Capture an insight |
| POST | `/api/knowledge/decisions` | Capture a decision |
| POST | `/api/knowledge/lessons` | Capture a lesson |
| POST | `/api/knowledge/extract` | Extract knowledge from research analysis batch |
| GET | `/api/knowledge/retrieve` | Retrieve relevant knowledge with ranked scoring |
| GET | `/api/knowledge/notes/{id}/related` | Get notes related to a given note |
| GET | `/api/knowledge/notes/{id}/backlinks` | Get backlinks for a note |
| POST | `/api/knowledge/context` | Build a categorized context bundle for an AI agent |

## Knowledge Retrieval Layer

The `KnowledgeRetriever` (`src/knowledge/retriever.py`) provides ranked retrieval of knowledge notes with transparent scoring, graph expansion, context building, and conflict detection.

### Retrieval Methods

| Method | Description |
|--------|-------------|
| `retrieve(query, ...)` | Retrieve relevant notes with ranked scoring |
| `retrieve_related(note_id, ...)` | Retrieve notes related via wikilinks, backlinks, relationships |
| `retrieve_backlinks(note_id, ...)` | Retrieve notes that link to a given note |
| `retrieve_project(project_id, ...)` | Retrieve all knowledge for a project |
| `retrieve_by_type(note_type, ...)` | Retrieve notes of a specific type |
| `retrieve_by_tags(tags, ...)` | Retrieve notes matching any of the given tags |
| `build_context(query, ...)` | Build a categorized context bundle for an AI agent |

### Ranking Algorithm (Transparent, Deterministic)

| Match Type | Score |
|------------|-------|
| Exact title match | +100 |
| Title token match (per token, max 3) | +40 |
| Alias match | +25 |
| Tag match | +30 |
| Content match | +20 |
| Same project | +15 |
| High confidence (>=0.90) | +10 |
| Source available (non-generated) | +10 |

Confidence and source are **boosts only** — they do not qualify a note as a match. A note must match the query through title, tags, or content to be returned.

### Graph Expansion

After finding the strongest direct matches, the retriever optionally expands through:
- Wikilinks in note content
- `related` frontmatter fields
- Typed relationships from the knowledge graph
- Backlinks (notes that link to the result)

Expansion is limited to 5 additional notes to prevent context explosion.

### Context Builder

The `build_context()` method produces a `KnowledgeContext` with:
- **Relevant Knowledge** — top-ranked notes
- **Evidence** — research notes
- **Lessons** — lesson notes
- **Decisions** — decision notes
- **Project Context** — project notes
- **Conflicts** — detected `contradicts` relationships

The context is rendered as compact Markdown for agent prompts, with size limits to prevent token overflow.

### Conflict Detection

When retrieved notes contain `contradicts` relationships, the context builder explicitly identifies the conflict with both notes' confidence scores. Conflicting knowledge is never silently merged.

### Source Traceability

Every `RetrievedKnowledge` item preserves:
- `note_id`, `title`, `note_type`
- `confidence`, `source`, `project`
- `source_video_ids`, `source_id`, `source_type`
- `match_reasons` (why the note was retrieved)
- `expanded_from` (if added via graph expansion)

## Integration with Existing Agents

The `KnowledgeBaseAgent` now writes structured pattern insights to the Obsidian vault when a pattern report is generated. This happens automatically during the research workflow.

The `AnalysisAgent` is integrated with the `KnowledgeRetriever` as a reference implementation. Before each transcript analysis, the agent retrieves prior knowledge from the vault and injects it as context into the LLM prompt, creating a closed learning loop:

```
Transcript → Knowledge Retrieval → LLM Analysis → Knowledge Extraction → Obsidian
```

## How to Open the Vault in Obsidian

1. Open Obsidian
2. Click "Open folder as vault"
3. Select the vault directory (e.g., `data/obsidian_vault`)
4. Browse the notes

## How Knowledge Flows

```
Research
    ↓
Transcript
    ↓
AI Analysis
    ↓
Pattern Extraction
    ↓
Knowledge Brain (SQLite + Obsidian)
    ↓
Obsidian Markdown
```

## Creating New Knowledge Types

To add a new note type:

1. Add the type to `NoteType` enum in `src/knowledge/models.py`
2. Add the folder mapping in the `folder` property
3. Add a template in `src/knowledge/templates/`
4. Add a capture method in `KnowledgeService` if needed
