#!/usr/bin/env python3
"""What swboot asks the plan database (/etc/ipplan.db) - by SITE.

The plan holds every site: the event's network, and the datacentre
sites that are there all year. A switch that boots at the event must be
told about the event's servers and no others - its time servers, its
resolvers, the jumpgates its access list admits. So every lookup by
package, by switch name or by gateway address takes the site and
answers for that site alone.

A site is what the plan calls it: the part before the "@" of a network's
name ("EVENT@TECH-SRV-A" is in site EVENT). A host is in the site of the
network its plan line stands under.

The site swboot serves is its own: the site of this machine, found by
its own name in the plan (own_site). A file /etc/swboot/site holding a
site's name overrides that, for a machine that is not in the plan.
"""

import os
import socket
import sqlite3
from collections import namedtuple

DB = '/etc/ipplan.db'
SITE_FILE = '/etc/swboot/site'

Host = namedtuple('Host', 'name ipv4 ipv6')
Switch = namedtuple('Switch', 'network ip gateway mgmt_vlan vlan')


def _site(network_name):
  """'EVENT@TECH-SRV-A' -> 'EVENT'; a name without a site -> None."""
  if not network_name or '@' not in network_name:
    return None
  return network_name.split('@', 1)[0]


def _rows(db, sql, args=()):
  conn = sqlite3.connect(db)
  try:
    return conn.execute(sql, args).fetchall()
  finally:
    conn.close()


def site_of_host(hostname, db=DB):
  """The site HOSTNAME's plan line is in, or None when the plan does not
  have the host."""
  rows = _rows(db, '''SELECT n.name FROM host AS h, network AS n
                      WHERE h.name = ? AND n.node_id = h.network_id''',
               (hostname,))
  return _site(rows[0][0]) if rows else None


def own_site(db=DB, hostname=None, site_file=SITE_FILE):
  """The site this server serves: the one named in SITE_FILE if that
  file is there, else this machine's own site by its name in the plan.
  No site is an error - a lookup without one would answer for every
  site at once."""
  try:
    with open(site_file) as handle:
      named = handle.read().strip()
    if named:
      return named.upper()
  except OSError:
    pass
  hostname = hostname or socket.getfqdn()
  site = site_of_host(hostname, db)
  if site is None:
    raise LookupError(
        'swboot does not know its site: %s is not in %s and %s names none'
        % (hostname, db, site_file))
  return site


def host(hostname, db=DB):
  """The host of that exact name, wherever it is - a template that
  names a machine means that machine."""
  rows = _rows(db, '''SELECT h.name, h.ipv4_addr_txt, h.ipv6_addr_txt
                      FROM host AS h WHERE h.name = ?''', (hostname,))
  if not rows:
    raise Exception('No IPv4 address found for host %s not in ipplan'
                    % hostname)
  return Host(*rows[0])


def package(package_name, site, db=DB):
  """The hosts of SITE that carry the package, sorted by name. Hosts of
  other sites with the same package are not in the answer."""
  rows = _rows(db, '''SELECT h.name, h.ipv4_addr_txt, h.ipv6_addr_txt, n.name
                      FROM host AS h
                      INNER JOIN package AS p ON p.node_id = h.node_id
                      INNER JOIN network AS n ON n.node_id = h.network_id
                      WHERE p.name = ?''', (package_name,))
  hosts = {Host(name, ipv4, ipv6) for name, ipv4, ipv6, network in rows
           if _site(network) == site}
  return sorted(hosts, key=lambda e: e.name)


def switch(name, site, db=DB):
  """The switch of SITE whose name starts with NAME (the option 82
  name, e.g. "D23-A"): its management network, address and gateway, the
  management network's VLAN and the VLAN of the network it serves. None
  when SITE has no such switch."""
  rows = _rows(db, '''SELECT n_mgmt.ipv4_txt, h.ipv4_addr_txt,
                             n_mgmt.ipv4_gateway_txt, n_mgmt.vlan, n.vlan,
                             n.name
                      FROM active_switch AS s, network AS n, host AS h,
                           network AS n_mgmt
                      WHERE s.switch_name LIKE ? AND n.node_id = s.node_id
                        AND h.name = s.switch_name
                        AND n_mgmt.node_id = h.network_id''',
               ('%s%%' % name.lower(),))
  for network, ip, gateway, mgmt_vlan, vlan, served in rows:
    if _site(served) == site:
      return Switch(network, ip, gateway, mgmt_vlan, vlan)
  return None


def network_by_gateway(gateway, site, db=DB):
  """The short name of SITE's network whose gateway is that address
  (the relay a booting switch's request came through), or None."""
  rows = _rows(db, '''SELECT short_name, name FROM network
                      WHERE ipv4_gateway_txt = ?''', (gateway,))
  for short_name, name in rows:
    if _site(name) == site:
      return short_name
  return None
