# The six secrets come from a JSON file; anything less than all six,
# non-empty, is an error that names what is missing and never a value.

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import swsecrets  # noqa: E402

GOOD = {'radius': 'r-key', 'username': 'dhtech', 'password': 'p-word',
        'enable': 'e-word', 'snmp_ro': 'c0mmunity', 'snmp_salt': 's4lt-value'}


def write(tmp_path, data):
  path = tmp_path / 'secrets.json'
  path.write_text(data if isinstance(data, str) else json.dumps(data))
  return str(path)


def test_all_six_are_read(tmp_path):
  assert swsecrets.load(write(tmp_path, dict(GOOD, extra='x'))) == GOOD


@pytest.mark.parametrize('name', swsecrets.NAMES)
def test_a_missing_or_empty_one_is_an_error(tmp_path, name):
  for bad in (None, '', 7):
    data = dict(GOOD)
    if bad is None:
      del data[name]
    else:
      data[name] = bad
    with pytest.raises(swsecrets.SecretsError) as caught:
      swsecrets.load(write(tmp_path, data))
    message = str(caught.value)
    assert name in message
    # what is there is not repeated
    assert not [v for v in GOOD.values() if v in message]


def test_no_file_or_not_json_is_an_error(tmp_path):
  with pytest.raises(swsecrets.SecretsError, match='cannot be read'):
    swsecrets.load(str(tmp_path / 'nothing'))
  with pytest.raises(swsecrets.SecretsError, match='not JSON'):
    swsecrets.load(write(tmp_path, 'radius = x'))
  with pytest.raises(swsecrets.SecretsError, match='not a JSON object'):
    swsecrets.load(write(tmp_path, '["a"]'))
