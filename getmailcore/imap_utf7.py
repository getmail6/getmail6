# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

"""
Modified utf-7 encoding as used in IMAP v4r1 for encoding mailbox names.

From the RFC:

5.1.3.  Mailbox International Naming Convention

   By convention, international mailbox names are specified using a
   modified version of the UTF-7 encoding described in [UTF-7].  The
   purpose of these modifications is to correct the following problems
   with UTF-7:

      1) UTF-7 uses the "+" character for shifting; this conflicts with
         the common use of "+" in mailbox names, in particular USENET
         newsgroup names.

      2) UTF-7's encoding is BASE64 which uses the "/" character; this
         conflicts with the use of "/" as a popular hierarchy delimiter.

      3) UTF-7 prohibits the unencoded usage of "\"; this conflicts with
         the use of "\" as a popular hierarchy delimiter.

      4) UTF-7 prohibits the unencoded usage of "~"; this conflicts with
         the use of "~" in some servers as a home directory indicator.

      5) UTF-7 permits multiple alternate forms to represent the same
         string; in particular, printable US-ASCII chararacters can be
         represented in encoded form.

   In modified UTF-7, printable US-ASCII characters except for "&"
   represent themselves; that is, characters with octet values 0x20-0x25
   and 0x27-0x7e.  The character "&" (0x26) is represented by the two-
   octet sequence "&-".

   All other characters (octet values 0x00-0x1f, 0x7f-0xff, and all
   Unicode 16-bit octets) are represented in modified BASE64, with a
   further modification from [UTF-7] that "," is used instead of "/".
   Modified BASE64 MUST NOT be used to represent any printing US-ASCII
   character which can represent itself.

   "&" is used to shift to modified BASE64 and "-" to shift back to US-
   ASCII.  All names start in US-ASCII, and MUST end in US-ASCII (that
   is, a name that ends with a Unicode 16-bit octet MUST end with a "-
   ").
"""

# From https://github.com/twisted/twisted/blob/trunk/src/twisted/mail/imap4.py.

# we need to cast Python >=3.3 memoryview to chars (from unsigned bytes), but
# cast is absent in previous versions: thus, the lambda returns the
# memoryview instance while ignoring the format

import codecs

memory_cast = getattr(memoryview, "cast", lambda *x: x[0])

def modified_base64(s):
    s_utf7 = s.encode('utf-7')
    return s_utf7[1:-1].replace(b'/', b',')

def modified_unbase64(s):
    s_utf7 = b'+' + s.replace(b',', b'/') + b'-'
    return s_utf7.decode('utf-7')

def encoder(s, errors=None):
    """
    Encode the given C{unicode} string using the IMAP4 specific variation of
    UTF-7.
    @type s: C{unicode}
    @param s: The text to encode.
    @param errors: Policy for handling encoding errors.  Currently ignored.
    @return: L{tuple} of a L{str} giving the encoded bytes and an L{int}
        giving the number of code units consumed from the input.
    """
    r = bytearray()
    _in = []
    valid_chars = set(map(chr, range(0x20,0x7f))) - {u"&"}
    for c in s:
        if c in valid_chars:
            if _in:
                r += b'&' + modified_base64(''.join(_in)) + b'-'
                del _in[:]
            r.append(ord(c))
        elif c == u'&':
            if _in:
                r += b'&' + modified_base64(''.join(_in)) + b'-'
                del _in[:]
            r += b'&-'
        else:
            _in.append(c)
    if _in:
        r.extend(b'&' + modified_base64(''.join(_in)) + b'-')
    return (bytes(r), len(s))

def decoder(s, errors=None):
    """
    Decode the given L{str} using the IMAP4 specific variation of UTF-7.
    @type s: L{str}
    @param s: The bytes to decode.
    @param errors: Policy for handling decoding errors.  Currently ignored.
    @return: a L{tuple} of a C{unicode} string giving the text which was
        decoded and an L{int} giving the number of bytes consumed from the
        input.
    """
    r = []
    decode = []
    s = memory_cast(memoryview(s), 'c')
    for c in s:
        if c == b'&' and not decode:
            decode.append(b'&')
        elif c == b'-' and decode:
            if len(decode) == 1:
                r.append(u'&')
            else:
                r.append(modified_unbase64(b''.join(decode[1:])))
            decode = []
        elif decode:
            decode.append(c)
        else:
            r.append(c.decode())
    if decode:
        r.append(modified_unbase64(b''.join(decode[1:])))
    return (u''.join(r), len(s))

class StreamReader(codecs.StreamReader):
    def decode(self, s, errors='strict'):
        return decoder(s)

class StreamWriter(codecs.StreamWriter):
    def encode(self, s, errors='strict'):
        return encoder(s)

_codecInfo = codecs.CodecInfo(encoder, decoder, StreamReader, StreamWriter)

def imap4_utf_7(name):
    if name == 'imap4-utf-7' or name == 'imap4_utf_7':
        return _codecInfo

codecs.register(imap4_utf_7)
