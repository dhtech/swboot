"""The few SNMP questions swboot asks.

swboot was written for the Net-SNMP project's own Python binding,
"netsnmp" - on PyPI as python3-netsnmp (github.com/bluecmd/python3-netsnmp;
it is compiled against libsnmp when installed). That is what is used
when it is there. Where it is not, the same questions go through
python3-ezsnmp or its ancestor python3-easysnmp (both packaged by
Debian, same interface).

Whatever the library, the answer is the same: text, or None for "no
answer" (the switch is away, does not know the object, refuses the
credentials) - never an exception.

  session = swsnmp.v2('192.168.0.7', 'private')
  swsnmp.get(session, '.1.3.6.1.2.1.47.1.1.1.1.13.1')    -> 'WS-C2950T-24'
  swsnmp.walk(session, '.1.3.6.1.2.1.31.1.1.1.1')        -> [('10101', 'Gi1/0/1'), ...]
"""

try:
  import netsnmp
except ImportError:
  netsnmp = None
  try:
    from ezsnmp import Session
  except ImportError:
    from easysnmp import Session

LIBRARY = 'netsnmp' if netsnmp is not None else 'ezsnmp'
NOTHING = ('NOSUCHOBJECT', 'NOSUCHINSTANCE', 'ENDOFMIBVIEW')


def _text(value):
  """An answer as text (netsnmp gives bytes)."""
  if value is None:
    return None
  if isinstance(value, bytes):
    value = value.decode('utf-8', 'replace')
  return value


def _last(*parts):
  """The last number of an OID that the library may have split into a
  name and an index (it does so differently for names and numbers)."""
  oid = '.'.join(p for p in parts if p)
  return oid.rsplit('.', 1)[-1]


def v2(host, community):
  """How to ask HOST with SNMPv2c."""
  if netsnmp is not None:
    return {'Version': 2, 'DestHost': host, 'Community': community}
  return Session(hostname=host, version=2, community=community,
                 use_numeric=True)


def v3(host, username, auth, priv):
  """How to ask HOST with SNMPv3: SHA authentication, AES (128)
  privacy - what the dist layer runs."""
  if netsnmp is not None:
    return {'Version': 3, 'DestHost': host, 'SecName': username,
            'SecLevel': 'authPriv', 'AuthProto': 'SHA', 'AuthPass': auth,
            'PrivProto': 'AES128', 'PrivPass': priv}
  return Session(hostname=host, version=3, security_level='auth_with_privacy',
                 security_username=username,
                 auth_protocol='SHA', auth_password=auth,
                 privacy_protocol='AES', privacy_password=priv,
                 use_numeric=True)


def get(session, oid):
  """The value of OID as text, or None."""
  try:
    if netsnmp is not None:
      return _text(netsnmp.snmpget(netsnmp.Varbind(oid), **session)[0])
    variable = session.get(oid)
    if variable is None or variable.snmp_type in NOTHING:
      return None
    return _text(variable.value)
  except Exception:
    return None


def walk(session, oid):
  """[(index, value)] below OID, or None when the switch did not
  answer."""
  try:
    if netsnmp is not None:
      found = netsnmp.VarList(netsnmp.Varbind(oid))
      if netsnmp.snmpwalk(found, **session) is None:
        return None
      return [(_last(v.tag, v.iid), _text(v.val)) for v in found
              if v.val is not None]
    return [(_last(v.oid, v.oid_index), _text(v.value))
            for v in session.walk(oid) if v.snmp_type not in NOTHING]
  except Exception:
    return None
