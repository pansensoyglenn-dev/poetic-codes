CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  date TEXT NOT NULL,
  content_type TEXT NOT NULL DEFAULT 'text',
  body TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  photo_url TEXT,
  video_url TEXT,
  github_url TEXT,
  page_url TEXT,
  deploy_status TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date DESC, id DESC);
