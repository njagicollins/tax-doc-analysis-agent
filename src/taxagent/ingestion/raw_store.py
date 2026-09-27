"""Write-once raw zone: every file we receive is stored untouched, named by its hash."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

RAW_DIR = Path("data/raw")


class TamperedFileError(Exception):
    """A stored file no longer matches the hash in its name."""


@dataclass(frozen=True)
class StoredFile:
    path: Path
    sha256: str
    size_bytes: int
    is_new: bool


def sha256_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def store_raw(
    content: bytes, name: str, quarter: str, raw_dir: Path = RAW_DIR
) -> StoredFile:
    # The name comes from outside (ADP), so it must not contain a path
    if Path(name).name != name:
        raise ValueError(f"Unsafe file name: {name!r}")

    digest = sha256_of(content)
    path = raw_dir / quarter / f"{digest[:12]}_{name}"

    if path.exists():
        # Already stored. Re-check it, so tampering is detected, not ignored
        if sha256_of(path.read_bytes()) != digest:
            raise TamperedFileError(f"{path} no longer matches its hash")
        return StoredFile(path, digest, len(content), is_new=False)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:  # "x" = fail if the file exists: never overwrite
        f.write(content)
    path.chmod(0o444)  # read-only
    return StoredFile(path, digest, len(content), is_new=True)
