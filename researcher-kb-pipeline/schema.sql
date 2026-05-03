-- Researcher Intelligence Platform Phase 1 Schema
-- MySQL DDL (InnoDB, utf8mb4)

-- Table: institutions
CREATE TABLE institutions (
    id VARCHAR(128) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(64) NOT NULL,
    region VARCHAR(64),
    h_index INT DEFAULT 0 NOT NULL,
    total_citations BIGINT DEFAULT 0 NOT NULL,
    prestige_tier TINYINT,
    is_ivy_league BOOLEAN DEFAULT FALSE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    INDEX idx_institutions_country (country),
    INDEX idx_institutions_prestige_tier (prestige_tier),
    INDEX idx_institutions_ivy_league (is_ivy_league)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: researchers
CREATE TABLE researchers (
    id VARCHAR(128) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    total_works INT DEFAULT 0 NOT NULL,
    total_citations BIGINT DEFAULT 0 NOT NULL,
    h_index INT DEFAULT 0 NOT NULL,
    i10_index INT DEFAULT 0 NOT NULL,
    career_start_year SMALLINT,
    years_active SMALLINT,
    last_author_ratio_recent DOUBLE,
    industry_collaboration_score DOUBLE,
    quality_score DOUBLE,
    recency_score DOUBLE,
    seniority_score DOUBLE,
    current_institution_id VARCHAR(128),
    country VARCHAR(64),
    last_updated DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (current_institution_id) REFERENCES institutions(id) ON DELETE SET NULL,
    INDEX idx_researchers_h_index (h_index),
    INDEX idx_researchers_total_citations (total_citations),
    INDEX idx_researchers_quality_score (quality_score),
    INDEX idx_researchers_institution (current_institution_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: papers
CREATE TABLE papers (
    id VARCHAR(128) PRIMARY KEY,
    researcher_id VARCHAR(128) NOT NULL,
    title VARCHAR(512) NOT NULL,
    year SMALLINT NOT NULL,
    venue VARCHAR(255),
    venue_type ENUM('conference','journal','other') NOT NULL,
    citations BIGINT DEFAULT 0 NOT NULL,
    concept VARCHAR(128),
    abstract TEXT,
    embedding_id VARCHAR(128),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (researcher_id) REFERENCES researchers(id) ON DELETE CASCADE,
    INDEX idx_papers_researcher (researcher_id),
    INDEX idx_papers_year (year),
    INDEX idx_papers_venue_type (venue_type),
    INDEX idx_papers_concept (concept),
    INDEX idx_papers_concept_year (concept, year),
    UNIQUE INDEX idx_papers_embedding_id (embedding_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: researcher_topics
CREATE TABLE researcher_topics (
    researcher_id VARCHAR(128) NOT NULL,
    topic VARCHAR(128) NOT NULL,
    subfield VARCHAR(128),
    field VARCHAR(128),
    domain VARCHAR(128),
    paper_count INT DEFAULT 0 NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (researcher_id, topic),
    FOREIGN KEY (researcher_id) REFERENCES researchers(id) ON DELETE CASCADE,
    INDEX idx_topics_field (field),
    INDEX idx_topics_subfield (subfield),
    INDEX idx_topics_topic (topic)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: researcher_collaborations
CREATE TABLE researcher_collaborations (
    researcher_id VARCHAR(128) NOT NULL,
    collaborator_name VARCHAR(255) NOT NULL,
    collaborator_type ENUM('industry','academia') NOT NULL,
    shared_papers INT DEFAULT 0 NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (researcher_id, collaborator_name, collaborator_type),
    FOREIGN KEY (researcher_id) REFERENCES researchers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
