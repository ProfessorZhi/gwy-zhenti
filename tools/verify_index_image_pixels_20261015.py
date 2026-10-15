"""Validate referenced image pixels at the exact Git index publication boundary.

Read staged exam Markdown and image blobs through cat-file streams. Never open
working-tree images, and reject additions/deletions/changes to either index map.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from PIL import Image, ImageFile, ImageSequence
from cloud_quality import image_refs, resolve_image

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(os.environ)
if os.name == "nt":
    ENV.update(GIT_CONFIG_GLOBAL="NUL", GIT_CONFIG_NOSYSTEM="1")


def command(*args):
    return ["git", "-c", "core.fsmonitor=false", *args]


def index_snapshot(root=ROOT):
    raw = subprocess.check_output(
        command("ls-files", "--stage", "-z", "--", "图片", "国考", "省考"),
        cwd=root, env=ENV, timeout=120,
    )
    images, markdown = {}, {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        mode, blob, stage = header.decode("ascii").split()
        path = raw_path.decode("utf-8")
        is_image = path.startswith("图片/")
        name = path.rsplit("/", 1)[-1]
        is_paper = (path.startswith(("国考/", "省考/"))
                    and name.startswith(("行测-", "申论-"))
                    and name.endswith(".md"))
        if not (is_image or is_paper):
            continue
        if stage != "0" or mode != "100644":
            raise ValueError("Unresolved or nonregular publication entry: " + path)
        target = images if is_image else markdown
        if path in target:
            raise ValueError("Duplicate stage-zero path: " + path)
        target[path] = blob
    return {"images": images, "markdown": markdown}


def fingerprint(entries):
    payload = "".join(path + "\0" + blob + "\n"
                      for path, blob in sorted(entries.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def blob_hash(data, oid):
    if len(oid) == 40:
        algorithm = hashlib.sha1
    elif len(oid) == 64:
        algorithm = hashlib.sha256
    else:
        raise ValueError("Unsupported Git object id: " + oid)
    return algorithm(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def read_exact(stream, size):
    if size < 0:
        raise ValueError("Negative Git object length")
    parts, remaining = [], size
    while remaining:
        part = stream.read(remaining)
        if not part:
            raise ValueError("Truncated Git batch object")
        parts.append(part)
        remaining -= len(part)
    return b"".join(parts)


def staged_blobs(root, entries):
    """Yield hash-verified blobs, draining the stream even when callers decode slowly."""
    ordered = sorted(entries.items())
    process = subprocess.Popen(
        command("cat-file", "--batch"), cwd=root, env=ENV,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    writer_errors = []

    def feed():
        try:
            for _, blob in ordered:
                process.stdin.write((blob + "\n").encode("ascii"))
            process.stdin.close()
        except Exception as exc:
            writer_errors.append(str(exc))

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    try:
        for path, oid in ordered:
            header = process.stdout.readline().decode("ascii").strip().split()
            if len(header) != 3 or header[0] != oid or header[1] != "blob":
                raise ValueError("Unexpected Git batch header: " + str(header))
            data = read_exact(process.stdout, int(header[2]))
            if process.stdout.read(1) != b"\n":
                raise ValueError("Missing Git batch object terminator")
            if blob_hash(data, oid) != oid:
                raise ValueError("Staged object hash mismatch: " + path)
            yield path, data
        writer.join(timeout=10)
        if writer.is_alive():
            raise ValueError("Git batch writer did not finish")
        if process.wait(timeout=120) or writer_errors:
            raise ValueError("Git batch process failed: " + str(writer_errors))
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        writer.join(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream:
                stream.close()


def assert_unchanged(before, after):
    for kind in ("images", "markdown"):
        if before[kind] != after[kind]:
            added = sorted(set(after[kind]) - set(before[kind]))
            removed = sorted(set(before[kind]) - set(after[kind]))
            changed = sorted(path for path in before[kind].keys() & after[kind].keys()
                             if before[kind][path] != after[kind][path])
            raise ValueError("Publication index changed during decoding: " + kind
                             + " " + repr({"added": added[:5], "removed": removed[:5],
                                           "changed": changed[:5]}))


def verify(root=ROOT, progress=True):
    root = Path(root)
    before = index_snapshot(root)
    if not before["markdown"]:
        raise ValueError("No staged exam Markdown files")
    references = set()
    for path, raw in staged_blobs(root, before["markdown"]):
        for ref in image_refs(raw.decode("utf-8-sig")):
            target = resolve_image(path, ref)
            if target is None or target.startswith("!"):
                raise ValueError("Unverifiable image: " + path + " -> " + ref)
            references.add(target)
    missing = references - set(before["images"])
    if missing:
        raise ValueError("Referenced images not staged: " + repr(sorted(missing)[:10]))
    selected = {path: before["images"][path] for path in sorted(references)}
    # Many regional copies reference identical content-addressed Git objects.
    # Verify and decode that exact object once, while binding every indexed path.
    # This never substitutes working-tree bytes or trusts an unverified object id.
    groups = {}
    for path, oid in selected.items():
        groups.setdefault(oid, []).append(path)
    representatives = {paths[0]: oid for oid, paths in groups.items()}
    errors, frames, path_frames, verified_paths = [], 0, 0, 0
    next_progress = 10000
    previous_truncation_policy = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        for n, (path, data) in enumerate(staged_blobs(root, representatives), 1):
            paths = groups[selected[path]]
            decoded = 0
            try:
                with Image.open(io.BytesIO(data)) as im:
                    for frame in ImageSequence.Iterator(im):
                        frame.load()
                        if frame.width <= 0 or frame.height <= 0:
                            raise ValueError("Invalid dimensions")
                        frames += 1
                        decoded += 1
            except Exception as exc:
                errors.extend({"path": p,
                               "error": type(exc).__name__ + ": " + str(exc)[:160]} for p in paths)
            path_frames += decoded * len(paths)
            verified_paths += len(paths)
            if progress and (verified_paths >= next_progress or n == len(representatives)):
                print(f"Git image pixels: {verified_paths}/{len(selected)} paths; "
                      f"{n}/{len(representatives)} distinct blobs", file=sys.stderr, flush=True)
                next_progress = (verified_paths // 10000 + 1) * 10000
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = previous_truncation_policy
    after = index_snapshot(root)
    assert_unchanged(before, after)
    return {
        "status": "passed" if not errors else "failed",
        "publication_boundary": "Stage-zero exam Markdown and referenced image blobs",
        "staged_exam_markdown": len(before["markdown"]),
        "indexed_images": len(before["images"]),
        "unique_images": len(selected),
        "unreferenced_index_images": len(before["images"]) - len(selected),
        "decoded_frames": frames,
        "validated_image_path_frames": path_frames,
        "unique_git_image_blobs": len(groups),
        "deduplication_basis": "Every path is bound to an unchanged stage-zero Git object id; each distinct blob is hash-verified and fully decoded",
        "failed_images": len(errors),
        "image_index_fingerprint_sha256": fingerprint(before["images"]),
        "paper_index_fingerprint_sha256": fingerprint(before["markdown"]),
        "referenced_image_fingerprint_sha256": fingerprint(selected),
        "index_stable_at_final_snapshot": True,
        "errors": errors,
    }


def main():
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result["status"] != "passed"


if __name__ == "__main__":
    sys.exit(main())
