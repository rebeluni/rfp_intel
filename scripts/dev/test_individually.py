import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

sys.stdout.reconfigure(encoding="utf-8")
import pytest

for k in [
    "TestTextCleaner",
    "TestMetadataClassifier",
    "TestTableExtractionAndFiltering",
    "TestFailureHandling",
    "TestHTMLParser",
    "TestDocumentChunker"
]:
    print(f"--- Running {k} ---")
    ret = pytest.main(["-k", k, str(project_root / "tests")])
    print(f"{k} result: {ret}")
