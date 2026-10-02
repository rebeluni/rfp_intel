"""
Hash Manifest for Incremental Indexing.
Tracks SHA-256 hashes and associated chunk IDs per document file.
Allows incremental re-indexing by deleting stale chunks when a file changes or is removed.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from config.settings import settings

logger = logging.getLogger(__name__)


class HashManifest:
    """Manages SHA-256 content hashes and chunk IDs for all indexed files."""

    def __init__(self, manifest_path: Optional[Path] = None):
        self.manifest_path = manifest_path or (settings.SEARCH_INDEX_DIR / "manifest.json")
        self.entries: Dict[str, dict] = {}
        self.load()

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute SHA-256 hash of a file's binary content."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                hasher.update(block)
        return hasher.hexdigest()

    def get_file_status(self, file_path: Path) -> str:
        """
        Check whether a file is 'new', 'modified', or 'unchanged'.
        """
        norm_key = str(Path(file_path).resolve())
        if norm_key not in self.entries:
            return "new"

        current_hash = self.compute_file_hash(file_path)
        stored_hash = self.entries[norm_key].get("hash")
        if current_hash != stored_hash:
            return "modified"

        return "unchanged"

    def record_indexed_file(
        self,
        file_path: Path,
        chunk_ids: List[str],
        file_hash: Optional[str] = None
    ) -> List[str]:
        """
        Record a newly indexed or updated file.
        Returns any prior chunk IDs that should be removed from the indices.
        """
        norm_key = str(Path(file_path).resolve())
        old_chunk_ids = self.entries.get(norm_key, {}).get("chunk_ids", [])

        file_hash = file_hash or self.compute_file_hash(file_path)
        mtime = file_path.stat().st_mtime if file_path.exists() else 0.0

        self.entries[norm_key] = {
            "file_name": file_path.name,
            "hash": file_hash,
            "mtime": mtime,
            "chunk_ids": chunk_ids,
        }
        self.save()
        return old_chunk_ids

    def remove_file(self, file_path: Path) -> List[str]:
        """
        Remove a file from the manifest and return its chunk IDs to delete.
        """
        norm_key = str(Path(file_path).resolve())
        if norm_key in self.entries:
            old_chunk_ids = self.entries[norm_key].get("chunk_ids", [])
            del self.entries[norm_key]
            self.save()
            return old_chunk_ids
        return []

    def get_all_indexed_chunks(self) -> Set[str]:
        """Return a set of all chunk IDs currently tracked in the manifest."""
        all_ids = set()
        for entry in self.entries.values():
            all_ids.update(entry.get("chunk_ids", []))
        return all_ids

    def load(self) -> None:
        """Load manifest from JSON file if present."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.entries = data.get("files", {})
                logger.info(f"Loaded hash manifest with {len(self.entries)} tracked files.")
            except Exception as e:
                logger.warning(f"Could not load hash manifest from {self.manifest_path}: {e}")
                self.entries = {}
        else:
            self.entries = {}

    def save(self) -> None:
        """Save manifest to JSON file."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "files": self.entries}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save hash manifest to {self.manifest_path}: {e}")
