CREATE TABLE IF NOT EXISTS jobs (
    -- Stable source-specific ID.
    -- Example: reed:54154602
    id TEXT PRIMARY KEY,

    -- Source job board.
    -- Example: reed, indeed, linkedin
    source TEXT NOT NULL,

    -- Original ID supplied by the source.
    source_job_id TEXT NOT NULL,

    -- Public job listing URL.
    url TEXT NOT NULL,

    -- Job information.
    title TEXT,
    company TEXT,
    company_logo_url TEXT,
    location TEXT,

    -- Expected normalized values:
    -- full time
    -- part time
    -- contract
    -- temporary
    work_type TEXT,

    -- Salary information.
    salary_min NUMERIC,
    salary_max NUMERIC,

    -- Expected values:
    -- year
    -- day
    -- hour
    salary_period TEXT,

    -- When the source says the job was posted.
    posted_at TIMESTAMPTZ,

    -- Plain-text job description.
    description TEXT,

    -- Used later for cross-source deduplication.
    canonical_job_id TEXT,

    -- Fingerprint of listing content.
    -- Used to detect content changes.
    content_hash TEXT,

    -- When we last successfully fetched the
    -- full detail page.
    detail_fetched_at TIMESTAMPTZ,

    -- First time our crawler ever observed this listing.
    first_seen_at TIMESTAMPTZ NOT NULL,

    -- Most recent time our crawler observed this
    -- listing as live.
    last_seen_at TIMESTAMPTZ NOT NULL,

    -- NULL means the listing is currently live.
    -- A timestamp means we have confirmed removal.
    removed_at TIMESTAMPTZ
);


-- ---------------------------------------------------------
-- INDEXES
-- ---------------------------------------------------------

-- Helpful for source-specific lookups.
CREATE INDEX IF NOT EXISTS idx_jobs_source
ON jobs (source);


-- Helpful when looking up a source listing.
CREATE INDEX IF NOT EXISTS idx_jobs_source_job_id
ON jobs (source, source_job_id);


-- Helpful for future cross-source deduplication.
CREATE INDEX IF NOT EXISTS idx_jobs_canonical_job_id
ON jobs (canonical_job_id);


-- Helpful when querying live/removed listings.
CREATE INDEX IF NOT EXISTS idx_jobs_removed_at
ON jobs (removed_at);


-- Helpful for detail refresh scheduling.
CREATE INDEX IF NOT EXISTS idx_jobs_detail_fetched_at
ON jobs (detail_fetched_at);