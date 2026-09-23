"""Wire crypto for the Uma Musume PC client's API traffic.

Request  = b64( <u32 flag=64> + blob1[64] + AES-CBC( pkcs7( LZ4( msgpack ) ) ) )
           blob1[ 0:16] = sid16  ^ rk[0:16]  ^ XOR_KEY[0:16]
           blob1[16:32] = udid16 ^ rk[16:32] ^ XOR_KEY[16:32]
           blob1[32:64] = rk (plaintext random key chosen by the client)
Response = b64( <36 bytes header> + AES-CBC(ciphertext) ), plaintext = LZ4(msgpack) or raw msgpack.

key = md5(bytes.fromhex(SID_header) + SALT)
iv  = md5(udid16 + SALT)

SID_header is the value of the request's "SID" HTTP header for that same flow.
udid16 is recovered from the request body itself (no external secret needed).
"""
import base64
import hashlib
import struct

import lz4.frame
import msgpack
from Crypto.Cipher import AES

SALT = bytes.fromhex("7a5adef05e2b499331474ca734f627f53c9030ca")
XOR_KEY = bytes.fromhex("dc3c456b597fdfb4e59a5fae0ea380453826699deec59696293394cfdd77de46")


def _unpack(plaintext: bytes):
    payload = lz4.frame.decompress(plaintext) if plaintext[:4] == b"\x04\x22\x4d\x18" else plaintext
    unpacker = msgpack.Unpacker(raw=False, strict_map_key=False, max_buffer_size=32 * 1024 * 1024)
    unpacker.feed(payload)
    return unpacker.unpack()


def recover_udid16(sid_header_hex: str, request_body_b64: str) -> bytes:
    raw = base64.b64decode(request_body_b64.strip() + "==")
    flag = struct.unpack("<I", raw[:4])[0]
    if flag != 64:
        raise ValueError(f"request flag != 64 (got {flag}); not a game API body")
    blob1 = raw[4:68]
    rk = blob1[32:64]
    return bytes(blob1[16 + i] ^ rk[16 + i] ^ XOR_KEY[16 + i] for i in range(16))


def derive_key_iv(sid_header_hex: str, udid16: bytes):
    key = hashlib.md5(bytes.fromhex(sid_header_hex) + SALT).digest()
    iv = hashlib.md5(udid16 + SALT).digest()
    return key, iv


def decrypt_response(sid_header_hex: str, request_body_b64: str, response_body_b64: str):
    udid16 = recover_udid16(sid_header_hex, request_body_b64)
    key, iv = derive_key_iv(sid_header_hex, udid16)
    raw = base64.b64decode(response_body_b64.strip() + "==")
    plaintext = AES.new(key, AES.MODE_CBC, iv).decrypt(raw[36:])
    return _unpack(plaintext)


def decrypt_request(sid_header_hex: str, request_body_b64: str):
    udid16 = recover_udid16(sid_header_hex, request_body_b64)
    key, iv = derive_key_iv(sid_header_hex, udid16)
    raw = base64.b64decode(request_body_b64.strip() + "==")
    ciphertext = raw[68:]
    plaintext = AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext)
    plaintext = plaintext[: -plaintext[-1]]  # pkcs7 unpad
    return _unpack(plaintext)
