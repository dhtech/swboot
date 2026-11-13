# The plan database holds every site; swboot answers for one. Run with
#   python3 -m pytest tests

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import ipplan  # noqa: E402

NETWORKS = [
    # node_id, name, short_name, vlan, ipv4_txt, ipv4_gateway_txt
    (1, 'EVENT@TECH-SRV-A', 'TECH-SRV-A', 910, '10.1.0.0/24', '10.1.0.1'),
    (2, 'EVENT@D-SW-BOOT', 'D-SW-BOOT', 610, '192.168.0.0/24', '192.168.0.1'),
    (3, 'EVENT@D-ACCESS-MGMT', 'D-ACCESS-MGMT', 650, '10.9.0.0/24', '10.9.0.1'),
    (4, 'EVENT@D23', 'D23', 123, '10.50.23.0/24', '10.50.23.1'),
    (5, 'COLO@SERVERS', 'SERVERS', 300, '10.2.0.0/24', '10.2.0.1'),
    # another site that happens to use the same boot addresses and has
    # a switch of the same name
    (6, 'COLO@LAB-SW-BOOT', 'LAB-SW-BOOT', 611, '192.168.0.0/24', '192.168.0.1'),
    (7, 'COLO@LAB-MGMT', 'LAB-MGMT', 651, '10.8.0.0/24', '10.8.0.1'),
    (8, 'COLO@D23', 'D23', 923, '10.60.23.0/24', '10.60.23.1'),
]
HOSTS = [
    # node_id, name, ipv4, ipv6, network_id, packages
    (10, 'swboot.event.test', '10.1.0.28', None, 1, ['swbootd']),
    (11, 'ntp1.event.test', '10.1.0.19', '2001:db8::19', 1, ['ntpd']),
    (12, 'ntp2.event.test', '10.1.0.20', None, 1, ['ntpd']),
    (13, 'jumpgate1.event.test', '10.1.0.17', None, 1, ['jumpgate']),
    (14, 'd23-a.event.dreamhack.local', '10.9.0.23', None, 3, []),
    (20, 'jumpgate1.colo.test', '10.2.0.13', None, 5, ['jumpgate']),
    (21, 'r1.colo.test', '10.2.0.1', None, 5, ['ntpd', 'router']),
    (22, 'd23-a.lab.dreamhack.local', '10.8.0.23', None, 7, []),
]
# node_id (of the network a switch serves), switch_name
SWITCHES = [(8, 'd23-a.lab.dreamhack.local'),
            (4, 'd23-a.event.dreamhack.local')]


@pytest.fixture
def db(tmp_path):
  path = str(tmp_path / 'ipplan.db')
  conn = sqlite3.connect(path)
  conn.executescript('''
    CREATE TABLE network(node_id, name, short_name, vlan, ipv4_txt,
                         ipv4_gateway_txt);
    CREATE TABLE host(node_id, name, ipv4_addr_txt, ipv6_addr_txt,
                      network_id);
    CREATE TABLE package(node_id, name);
    CREATE TABLE active_switch(node_id, switch_name);
  ''')
  conn.executemany('INSERT INTO network VALUES (?, ?, ?, ?, ?, ?)', NETWORKS)
  for node_id, name, v4, v6, network_id, packages in HOSTS:
    conn.execute('INSERT INTO host VALUES (?, ?, ?, ?, ?)',
                 (node_id, name, v4, v6, network_id))
    conn.executemany('INSERT INTO package VALUES (?, ?)',
                     [(node_id, p) for p in packages])
  conn.executemany('INSERT INTO active_switch VALUES (?, ?)', SWITCHES)
  conn.commit()
  conn.close()
  return path


def test_a_package_is_the_sites_hosts_and_no_others(db):
  assert [h.name for h in ipplan.package('ntpd', 'EVENT', db)] == [
      'ntp1.event.test', 'ntp2.event.test']
  assert [h.name for h in ipplan.package('jumpgate', 'EVENT', db)] == [
      'jumpgate1.event.test']
  # the other site has hosts with the same packages: they are its own
  assert [h.name for h in ipplan.package('ntpd', 'COLO', db)] == [
      'r1.colo.test']
  assert [h.name for h in ipplan.package('jumpgate', 'COLO', db)] == [
      'jumpgate1.colo.test']
  # addresses come along; nothing for a package or a site nobody has
  assert ipplan.package('ntpd', 'EVENT', db)[0] == ipplan.Host(
      'ntp1.event.test', '10.1.0.19', '2001:db8::19')
  assert ipplan.package('nothing', 'EVENT', db) == []
  assert ipplan.package('ntpd', 'ELSEWHERE', db) == []


def test_a_host_by_name_is_that_host(db):
  assert ipplan.host('jumpgate1.colo.test', db).ipv4 == '10.2.0.13'
  with pytest.raises(Exception, match='not in ipplan'):
    ipplan.host('nobody.test', db)


def test_a_switch_is_looked_up_in_its_own_site(db):
  # both sites have a "D23-A"; each gets its own
  event = ipplan.switch('D23-A', 'EVENT', db)
  assert event == ipplan.Switch('10.9.0.0/24', '10.9.0.23', '10.9.0.1',
                                650, 123)
  colo = ipplan.switch('D23-A', 'COLO', db)
  assert (colo.ip, colo.mgmt_vlan, colo.vlan) == ('10.8.0.23', 651, 923)
  assert ipplan.switch('D99-A', 'EVENT', db) is None
  assert ipplan.switch('D23-A', 'ELSEWHERE', db) is None


def test_a_relay_is_looked_up_in_its_own_site(db):
  # the same gateway address in two sites
  assert ipplan.network_by_gateway('192.168.0.1', 'EVENT', db) == 'D-SW-BOOT'
  assert ipplan.network_by_gateway('192.168.0.1', 'COLO', db) == 'LAB-SW-BOOT'
  assert ipplan.network_by_gateway('192.168.77.1', 'EVENT', db) is None


def test_the_site_served_is_the_servers_own(db, tmp_path):
  none = str(tmp_path / 'no-such-file')
  assert ipplan.site_of_host('swboot.event.test', db) == 'EVENT'
  assert ipplan.own_site(db, 'swboot.event.test', none) == 'EVENT'
  assert ipplan.own_site(db, 'r1.colo.test', none) == 'COLO'
  # a machine the plan does not have serves no site: an error, never
  # "every site"
  with pytest.raises(LookupError, match='does not know its site'):
    ipplan.own_site(db, 'laptop.test', none)
  # ... unless the file names one
  named = tmp_path / 'site'
  named.write_text('event\n')
  assert ipplan.own_site(db, 'laptop.test', str(named)) == 'EVENT'
  named.write_text('\n')
  assert ipplan.own_site(db, 'swboot.event.test', str(named)) == 'EVENT'
