#!/usr/bin/env python3
"""Verify a composed Program's content-addressed whole-Wasm identity."""
import hashlib
import re
import struct
import sys
import tarfile


def verify(path, expected):
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("invalid whole-Wasm SHA-256")
    with tarfile.open(path, "r:gz") as archive:
        entry = archive.getmember("program/bin/mcpgit")
        if not entry.isfile() or entry.size < 96:
            raise ValueError("missing composed Program")
        stream = archive.extractfile(entry)
        stream.seek(entry.size - 96)
        footer = stream.read(96)
        core, bundle = struct.unpack("<QQ", footer[:16])
        if (footer[80:] != b"MCPGITBUNDLE0001" or not core or not bundle or
                core + bundle + 96 != entry.size or footer[48:80].hex() != expected):
            raise ValueError("composition identity mismatch")
        stream.seek(0)
        for length, digest, wasm in ((core, footer[16:48], False), (bundle, footer[48:80], True)):
            h = hashlib.sha256()
            first = True
            while length:
                chunk = stream.read(min(length, 1024 * 1024))
                if not chunk or (first and wasm and not chunk.startswith(b"\0asm\x01\0\0\0")):
                    raise ValueError("invalid composed bytes")
                h.update(chunk)
                length -= len(chunk)
                first = False
            if h.digest() != digest:
                raise ValueError("composed bytes do not match footer")


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("usage: verify-offline-composition.py PROGRAM_ARCHIVE BUNDLE_SHA256")
        verify(sys.argv[1], sys.argv[2])
    except (ValueError, OSError, KeyError, EOFError, struct.error, tarfile.TarError) as error:
        print("composition verification failed: " + str(error), file=sys.stderr)
        raise SystemExit(1)
