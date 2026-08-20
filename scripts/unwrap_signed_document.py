"""Extract the payload from a Ukrainian DSTU-signed PKCS#7 container.

Ukrainian official documents — bank statements, utility bills, довідки issued through Дія — arrive as
PKCS#7/CMS envelopes, usually still named `.pdf`. They are signed with DSTU 4145 / GOST 34311-95, which
OpenSSL does not implement, so `openssl smime -verify -noverify` fails with "unknown digest type" and every
document system rejects the file as `application/octet-stream`.

Reading the document does not require the signature algorithm at all. The payload sits in
signedData.encapContentInfo.eContent, and a plain DER walk lifts it out. What is *not* possible here is
verifying the signature — that genuinely needs DSTU support, and this script never claims the document is
authentic, only that this is what was inside.
"""

import sys
from pathlib import Path

CONSTRUCTED = 0x20
CONTEXT_SPECIFIC = 0x80
SEQUENCE = 0x30
OCTET_STRING = 0x04


def read_length(data: bytes, offset: int) -> tuple[int, int]:
    """The value's length and the offset it starts at, handling DER's long form."""
    first = data[offset]
    offset += 1
    if first < 0x80:
        return first, offset
    byte_count = first & 0x7F
    return int.from_bytes(data[offset : offset + byte_count], "big"), offset + byte_count


def walk(data: bytes, offset: int, end: int):
    """Yield (tag, value_start, value_end) for each TLV at this level."""
    while offset < end:
        tag = data[offset]
        length, value_start = read_length(data, offset + 1)
        yield tag, value_start, value_start + length
        offset = value_start + length


def find_encapsulated_content(data: bytes) -> bytes | None:
    """The eContent octets, found by descending ContentInfo → SignedData → EncapsulatedContentInfo."""
    for tag, start, end in walk(data, 0, len(data)):
        if tag != SEQUENCE:
            continue
        for inner_tag, inner_start, inner_end in walk(data, start, end):
            if inner_tag != (CONTEXT_SPECIFIC | CONSTRUCTED | 0):
                continue
            for signed_tag, signed_start, signed_end in walk(data, inner_start, inner_end):
                if signed_tag != SEQUENCE:
                    continue
                for field_tag, field_start, field_end in walk(data, signed_start, signed_end):
                    if field_tag != SEQUENCE:
                        continue
                    # EncapsulatedContentInfo: an eContentType OID followed by [0] EXPLICIT OCTET STRING
                    for part_tag, part_start, part_end in walk(data, field_start, field_end):
                        if part_tag != (CONTEXT_SPECIFIC | CONSTRUCTED | 0):
                            continue
                        for octet_tag, octet_start, octet_end in walk(data, part_start, part_end):
                            if octet_tag == OCTET_STRING:
                                return data[octet_start:octet_end]
    return None


def unwrap(path: Path) -> bytes | None:
    data = path.read_bytes()
    payload = find_encapsulated_content(data)
    if payload:
        return payload
    # a detached signature carries no payload; an unusual encoding may still hide a readable document
    start = data.find(b"%PDF-")
    end = data.rfind(b"%%EOF")
    return data[start : end + 5] if start != -1 and end != -1 else None


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: unwrap_signed_document.py <source-dir> <target-dir>", file=sys.stderr)
        return 2

    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    target.mkdir(parents=True, exist_ok=True)
    unwrapped = skipped = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        payload = unwrap(path)
        if payload is None or len(payload) < 100:
            print(f"  SKIP     {path.name} — no payload found")
            skipped += 1
            continue
        (target / path.name).write_bytes(payload)
        print(f"  unwrapped {path.name}  {len(path.read_bytes())} → {len(payload)} bytes")
        unwrapped += 1

    print(f"\nunwrapped {unwrapped}, skipped {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
