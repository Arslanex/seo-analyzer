"""SQLite schema (MVP subset of belge 04). Findings/scores are append-only by convention."""

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS audits (
  id TEXT PRIMARY KEY,
  mode TEXT NOT NULL CHECK (mode IN ('site','page')),
  target_url TEXT NOT NULL,
  final_origin TEXT,
  status TEXT NOT NULL CHECK (status IN ('queued','running','partial','completed','failed','canceled')),
  business_type TEXT,
  lang TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT,
  rule_version TEXT NOT NULL DEFAULT '1.0',
  score_version TEXT NOT NULL DEFAULT 'mvp-0.1',
  parent_audit_id TEXT,
  sample_seed INTEGER,
  options TEXT NOT NULL DEFAULT '{}',
  coverage TEXT NOT NULL DEFAULT '{}',
  budget TEXT NOT NULL DEFAULT '{}',
  cost TEXT NOT NULL DEFAULT '{}',
  scores TEXT,
  synthesis TEXT,
  error TEXT,
  cancel_requested INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_stages (
  audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT, finished_at TEXT, detail TEXT,
  PRIMARY KEY (audit_id, stage)
);
CREATE TABLE IF NOT EXISTS audit_pages (
  id TEXT PRIMARY KEY,
  audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  final_url TEXT, status INTEGER, sample_kind TEXT NOT NULL DEFAULT 'core',
  template_key TEXT, html_bytes INTEGER, ttfb_ms INTEGER, error TEXT,
  rendered INTEGER NOT NULL DEFAULT 0, is_spa INTEGER, js_gap TEXT,
  title TEXT, word_count INTEGER, page_score REAL, body_ref TEXT,
  UNIQUE (audit_id, url)
);
CREATE TABLE IF NOT EXISTS findings (
  rowid_ INTEGER PRIMARY KEY AUTOINCREMENT,
  audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  check_id TEXT NOT NULL, severity TEXT NOT NULL, category TEXT NOT NULL, layer TEXT NOT NULL,
  url TEXT, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS findings_audit ON findings(audit_id, severity);
CREATE TABLE IF NOT EXISTS not_checked (
  audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  check_id TEXT NOT NULL, reason_code TEXT NOT NULL, url TEXT
);
CREATE TABLE IF NOT EXISTS advisory (
  audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, page_url TEXT, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS advice (
  audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  finding_id TEXT NOT NULL, url TEXT, text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL, data TEXT NOT NULL,
  PRIMARY KEY (audit_id, seq)
);
CREATE TABLE IF NOT EXISTS audit_data (
  audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,  -- links | perf | indexability | visibility | gsc | field (validated in code)
  data TEXT NOT NULL,
  PRIMARY KEY (audit_id, kind)
);
CREATE TABLE IF NOT EXISTS site_profiles (
  host TEXT PRIMARY KEY,  -- lower-case, without www.
  keywords TEXT NOT NULL DEFAULT '[]',
  competitors TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS qa (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  question TEXT NOT NULL, answer TEXT NOT NULL, created_at TEXT NOT NULL
);
"""
