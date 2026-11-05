#!/usr/bin/env python3
"""Package tracked C sources only; exclude old binaries, configs and credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source_parent", type=Path)
parser.add_argument("archive", type=Path)
args = parser.parse_args()
manifest = {}
with tarfile.open(args.archive, "w:gz") as archive:
    for name in ("oes_source", "module", "module-unstable"):
        root = args.source_parent / name
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
        files = {}
        for relative in tracked:
            path = root / relative
            if not relative or path.suffix not in (".c", ".h") or not path.is_file():
                continue
            if path.is_symlink():
                raise ValueError(f"Unexpected source symlink: {path}")
            if name == "oes_source" and len(Path(relative).parts) > 1 and Path(relative).parts[0] not in ("httpportal", "okernel", "dispatcher"):
                continue
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            archive.add(path, arcname=f"{name}/{relative}", recursive=False)
        manifest[name] = {"commit": commit, "files": files}
manifest_path = args.archive.with_suffix(args.archive.suffix + ".json")
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({"archive": str(args.archive), "manifest": str(manifest_path), "sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(), "sources": {key: {"commit": value["commit"], "file_count": len(value["files"])} for key, value in manifest.items()}}, indent=2))
