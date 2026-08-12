-- =====================================================
-- IDEAS
-- =====================================================

CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    title TEXT NOT NULL,
    hook TEXT NOT NULL,
    emotion TEXT NOT NULL,
    topic TEXT NOT NULL,

    virality_score REAL NOT NULL,
    confidence_score REAL NOT NULL,

    source_pattern_id INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ideas_virality
ON ideas(virality_score DESC);

CREATE INDEX IF NOT EXISTS idx_ideas_topic
ON ideas(topic);

-- =====================================================
-- JOB QUEUE
-- =====================================================

CREATE TABLE IF NOT EXISTS jobs (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    agent_name TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'pending',

    payload TEXT,

    error TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    started_at TIMESTAMP,

    finished_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_status
ON jobs(status);

CREATE INDEX IF NOT EXISTS idx_jobs_agent
ON jobs(agent_name);

-- =====================================================
-- SCRIPTS
-- =====================================================

CREATE TABLE IF NOT EXISTS scripts (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    idea_id INTEGER NOT NULL,

    title TEXT NOT NULL,

    hook TEXT NOT NULL,

    introduction TEXT NOT NULL,

    body TEXT NOT NULL,

    conclusion TEXT NOT NULL,

    call_to_action TEXT NOT NULL,

    estimated_duration INTEGER NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (idea_id) REFERENCES ideas(id)
);

CREATE INDEX IF NOT EXISTS idx_scripts_idea
ON scripts(idea_id);