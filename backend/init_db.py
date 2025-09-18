import sqlite3
import os

BASE = os.path.dirname(__file__)
DB = os.path.join(BASE, 'data.db')

schema = """
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  summary TEXT,
  link TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TEXT
);
"""

seed_projects = [
    ('SM Implementation: Example 1', 'Short summary describing the project, contents, and results.', ''),
    ('SM Simulation & Diagrams', 'Includes diagrams, state machine definitions and code samples.', ''),
    ('Paper: Implementation of SM', 'PDF and source code demonstrating the method.', '')
]

def init():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.executescript(schema)
    c.executemany("INSERT INTO projects (title, summary, link) VALUES (?, ?, ?)", seed_projects)
    conn.commit()
    conn.close()
    print("Database created and seeded at", DB)

if __name__ == '__main__':
    init()
