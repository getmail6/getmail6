import pytest

from getmailcore.exceptions import getmailConfigurationError
from getmailcore.utilities import check_ssl_fingerprints

GOOD = 'ab' * 32


def test_accepts_hex_with_or_without_colons():
    colons = ':'.join(['AB'] * 32)
    assert check_ssl_fingerprints({'ssl_fingerprints': (colons, GOOD)}) == [GOOD, GOOD]


@pytest.mark.parametrize('fpr', ['zz' * 32, 'ab' * 31 + 'g1', 'ab' * 31 + '  '])
def test_rejects_non_hex_fingerprint(fpr):
    with pytest.raises(getmailConfigurationError):
        check_ssl_fingerprints({'ssl_fingerprints': (fpr,)})
