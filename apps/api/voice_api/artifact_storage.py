"""Safe relative paths and streaming checksums for finalized local call files."""

import hashlib
import wave
from pathlib import Path


def artifact_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive or ".." in candidate.parts or ":" in relative:
        raise ValueError("Artifact path must stay within configured storage")
    root = root.resolve()
    joined = root / candidate
    resolved = joined.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("Artifact path escapes storage")
    for part in (joined, *joined.parents):
        if part == root:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError("Artifact links are forbidden")
    return resolved


def file_metadata(path: Path, audio: bool) -> dict:
    with path.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    metadata = {"sha256": checksum, "size_bytes": path.stat().st_size}
    if audio:
        with wave.open(str(path), "rb") as recording:
            if recording.getsampwidth() != 2 or recording.getnchannels() != 1:
                raise ValueError("Expected mono signed 16-bit WAV")
            metadata.update(
                sample_rate=recording.getframerate(),
                channels=recording.getnchannels(),
                sample_width=recording.getsampwidth(),
                duration_seconds=recording.getnframes() / recording.getframerate(),
            )
    return metadata
