#!/usr/bin/env python3
"""The secrets a switch's configuration needs, from a file.

swboot puts six secrets into what it generates: the radius key, the
local login's name and password, the enable password, the SNMP read
community and the salt of the per-switch SNMP write community. They
are not kept in config.py: a JSON file holds them (SECRETS_FILE, or
`secrets_file` in config.py), written by whoever looks after secrets on
the server and readable by swboot alone:

    {"radius": "...", "username": "...", "password": "...",
     "enable": "...", "snmp_ro": "...", "snmp_salt": "..."}

A missing file, a missing name or an empty value is an error - a
switch must never be configured with an empty password.
"""

import json

SECRETS_FILE = '/etc/swboot/secrets.json'
NAMES = ('radius', 'username', 'password', 'enable', 'snmp_ro', 'snmp_salt')


class SecretsError(Exception):
  pass


def load(path=SECRETS_FILE):
  """{name: value} for the six NAMES, every one a non-empty string."""
  try:
    with open(path) as handle:
      data = json.load(handle)
  except OSError as error:
    raise SecretsError('the secrets file %s cannot be read (%s)'
                       % (path, error.strerror or error))
  except ValueError:
    raise SecretsError('the secrets file %s is not JSON' % path)
  if not isinstance(data, dict):
    raise SecretsError('the secrets file %s is not a JSON object' % path)
  missing = [name for name in NAMES
             if not isinstance(data.get(name), str) or not data[name]]
  if missing:
    # the names only - never a value
    raise SecretsError('the secrets file %s lacks %s'
                       % (path, ', '.join(missing)))
  return {name: data[name] for name in NAMES}
