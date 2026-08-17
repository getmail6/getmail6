# -*- coding: utf-8 -*-
# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

# Copied under
# Apache License 2.0
# https://github.com/ikvk/imap_tools/blob/master/LICENSE
# from
# https://github.com/ikvk/imap_tools/blob/master/imap_tools/imap_utf7.py
# just changing the return value of utf7_encode() and utf7_decode()

import codecs

import binascii
from typing import MutableSequence

AMPERSAND_ORD = ord('&')
HYPHEN_ORD = ord('-')

def _modified_base64(value: str) -> bytes:
    return binascii.b2a_base64(value.encode('utf-16be')).rstrip(b'\n=').replace(b'/', b',')
def _do_b64(_in: MutableSequence[str], r: MutableSequence[bytes]):
    if _in:
        r.append(b'&' + _modified_base64(''.join(_in)) + b'-')
    _in.clear()
def utf7_encode(value: str) -> bytes:
    res = []
    _in = []
    for char in value:
        ord_c = ord(char)
        if 0x20 <= ord_c <= 0x25 or 0x27 <= ord_c <= 0x7e:
            _do_b64(_in, res)
            res.append(char.encode())
        elif char == '&':
            _do_b64(_in, res)
            res.append(b'&-')
        else:
            _in.append(char)
    _do_b64(_in, res)
    return b''.join(res), len(value)


def _modified_unbase64(value: bytearray) -> str:
    return binascii.a2b_base64(value.replace(b',', b'/') + b'===').decode('utf-16be')
def utf7_decode(value: bytes) -> str:
    res = []
    encoded_chars = bytearray()
    for char in value:
        if char == AMPERSAND_ORD and not encoded_chars:
            encoded_chars.append(AMPERSAND_ORD)
        elif char == HYPHEN_ORD and encoded_chars:
            if len(encoded_chars) == 1:
                res.append('&')
            else:
                res.append(_modified_unbase64(encoded_chars[1:]))
            encoded_chars = bytearray()
        elif encoded_chars:
            encoded_chars.append(char)
        else:
            res.append(chr(char))
    if encoded_chars:
        res.append(_modified_unbase64(encoded_chars[1:]))
    return ''.join(res), len(value)

class StreamReader(codecs.StreamReader):
    def decode(self, s, errors='strict'):
        return utf7_decode(s)

class StreamWriter(codecs.StreamWriter):
    def encode(self, s, errors='strict'):
        return utf7_encode(s)

_codecInfo = codecs.CodecInfo(utf7_encode, utf7_decode, StreamReader, StreamWriter)

def utf_7_imap(name):
    if name in {'imap4-utf-7','imap4_utf_7'}:
        return _codecInfo

codecs.register(utf_7_imap)
