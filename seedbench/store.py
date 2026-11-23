"""Persist tray revisions, source photos and immutable saved checks."""

from datetime import datetime, timezone
from hashlib import sha256
from json import dumps, loads
from os import fsync, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock

from image_lab.validation import Conflict, Invalid

from .model import MAX_PHOTOS, MAX_PROOFS, identity, key


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(path, blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix="pending-", delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(blob)
            file.flush()
            fsync(file.fileno())
            replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, (dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode())


def read_json(path):
    try:
        return loads(path.read_bytes())
    except FileNotFoundError as error:
        raise Invalid("This tray or saved check was not found.") from error


class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.trays = self.root / "trays"
        self.guard = RLock()
        self.trays.mkdir(parents=True, exist_ok=True)

    def tray_path(self, tray_id):
        return self.trays / (key(tray_id) + ".json")

    def tray(self, tray_id):
        return read_json(self.tray_path(tray_id))

    def list(self):
        records = [read_json(path) for path in self.trays.glob("*.json")]
        fields = ("id", "title", "filename", "revision", "synthetic", "updated")
        return [{k: row[k] for k in fields} for row in sorted(records, key=lambda row: row["updated"], reverse=True)]

    def blob(self, digest):
        return self.root / "photos" / digest[:2] / (digest + ".png")

    def create(self, title, filename, source, width, height, options, synthetic=False, preparation=None):
        with self.guard:
            if len(self.list()) >= MAX_PHOTOS:
                raise Invalid(f"The library holds up to {MAX_PHOTOS} trays. Remove an unused tray first.")
            digest = sha256(source).hexdigest()
            content = self.blob(digest)
            if not content.exists():
                atomic_write(content, source)
            tray = {
                "id": identity(), "title": title, "filename": filename, "blob": digest,
                "width": width, "height": height, "settings": options, "revision": 1,
                "synthetic": synthetic, "created": stamp(), "updated": stamp(), "proofs": [],
            }
            if preparation is not None:
                tray["preparation"] = preparation
            write_json(self.tray_path(tray["id"]), tray)
            return tray

    @staticmethod
    def revision(row, revision):
        if type(revision) is not int or revision != row["revision"]:
            raise Conflict("This tray changed. Reopen it before saving.")

    def update(self, tray_id, revision, options):
        with self.guard:
            tray = self.tray(tray_id)
            self.revision(tray, revision)
            tray.update(settings=options, revision=revision+1, updated=stamp())
            write_json(self.tray_path(tray_id), tray)
            return tray

    def remove(self, tray_id, revision):
        with self.guard:
            tray = self.tray(tray_id)
            self.revision(tray, revision)
            digest = tray["blob"]
            self.tray_path(tray_id).unlink()
            for proof in tray["proofs"]:
                self.proof_path(tray_id, proof["id"]).unlink(missing_ok=True)
            if not any(self.tray(row["id"])["blob"] == digest for row in self.list()):
                self.blob(digest).unlink(missing_ok=True)

    def proof_path(self, tray_id, proof_id):
        return self.root / "proofs" / key(tray_id) / (key(proof_id) + ".json")

    def proof(self, tray_id, proof_id):
        tray = self.tray(tray_id)
        key(proof_id)
        if not any(row["id"] == proof_id for row in tray["proofs"]):
            raise Invalid("This saved check does not belong to the tray.")
        return read_json(self.proof_path(tray_id, proof_id))

    def retain(self, tray_id, revision, result):
        with self.guard:
            tray = self.tray(tray_id)
            self.revision(tray, revision)
            if len(tray["proofs"]) >= MAX_PROOFS:
                raise Invalid(f"A tray holds up to {MAX_PROOFS} saved checks.")
            row = {**result, "id": identity(), "revision": revision, "saved": stamp(), "source": tray["blob"]}
            path = self.proof_path(tray_id, row["id"])
            write_json(path, row)
            summary = {k: row[k] for k in ("id", "mode", "title", "saved")}
            if row.get("policy"):
                summary["policy"] = row["policy"]
            tray["proofs"].append(summary)
            tray.update(revision=revision+1, updated=stamp())
            try:
                write_json(self.tray_path(tray_id), tray)
            except OSError:
                path.unlink(missing_ok=True)
                raise
            return tray, row
