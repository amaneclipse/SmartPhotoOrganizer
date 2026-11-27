"""SQLite cache and operation journal."""
import json
import sqlite3
from pathlib import Path
from app.models import ClassificationResult, ImageRecord

class Repository:
    def __init__(self, database_path: Path):
        self.connection = sqlite3.connect(database_path); self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("CREATE TABLE IF NOT EXISTS images(path TEXT PRIMARY KEY,size INTEGER NOT NULL,modified_at REAL NOT NULL,width INTEGER,height INTEGER,format TEXT,sha256 TEXT,phash TEXT,metadata TEXT,category TEXT,subcategory TEXT,source TEXT,confidence REAL,tags TEXT,analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS operations(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,destination TEXT NOT NULL,action TEXT NOT NULL,status TEXT NOT NULL,error TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);"); self.connection.commit()
    def save_analysis(self, record: ImageRecord, result: ClassificationResult) -> None:
        self.connection.execute("""INSERT INTO images(path,size,modified_at,width,height,format,sha256,phash,metadata,category,subcategory,source,confidence,tags) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET size=excluded.size,modified_at=excluded.modified_at,width=excluded.width,height=excluded.height,format=excluded.format,metadata=excluded.metadata,category=excluded.category,subcategory=excluded.subcategory,source=excluded.source,confidence=excluded.confidence,tags=excluded.tags,analyzed_at=CURRENT_TIMESTAMP""", (str(record.path), record.size, record.modified_at, record.width, record.height, record.format, record.sha256, record.phash, json.dumps(record.metadata, ensure_ascii=False), result.category, result.subcategory, result.source, result.confidence, json.dumps(result.tags, ensure_ascii=False))); self.connection.commit()
    def log_operation(self, source: Path, destination: Path, action: str, status: str, error: str = "") -> None:
        self.connection.execute("INSERT INTO operations(source,destination,action,status,error) VALUES(?,?,?,?,?)", (str(source), str(destination), action, status, error)); self.connection.commit()
    def close(self) -> None: self.connection.close()
