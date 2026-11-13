# The SNMP questions, with stand-ins for the libraries (neither netsnmp
# nor ezsnmp is needed to run the tests).
import os
import sys
import types
from collections import namedtuple

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

MODEL = '.1.3.6.1.2.1.47.1.1.1.1.13.1'
NAMES = '.1.3.6.1.2.1.31.1.1.1.1'


def load(monkeypatch, **modules):
  """swsnmp, imported with only MODULES as SNMP libraries."""
  for name in ('netsnmp', 'ezsnmp', 'easysnmp'):
    # None in sys.modules makes "import name" fail
    monkeypatch.setitem(sys.modules, name, modules.get(name))
  monkeypatch.delitem(sys.modules, 'swsnmp', raising=False)
  import swsnmp
  return swsnmp


# --- netsnmp (python3-netsnmp from PyPI): the binding swboot was written for

class Varbind:
  def __init__(self, tag=None, iid=None, val=None):
    self.tag, self.iid, self.val = tag, iid, val


class FakeNetsnmp:
  """Answers like the binding: bytes, None for nothing; a walk fills
  the list it was given."""

  def __init__(self):
    self.asked = []
    self.values = {}
    self.interfaces = []
    self.away = False
    self.Varbind = Varbind
    self.VarList = lambda *v: list(v)

  def snmpget(self, var, **how):
    self.asked.append(('get', var.tag, how))
    return (None if self.away else self.values.get(var.tag),)

  def snmpwalk(self, varlist, **how):
    self.asked.append(('walk', varlist[0].tag, how))
    if self.away:
      return None
    varlist[:] = [Varbind(tag, iid, val) for tag, iid, val in self.interfaces]
    return tuple(v.val for v in varlist)


def test_netsnmp_is_used_when_it_is_there(monkeypatch):
  lib = FakeNetsnmp()
  swsnmp = load(monkeypatch, netsnmp=lib,
                ezsnmp=types.SimpleNamespace(Session=None))
  assert swsnmp.LIBRARY == 'netsnmp'
  session = swsnmp.v2('192.168.0.7', 'private')
  lib.values[MODEL] = b'WS-C2950T-24'
  assert swsnmp.get(session, MODEL) == 'WS-C2950T-24'      # text, not bytes
  assert swsnmp.get(session, MODEL + '001') is None
  # asked exactly as swtftpd always asked
  assert lib.asked[0] == ('get', MODEL, {'Version': 2,
                                         'DestHost': '192.168.0.7',
                                         'Community': 'private'})
  lib.away = True
  assert swsnmp.get(session, MODEL) is None


def test_netsnmp_v3_and_the_walk(monkeypatch):
  lib = FakeNetsnmp()
  swsnmp = load(monkeypatch, netsnmp=lib)
  session = swsnmp.v3('dist-a', 'user', 'auth-word', 'priv-word')
  assert session == {'Version': 3, 'DestHost': 'dist-a', 'SecName': 'user',
                     'SecLevel': 'authPriv', 'AuthProto': 'SHA',
                     'AuthPass': 'auth-word', 'PrivProto': 'AES128',
                     'PrivPass': 'priv-word'}
  lib.interfaces = [('ifName', '10101', b'Gi1/0/1'),           # a name and an index
                    (NAMES + '.10102', '', b'Gi1/0/2'),        # or all in the tag
                    (NAMES, '10103', None)]
  assert swsnmp.walk(session, NAMES) == [('10101', 'Gi1/0/1'),
                                         ('10102', 'Gi1/0/2')]
  lib.away = True
  assert swsnmp.walk(session, NAMES) is None


# --- ezsnmp / easysnmp (Debian's): when netsnmp is not installed -----------

Variable = namedtuple('Variable', 'oid oid_index value snmp_type')


class FakeSession:
  def __init__(self, **how):
    self.how = how
    self.answers = {}
    self.away = False

  def get(self, oid):
    if self.away:
      raise RuntimeError('timed out')
    return self.answers.get(oid, Variable(oid, '', 'NOSUCHINSTANCE',
                                          'NOSUCHINSTANCE'))

  def walk(self, oid):
    if self.away:
      raise RuntimeError('timed out')
    return self.answers.get(oid, [])


@pytest.fixture(params=['ezsnmp', 'easysnmp'])
def swsnmp(request, monkeypatch):
  module = load(monkeypatch, **{request.param: types.SimpleNamespace(
      Session=FakeSession)})
  assert module.LIBRARY == 'ezsnmp'
  return module


def test_without_netsnmp_v2_asks_with_the_community(swsnmp):
  session = swsnmp.v2('192.168.0.7', 'private')
  assert session.how == {'hostname': '192.168.0.7', 'version': 2,
                         'community': 'private', 'use_numeric': True}


def test_without_netsnmp_v3_asks_with_sha_and_aes(swsnmp):
  how = swsnmp.v3('dist-a', 'user', 'auth-word', 'priv-word').how
  assert how['version'] == 3 and how['security_level'] == 'auth_with_privacy'
  assert (how['security_username'], how['auth_protocol'], how['auth_password'],
          how['privacy_protocol'], how['privacy_password']) == (
              'user', 'SHA', 'auth-word', 'AES', 'priv-word')


def test_without_netsnmp_get_is_text_or_none(swsnmp):
  session = swsnmp.v2('192.168.0.7', 'private')
  session.answers[MODEL] = Variable(MODEL, '', 'WS-C2950T-24', 'OCTETSTR')
  assert swsnmp.get(session, MODEL) == 'WS-C2950T-24'
  assert swsnmp.get(session, MODEL + '001') is None      # no such instance
  session.away = True
  assert swsnmp.get(session, MODEL) is None              # no answer, no exception


def test_without_netsnmp_walk_gives_the_last_number_and_the_value(swsnmp):
  session = swsnmp.v3('dist-a', 'user', 'a', 'p')
  session.answers[NAMES] = [
      Variable(NAMES, '10101', 'Gi1/0/1', 'OCTETSTR'),       # split by the library
      Variable(NAMES + '.10102', '', 'Gi1/0/2', 'OCTETSTR'),  # or not
      Variable(NAMES, '', '', 'ENDOFMIBVIEW')]
  assert swsnmp.walk(session, NAMES) == [('10101', 'Gi1/0/1'),
                                         ('10102', 'Gi1/0/2')]
  session.away = True
  assert swsnmp.walk(session, NAMES) is None


def test_no_library_at_all_is_an_import_error(monkeypatch):
  with pytest.raises(ImportError):
    load(monkeypatch)
