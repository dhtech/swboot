# swhttpd's answers to a Juniper switch, with stand-ins for redis and the
# configuration (no server is started: swhttpd only listens when run).
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class FakeRedis:
  """What swhttpd asks of redis: get, and set with nx/ex."""
  store = {}

  def __init__(self, *args, **kwargs):
    pass

  def get(self, key):
    value = self.store.get(key)
    return value.encode() if isinstance(value, str) else value

  def set(self, key, value, ex=None, nx=False):
    if nx and key in self.store:
      return None
    self.store[key] = value
    return True


class Model(dict):
  """A models entry as config.py builds it (tempita's bunch is a dict)."""
  def __getattr__(self, name):
    return self[name]


@pytest.fixture
def swhttpd(monkeypatch):
  FakeRedis.store = {}
  config = types.ModuleType('config')
  config.models = {'Juniper-ex3400-24t': Model(template='/t/ex3400.cfg', eth=24)}
  config.generate = lambda switch, model: 'config for %s (%s)\n' % (switch, model)
  config.static_configs = '/nonexistent'
  monkeypatch.setitem(sys.modules, 'config', config)
  monkeypatch.setitem(sys.modules, 'redis', types.SimpleNamespace(Redis=FakeRedis))
  monkeypatch.delitem(sys.modules, 'swhttpd', raising=False)
  import swhttpd
  said = []
  monkeypatch.setattr(swhttpd, 'error', lambda *a: said.append(('error', ' '.join(a))))
  monkeypatch.setattr(swhttpd, 'log', lambda *a: said.append(('log', ' '.join(a))))
  swhttpd.said = said
  swhttpd.config = config
  return swhttpd


def ask(swhttpd, path, ip='192.0.2.10'):
  """One GET as the switch at IP; returns (status, body)."""
  handler = swhttpd.swbootHttpHandler.__new__(swhttpd.swbootHttpHandler)
  handler.client_address = (ip, 1234)
  handler.path = path
  answer = {'status': None, 'body': b''}
  handler.send_error = lambda code, message=None: answer.update(status=code)
  handler.send_response = lambda code: answer.update(status=code)
  handler.send_header = lambda *a: None
  handler.end_headers = lambda: None
  handler.copyfile = lambda f, out: answer.update(body=f.read())
  handler.wfile = None
  handler.do_GET()
  return answer['status'], answer['body']


def switch(model, sw_type='TABLE', ip='192.0.2.10', name='D23-A'):
  FakeRedis.store.update({ip: name, 'client-' + ip: model, 'type-' + ip: sw_type})


def test_a_known_model_gets_its_config(swhttpd):
  switch('Juniper-ex3400-24t')
  status, body = ask(swhttpd, '/juniper-confg')
  assert status == 200
  assert body == b'config for D23-A (Juniper-ex3400-24t)\n'


def test_an_unknown_model_is_said_once_and_not_a_crash(swhttpd):
  switch('Juniper-ex4300-24t')
  # the switch asks again and again - one error line, a 404 each time
  for _ in range(3):
    status, _ = ask(swhttpd, '/juniper-confg')
    assert status == 404
  errors = [text for kind, text in swhttpd.said if kind == 'error']
  assert len(errors) == 1
  assert 'Juniper-ex4300-24t' in errors[0] and 'D23-A' in errors[0]
  assert 'switchconfig/config.yaml' in errors[0]


def test_each_switch_with_an_unknown_model_is_said(swhttpd):
  switch('Juniper-ex4300-24t', ip='192.0.2.10', name='D23-A')
  switch('Juniper-ex4300-24t', ip='192.0.2.11', name='D24-A')
  ask(swhttpd, '/juniper-confg', ip='192.0.2.10')
  ask(swhttpd, '/juniper-confg', ip='192.0.2.11')
  errors = [text for kind, text in swhttpd.said if kind == 'error']
  assert len(errors) == 2


def test_an_unknown_model_asking_for_junos_is_said_not_a_crash(swhttpd):
  switch('Juniper-ex4300-24t')
  status, _ = ask(swhttpd, '/juniper.tgz')
  assert status == 404
  assert any(kind == 'error' for kind, _ in swhttpd.said)


def test_a_model_without_an_image_is_said_not_a_crash(swhttpd):
  switch('Juniper-ex3400-24t')
  status, _ = ask(swhttpd, '/juniper.tgz')
  assert status == 404
  assert any(kind == 'error' and 'No JunOS image' in text
             for kind, text in swhttpd.said)


def test_a_failing_generation_is_a_500_not_a_crash(swhttpd):
  def broken(switch, model):
    raise Exception('The switch D23-A was not found in ipplan')
  swhttpd.config.generate = broken
  switch('Juniper-ex3400-24t')
  status, _ = ask(swhttpd, '/juniper-confg')
  assert status == 500
  assert any(kind == 'error' and 'not found in ipplan' in text
             for kind, text in swhttpd.said)


def test_an_unknown_switch_is_a_404_not_a_crash(swhttpd):
  status, _ = ask(swhttpd, '/juniper-confg', ip='192.0.2.99')
  assert status == 404


def test_a_static_config_needs_no_model_entry(swhttpd, tmp_path):
  # ACCESS switches get a file as it is; their model is not looked up
  swhttpd.config.static_configs = str(tmp_path)
  (tmp_path / 'd23-a.txt').write_text('static config\n')
  switch('Juniper-ex4300-24t', sw_type='ACCESS')
  status, body = ask(swhttpd, '/juniper-confg')
  assert status == 200
  assert body == b'static config\n'
  assert not any(kind == 'error' for kind, _ in swhttpd.said)
