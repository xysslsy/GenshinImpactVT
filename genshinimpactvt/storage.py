"""Small transactional local bookmark and browsing-history store."""
import sqlite3
from pathlib import Path

class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL,
                visited_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        ''')
        self.db.commit()

    def bookmark(self, url, title):
        with self.db:
            self.db.execute('INSERT INTO bookmarks(url,title) VALUES(?,?) ON CONFLICT(url) DO UPDATE SET title=excluded.title', (url, title))

    def visit(self, url, title):
        with self.db:
            self.db.execute('INSERT INTO history(url,title) VALUES(?,?)', (url, title))

    def rows(self, kind):
        if kind not in ('bookmarks', 'history'):
            raise ValueError('invalid list')
        return self.db.execute(f'SELECT id,title,url FROM {kind} ORDER BY id DESC LIMIT 500').fetchall()

    def delete(self, kind, row_id):
        if kind not in ('bookmarks', 'history'):
            raise ValueError('invalid list')
        with self.db:
            self.db.execute(f'DELETE FROM {kind} WHERE id=?', (row_id,))

    def close(self):
        self.db.close()
