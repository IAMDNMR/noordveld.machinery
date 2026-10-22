"""Start the local Studio website using a dedicated temporary data directory."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    directory = Path(tempfile.gettempdir()) / "noordveld-studio-local-site"
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["DESIGN_STUDIO_LOCAL_DEV"] = "1"
    os.environ["APP_ENV"] = "local"
    os.environ.setdefault("DESIGN_STUDIO_LOCAL_DB", str(directory / "studio.sqlite"))
    release_directory = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Noordveld" / "Studio"
    )
    release_directory.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DESIGN_STUDIO_RELEASE_DB", str(release_directory / "releases.sqlite"))
    import uvicorn

    uvicorn.run("app.local_site:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
