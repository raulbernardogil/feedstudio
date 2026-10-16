"""Local development entry point: apply migrations, then start the API.

    python run_dev.py            # http://localhost:8000 (docs at /docs)
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402


def main() -> None:
    command.upgrade(Config(str(HERE / "alembic.ini")), "head")
    import uvicorn

    uvicorn.run("feedstudio.main:app", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")),
                reload=os.environ.get("RELOAD", "0") == "1")


if __name__ == "__main__":
    main()
