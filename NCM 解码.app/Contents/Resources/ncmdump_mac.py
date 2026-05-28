#!/usr/bin/env python3
"""Convert NetEase Cloud Music .ncm files to their original audio format."""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
import shlex
import struct
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path


CORE_KEY = b"hzHRAmso5kInbaxW"
META_KEY = b"#14ljk_!\\]&0U<'("
MAGIC = b"CTENFDAM"


class NCMError(Exception):
    pass


print_lock = threading.Lock()


def default_log_path() -> Path:
    return Path.home() / "Music" / "ncmdump_mac.log"


def write_log(log_path: Path | None, message: str) -> None:
    if not log_path:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(message + "\n")
    except OSError:
        pass


def bounded_int(value: str, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise argparse.ArgumentTypeError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def workers_value(value: str) -> int:
    return bounded_int(value, "workers", 1, 32)


def max_failures_value(value: str) -> int:
    return bounded_int(value, "max-failures", 0, 100000)


def aes_128_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    try:
        result = subprocess.run(
            [
                "openssl",
                "enc",
                "-d",
                "-aes-128-ecb",
                "-K",
                key.hex(),
                "-nopad",
                "-nosalt",
            ],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise NCMError("openssl not found; install it with Homebrew or Xcode tools") from exc

    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise NCMError(f"openssl AES decrypt failed: {detail}")
    return result.stdout


def pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise NCMError("empty AES plaintext")
    pad = data[-1]
    if pad < 1 or pad > 16 or data[-pad:] != bytes([pad]) * pad:
        raise NCMError("invalid PKCS#7 padding")
    return data[:-pad]


def read_u32(handle) -> int:
    raw = handle.read(4)
    if len(raw) != 4:
        raise NCMError("unexpected end of file")
    return struct.unpack("<I", raw)[0]


def build_key_box(key: bytes) -> list[int]:
    box = list(range(256))
    key_len = len(key)
    last_byte = 0
    key_offset = 0

    for i in range(256):
        swap = box[i]
        c = (swap + last_byte + key[key_offset]) & 0xFF
        key_offset = (key_offset + 1) % key_len
        box[i] = box[c]
        box[c] = swap
        last_byte = c

    return box


def decrypt_audio(data: bytes, box: list[int]) -> bytes:
    output = bytearray(data)
    for i, value in enumerate(output):
        j = (i + 1) & 0xFF
        output[i] = value ^ box[(box[j] + box[(box[j] + j) & 0xFF]) & 0xFF]
    return bytes(output)


def parse_metadata(raw: bytes) -> dict:
    if not raw:
        return {}

    decoded = bytes(byte ^ 0x63 for byte in raw)
    prefix = b"163 key(Don't modify):"
    if decoded.startswith(prefix):
        decoded = decoded[len(prefix) :]

    try:
        encrypted = base64.b64decode(decoded)
        plaintext = pkcs7_unpad(aes_128_ecb_decrypt(encrypted, META_KEY))
    except Exception as exc:
        raise NCMError(f"failed to decrypt metadata: {exc}") from exc

    if plaintext.startswith(b"music:"):
        plaintext = plaintext[len(b"music:") :]

    try:
        return json.loads(plaintext.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise NCMError(f"failed to parse metadata JSON: {exc}") from exc


def title_from_metadata(meta: dict, fallback: str) -> str:
    title, artists, _ = metadata_fields(meta, fallback)
    return f"{artists} - {title}" if artists else title


def metadata_fields(meta: dict, fallback: str) -> tuple[str, str, str]:
    title = str(meta.get("musicName") or meta.get("name") or fallback)
    album = str(meta.get("album") or "")
    artists = meta.get("artist") or meta.get("artists") or []
    names: list[str] = []
    for artist in artists:
        if isinstance(artist, list) and artist:
            names.append(str(artist[0]))
        elif isinstance(artist, dict) and artist.get("name"):
            names.append(str(artist["name"]))
        elif isinstance(artist, str):
            names.append(artist)
    return title, ", ".join(names), album


def safe_filename(name: str) -> str:
    cleaned = "".join("_" if char in '/\\:*?"<>|' else char for char in name)
    cleaned = cleaned.strip()
    return cleaned[:180] or "converted"


def sniff_format(audio: bytes, meta: dict) -> str:
    fmt = str(meta.get("format") or "").lower().strip(".")
    if fmt:
        return fmt
    if audio.startswith(b"fLaC"):
        return "flac"
    if audio.startswith(b"ID3") or audio[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    return "bin"


def image_mime_type(image_data: bytes) -> str:
    if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return "image/jpeg"


def image_dimensions(image_data: bytes) -> tuple[int, int, int]:
    if image_data.startswith(b"\x89PNG\r\n\x1a\n") and len(image_data) >= 25:
        width = int.from_bytes(image_data[16:20], "big")
        height = int.from_bytes(image_data[20:24], "big")
        bit_depth = image_data[24]
        color_type = image_data[25] if len(image_data) > 25 else 0
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type, 0)
        depth = bit_depth * channels if channels else bit_depth
        return width, height, depth

    if image_data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(image_data):
            if image_data[index] != 0xFF:
                index += 1
                continue
            marker = image_data[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(image_data):
                break
            length = int.from_bytes(image_data[index : index + 2], "big")
            if length < 2 or index + length > len(image_data):
                break
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                precision = image_data[index + 2]
                height = int.from_bytes(image_data[index + 3 : index + 5], "big")
                width = int.from_bytes(image_data[index + 5 : index + 7], "big")
                components = image_data[index + 7] if index + 7 < len(image_data) else 0
                depth = precision * components if components else precision
                return width, height, depth
            index += length

    return 0, 0, 0


def build_vorbis_comment(meta: dict, fallback: str) -> bytes:
    title, artists, album = metadata_fields(meta, fallback)
    comments = []
    if title:
        comments.append(f"TITLE={title}".encode("utf-8"))
    if artists:
        comments.append(f"ARTIST={artists}".encode("utf-8"))
    if album:
        comments.append(f"ALBUM={album}".encode("utf-8"))

    vendor = b"ncmdump_mac.py"
    payload = bytearray()
    payload += struct.pack("<I", len(vendor))
    payload += vendor
    payload += struct.pack("<I", len(comments))
    for comment in comments:
        payload += struct.pack("<I", len(comment))
        payload += comment
    return bytes(payload)


def build_flac_picture(image_data: bytes) -> bytes:
    mime = image_mime_type(image_data).encode("ascii")
    width, height, depth = image_dimensions(image_data)
    payload = bytearray()
    payload += struct.pack(">I", 3)
    payload += struct.pack(">I", len(mime)) + mime
    payload += struct.pack(">I", 0)
    payload += struct.pack(">IIII", width, height, depth, 0)
    payload += struct.pack(">I", len(image_data)) + image_data
    return bytes(payload)


def flac_block(block_type: int, payload: bytes, is_last: bool) -> bytes:
    if len(payload) > 0xFFFFFF:
        raise NCMError("FLAC metadata block is too large")
    first = block_type | (0x80 if is_last else 0)
    return bytes([first]) + len(payload).to_bytes(3, "big") + payload


def embed_flac_tags(audio: bytes, meta: dict, image_data: bytes, fallback: str) -> bytes:
    if not audio.startswith(b"fLaC"):
        return audio

    offset = 4
    blocks: list[tuple[int, bytes]] = []
    while True:
        if offset + 4 > len(audio):
            raise NCMError("invalid FLAC metadata header")
        header = audio[offset : offset + 4]
        offset += 4
        is_last = bool(header[0] & 0x80)
        block_type = header[0] & 0x7F
        length = int.from_bytes(header[1:4], "big")
        if offset + length > len(audio):
            raise NCMError("invalid FLAC metadata length")
        payload = audio[offset : offset + length]
        offset += length
        if block_type not in {4, 6}:
            blocks.append((block_type, payload))
        if is_last:
            break

    new_blocks = [(4, build_vorbis_comment(meta, fallback))]
    if image_data:
        new_blocks.append((6, build_flac_picture(image_data)))
    blocks.extend(new_blocks)

    output = bytearray(b"fLaC")
    for index, (block_type, payload) in enumerate(blocks):
        output += flac_block(block_type, payload, index == len(blocks) - 1)
    output += audio[offset:]
    return bytes(output)


def syncsafe(size: int) -> bytes:
    if size > 0x0FFFFFFF:
        raise NCMError("ID3 tag is too large")
    return bytes(
        [
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
        ]
    )


def unsyncsafe(data: bytes) -> int:
    return ((data[0] & 0x7F) << 21) | ((data[1] & 0x7F) << 14) | ((data[2] & 0x7F) << 7) | (data[3] & 0x7F)


def id3_frame(frame_id: str, payload: bytes) -> bytes:
    return frame_id.encode("ascii") + len(payload).to_bytes(4, "big") + b"\x00\x00" + payload


def id3_text_frame(frame_id: str, text: str) -> bytes:
    return id3_frame(frame_id, b"\x01" + text.encode("utf-16"))


def embed_mp3_tags(audio: bytes, meta: dict, image_data: bytes, fallback: str) -> bytes:
    if audio.startswith(b"ID3") and len(audio) >= 10:
        old_tag_size = unsyncsafe(audio[6:10])
        if len(audio) < 10 + old_tag_size:
            raise NCMError("invalid existing ID3 tag size")
        audio = audio[10 + old_tag_size :]

    title, artists, album = metadata_fields(meta, fallback)
    frames = bytearray()
    if title:
        frames += id3_text_frame("TIT2", title)
    if artists:
        frames += id3_text_frame("TPE1", artists)
    if album:
        frames += id3_text_frame("TALB", album)
    if image_data:
        mime = image_mime_type(image_data).encode("ascii")
        apic = b"\x00" + mime + b"\x00" + b"\x03" + b"\x00" + image_data
        frames += id3_frame("APIC", apic)

    if not frames:
        return audio
    return b"ID3\x03\x00\x00" + syncsafe(len(frames)) + bytes(frames) + audio


def embed_audio_tags(audio: bytes, ext: str, meta: dict, image_data: bytes, fallback: str) -> bytes:
    if not meta and not image_data:
        return audio
    if ext == "flac":
        return embed_flac_tags(audio, meta, image_data, fallback)
    if ext == "mp3":
        return embed_mp3_tags(audio, meta, image_data, fallback)
    return audio


def validate_flac_audio(audio: bytes) -> None:
    if not audio.startswith(b"fLaC"):
        raise NCMError("self-check failed: output is not a FLAC stream; the NCM file may be incomplete or damaged")

    offset = 4
    has_streaminfo = False
    while True:
        if offset + 4 > len(audio):
            raise NCMError("self-check failed: truncated FLAC metadata header; check whether the source NCM is damaged")
        header = audio[offset : offset + 4]
        offset += 4
        is_last = bool(header[0] & 0x80)
        block_type = header[0] & 0x7F
        length = int.from_bytes(header[1:4], "big")
        if offset + length > len(audio):
            raise NCMError("self-check failed: truncated FLAC metadata block; check whether the source NCM is damaged")
        if block_type == 0:
            if length != 34:
                raise NCMError("self-check failed: invalid FLAC STREAMINFO block")
            has_streaminfo = True
        offset += length
        if is_last:
            break

    if not has_streaminfo:
        raise NCMError("self-check failed: missing FLAC STREAMINFO block")
    if offset >= len(audio):
        raise NCMError("self-check failed: FLAC contains metadata but no audio frames")


def mp3_payload_offset(audio: bytes) -> int:
    if audio.startswith(b"ID3") and len(audio) >= 10:
        tag_size = unsyncsafe(audio[6:10])
        offset = 10 + tag_size
        if offset >= len(audio):
            raise NCMError("self-check failed: MP3 has an invalid ID3 tag size")
        return offset
    return 0


def validate_mp3_audio(audio: bytes) -> None:
    offset = mp3_payload_offset(audio)
    limit = min(len(audio) - 1, offset + 65536)
    index = offset
    while index < limit:
        if audio[index] == 0xFF and (audio[index + 1] & 0xE0) == 0xE0:
            version = (audio[index + 1] >> 3) & 0x03
            layer = (audio[index + 1] >> 1) & 0x03
            bitrate = (audio[index + 2] >> 4) & 0x0F if index + 2 < len(audio) else 0
            sample_rate = (audio[index + 2] >> 2) & 0x03 if index + 2 < len(audio) else 3
            if version != 1 and layer != 0 and bitrate not in {0, 15} and sample_rate != 3:
                return
        index += 1
    raise NCMError("self-check failed: no valid MP3 frame sync found; check whether the source NCM is damaged")


def validate_audio(audio: bytes, ext: str) -> None:
    if ext == "flac":
        validate_flac_audio(audio)
    elif ext == "mp3":
        validate_mp3_audio(audio)
    elif ext == "bin":
        raise NCMError("self-check failed: unknown decrypted audio format")


def atomic_write(path: Path, data: bytes) -> None:
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_bytes(data)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def convert_file(
    input_path: Path,
    output_dir: Path | None,
    write_sidecars: bool,
    embed_tags: bool,
) -> Path:
    with input_path.open("rb") as handle:
        magic = handle.read(8)
        if magic != MAGIC:
            raise NCMError("not an NCM file: bad magic header")

        handle.read(2)

        key_length = read_u32(handle)
        encrypted_key = bytes(byte ^ 0x64 for byte in handle.read(key_length))
        if len(encrypted_key) != key_length:
            raise NCMError("truncated encrypted key")

        key_data = pkcs7_unpad(aes_128_ecb_decrypt(encrypted_key, CORE_KEY))
        if len(key_data) <= 17:
            raise NCMError("decrypted key is too short")
        key_box = build_key_box(key_data[17:])

        meta_length = read_u32(handle)
        meta = parse_metadata(handle.read(meta_length))

        handle.read(5)

        cover_frame_length = read_u32(handle)
        image_length = read_u32(handle)
        image_data = handle.read(image_length)
        if len(image_data) != image_length:
            raise NCMError("truncated cover image")
        if cover_frame_length < image_length:
            raise NCMError("invalid cover frame length")
        handle.seek(cover_frame_length - image_length, os.SEEK_CUR)

        audio = decrypt_audio(handle.read(), key_box)

    ext = sniff_format(audio, meta)
    if embed_tags:
        audio = embed_audio_tags(audio, ext, meta, image_data, input_path.stem)
    validate_audio(audio, ext)

    base_name = safe_filename(input_path.stem)
    output_dir = output_dir or input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{base_name}.{ext}"

    counter = 2
    while output_path.exists():
        output_path = output_dir / f"{base_name} ({counter}).{ext}"
        counter += 1

    atomic_write(output_path, audio)

    if write_sidecars:
        if meta:
            output_path.with_suffix(output_path.suffix + ".json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if image_data:
            image_ext = ".jpg"
            if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
                image_ext = ".png"
            output_path.with_suffix(output_path.suffix + image_ext).write_bytes(image_data)

    return output_path


def collect_inputs(paths: list[Path], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        path = path.expanduser()
        if path.is_dir():
            pattern = "**/*.ncm" if recursive else "*.ncm"
            files.extend(sorted(path.glob(pattern)))
        elif path.is_file():
            files.append(path)
        else:
            raise NCMError(f"path does not exist: {path}")

    seen: set[Path] = set()
    unique: list[Path] = []
    for file_path in files:
        resolved = file_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(file_path)
    return unique


def print_status(message: str, *, error: bool = False) -> None:
    with print_lock:
        print(message, file=sys.stderr if error else sys.stdout, flush=True)


def run_batch(
    inputs: list[Path],
    output_dir: Path | None,
    write_sidecars: bool,
    embed_tags: bool,
    workers: int,
    max_failures: int,
    log_path: Path | None,
) -> int:
    if workers < 1 or workers > 32:
        raise NCMError("workers must be between 1 and 32")
    if max_failures < 0 or max_failures > 100000:
        raise NCMError("max-failures must be between 0 and 100000")
    total = len(inputs)
    success = 0
    failed = 0
    submitted = 0
    completed = 0
    stop_reason = ""
    failures: list[tuple[Path, str]] = []

    def submit_next(executor, futures):
        nonlocal submitted
        while submitted < total and len(futures) < workers:
            input_path = inputs[submitted]
            future = executor.submit(
                convert_file,
                input_path,
                output_dir,
                write_sidecars,
                embed_tags,
            )
            futures[future] = input_path
            submitted += 1

    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    print_status(f"Found {total} NCM file(s). Workers: {workers}.")
    if log_path:
        print_status(f"Log file: {log_path}")
    write_log(log_path, "")
    write_log(log_path, f"=== ncmdump run started at {started_at} ===")
    write_log(log_path, f"workers={workers}, max_failures={max_failures}, total={total}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures: dict[concurrent.futures.Future[Path], Path] = {}
        submit_next(executor, futures)

        while futures:
            done, _ = concurrent.futures.wait(
                futures,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                input_path = futures.pop(future)
                completed += 1
                try:
                    output_path = future.result()
                except Exception as exc:
                    failed += 1
                    reason = str(exc)
                    failures.append((input_path, reason))
                    print_status(
                        f"[FAIL {completed}/{total}] {input_path}\n  Reason: {reason}",
                        error=True,
                    )
                    write_log(log_path, f"FAIL\t{input_path}\t{reason}")
                    if max_failures > 0 and failed >= max_failures:
                        stop_reason = f"stopped after {failed} failure(s)"
                        for pending in list(futures):
                            pending.cancel()
                        break
                else:
                    success += 1
                    print_status(f"[OK {completed}/{total}] {input_path} -> {output_path}")
                    write_log(log_path, f"OK\t{input_path}\t{output_path}")

            if stop_reason:
                break
            submit_next(executor, futures)

    if stop_reason:
        for future, input_path in list(futures.items()):
            if future.cancelled():
                futures.pop(future, None)
                continue
            try:
                output_path = future.result()
            except Exception as exc:
                failed += 1
                reason = str(exc)
                failures.append((input_path, reason))
                print_status(f"[FAIL] {input_path}\n  Reason: {reason}", error=True)
                write_log(log_path, f"FAIL\t{input_path}\t{reason}")
            else:
                success += 1
                print_status(f"[OK] {input_path} -> {output_path}")
                write_log(log_path, f"OK\t{input_path}\t{output_path}")
            finally:
                futures.pop(future, None)

    skipped = max(0, total - success - failed)
    print_status(
        f"Done. Success: {success}, failed: {failed}, skipped: {skipped}."
        + (f" Auto interrupt: {stop_reason}." if stop_reason else "")
    )
    if failures:
        print_status("Failed files summary:", error=True)
        for index, (path, reason) in enumerate(failures, 1):
            print_status(f"{index}. {path}\n   Reason: {reason}", error=True)
        print_status("Tip: check that the failed item is a valid .ncm file and is not incomplete.", error=True)
    if log_path:
        finished_at = time.strftime("%Y-%m-%d %H:%M:%S")
        write_log(
            log_path,
            f"=== finished at {finished_at}; success={success}, failed={failed}, skipped={skipped} ===",
        )
        print_status(f"Log saved to: {log_path}")
    return 0 if success == total else 1


def parse_dragged_paths(raw: str) -> list[Path]:
    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        raise NCMError(f"failed to parse dragged paths: {exc}") from exc
    return [Path(part) for part in parts]


def interactive_main(workers: int, max_failures: int, log_path: Path | None) -> int:
    print("NCM macOS decoder")
    print("Drag one or more .ncm files or folders into this terminal, then press Enter.")
    print("Output files are written next to the original .ncm files.")
    print("Type q and press Enter to quit.")
    print()

    while True:
        try:
            raw = input("Drop files here > ").strip()
        except EOFError:
            return 0

        if raw.lower() in {"q", "quit", "exit"}:
            return 0
        if not raw:
            continue

        try:
            paths = parse_dragged_paths(raw)
            inputs = collect_inputs(paths, recursive=True)
            if not inputs:
                raise NCMError("no .ncm files found")
            return run_batch(
                inputs=inputs,
                output_dir=None,
                write_sidecars=False,
                embed_tags=True,
                workers=workers,
                max_failures=max_failures,
                log_path=log_path,
            )
        except KeyboardInterrupt:
            print_status("\nInterrupted by user.", error=True)
            return 130
        except Exception as exc:
            print_status(f"[ERROR] {exc}", error=True)
            print("Try again, or type q to quit.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert NetEase Cloud Music .ncm files on macOS."
    )
    parser.add_argument("inputs", nargs="*", type=Path, help="NCM file(s) or directory")
    parser.add_argument("-o", "--output", type=Path, help="output directory")
    parser.add_argument("-r", "--recursive", action="store_true", help="scan directories recursively")
    parser.add_argument("-w", "--workers", type=workers_value, default=min(os.cpu_count() or 4, 4))
    parser.add_argument(
        "--max-failures",
        type=max_failures_value,
        default=3,
        help="stop scheduling new work after this many failures; 0 disables the limit",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="prompt for dragged files and write outputs next to the originals",
    )
    parser.add_argument(
        "--no-sidecars",
        action="store_true",
        help="do not write metadata JSON and cover image sidecar files",
    )
    parser.add_argument(
        "--no-tags",
        action="store_true",
        help="do not embed title, artist, album, and cover into output audio",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=default_log_path(),
        help="write a conversion log to this file",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="disable conversion log output",
    )
    args = parser.parse_args()

    try:
        log_path = None if args.no_log else args.log.expanduser()
        if args.interactive or not args.inputs:
            return interactive_main(args.workers, args.max_failures, log_path)

        inputs = collect_inputs(args.inputs, args.recursive)
        if not inputs:
            raise NCMError("no .ncm files found")
        return run_batch(
            inputs=inputs,
            output_dir=args.output,
            write_sidecars=not args.no_sidecars,
            embed_tags=not args.no_tags,
            workers=args.workers,
            max_failures=args.max_failures,
            log_path=log_path,
        )
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except NCMError as exc:
        print(f"ncmdump: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
