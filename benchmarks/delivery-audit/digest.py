"""Independent content-digest implementation used by the benchmark harness.

It intentionally re-implements the frozen ``delivery-content/v1`` algorithm
rather than calling the tool under test, so a bug in the tool cannot silently
bless its own fixture digests.
"""

import hashlib
import zipfile
from pathlib import Path


def content_digest(entries):
    payload = b"delivery-content/v1\n"
    for path, data in sorted(entries, key=lambda item: (item[0].casefold(),
                                                        item[0])):
        payload += ("%s\t%d\t%s\n" % (hashlib.sha256(data).hexdigest(),
                                      len(data), path)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def directory_entries(root):
    root = Path(root)
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            entries.append((path.relative_to(root).as_posix(), path.read_bytes()))
    return entries


def zip_entries(path):
    with zipfile.ZipFile(path) as archive:
        return [(info.filename, archive.read(info))
                for info in archive.infolist() if not info.is_dir()]


def file_entries(path):
    path = Path(path)
    return [(path.name, path.read_bytes())]


def describe(entries):
    return [{"path": path, "size": len(data),
             "sha256": hashlib.sha256(data).hexdigest()}
            for path, data in sorted(entries, key=lambda item: (item[0].casefold(),
                                                                item[0]))]
