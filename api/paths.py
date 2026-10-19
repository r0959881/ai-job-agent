"""Only files inside OUTPUT_DIR may be served, previewed or deleted."""
from pathlib import Path

from config import OUTPUT_DIR, resolve_project_path


class UnsafePath(Exception):
    pass


def safe_output_path(stored_path):
    """Resolve a stored path and refuse anything outside output/ (traversal, absolute paths, links)."""
    if not stored_path:
        raise UnsafePath("No file path is stored for this item.")
    resolved = Path(resolve_project_path(stored_path)).resolve()
    root = OUTPUT_DIR.resolve()
    if resolved != root and root not in resolved.parents:
        raise UnsafePath("That file is outside the output folder, so it cannot be opened here.")
    return resolved
