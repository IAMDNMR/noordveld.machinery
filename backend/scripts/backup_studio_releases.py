"""Back up retained release packages and test history to a new local file.

Restoration uses the verified copy as DESIGN_STUDIO_RELEASE_DB after stopping
the backend. Never overwrite the running database. Keep backups on durable,
access-controlled storage; this command does not upload them to a provider.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.design_studio.releases import ReleaseStore

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--target", type=Path, required=True)
args = parser.parse_args()
if not args.source.is_file():
    parser.error("The source release database does not exist.")
print(json.dumps(ReleaseStore(args.source, initialize=False).backup(args.target)))
