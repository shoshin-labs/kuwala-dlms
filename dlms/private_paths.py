"""Filesystem fences for private operator state and explicit dependencies."""
from pathlib import Path


def checked_path(value, label):
    path = Path(value)
    if not path.is_absolute() or path == Path(path.anchor) or '..' in path.parts:
        raise ValueError(label + ' must be an absolute path without parent traversal.')
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise ValueError(label + ' must not contain symlinks.')
        if part.exists() and part != path and not part.is_dir():
            raise ValueError(label + ' has a non-directory parent.')
    return path


def checked_directory(value, label, *, create=False):
    path = checked_path(value, label)
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and not path.is_dir():
        raise ValueError(label + ' must be a directory.')
    return path


def require_disjoint(path, protected, label):
    for value in protected:
        try:
            root = Path(value).resolve()
        except (OSError, RuntimeError) as exc:
            raise ValueError(label + ' has an unavailable protected root.') from exc
        if path.is_relative_to(root) or root.is_relative_to(path):
            raise ValueError(label + ' must not overlap source code, originals, exports or a protected live/evaluation root.')
