import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from genshinimpactvt.storage import Store
from genshinimpactvt.urls import normalize_url

class CoreTests(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(normalize_url('example.com/a'), 'https://example.com/a')
        for bad in ('', 'file:///x', 'javascript:alert(1)', 'https://has space'):
            with self.subTest(bad=bad), self.assertRaises(ValueError): normalize_url(bad)
    def test_storage_restart_and_delete(self):
        with self.subTest('persistent database'):
            path = Path(__file__).resolve().parents[1]/'test-local.sqlite3'; path.unlink(missing_ok=True); self.addCleanup(path.unlink, missing_ok=True); db = Store(path)
            db.bookmark('https://example.com','A'); db.bookmark('https://example.com','B'); db.visit('https://example.com','A'); db.close()
            db = Store(path); self.assertEqual(db.rows('bookmarks')[0][1], 'B'); self.assertEqual(len(db.rows('history')), 1)
            db.delete('history', db.rows('history')[0][0]); self.assertEqual(db.rows('history'), []); self.assertEqual(len(db.rows('bookmarks')), 1); db.close()

if __name__ == '__main__': unittest.main()
