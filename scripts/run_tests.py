import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

sys.stdout.reconfigure(encoding="utf-8")
import pytest

exit_code = pytest.main(["-v", str(project_root / "tests")])
sys.exit(exit_code)
