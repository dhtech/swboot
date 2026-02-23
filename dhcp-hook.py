#!/usr/bin/env python3
import os
import redis
import sys
import sqlite3
import re

db = redis.Redis()

if sys.argv[1] == "commit":
  swMac = sys.argv[2]
  swIp = sys.argv[3]
  #Parse switch type + remove vlan from the circuit ID
  #Example : "TABLE; D55-A:667" -> "TABLE" "D55-A"
  m = re.search(r"^([^;]+);\s([^:]+):.*$", table[4])
  if m:
    swType = m.group(1)
    swName = m.group(2)
    db.set('type-{}'.format(swIp), swType)
  else:
    swName = table[4]
  # Remove the serial number from Juniper's vendor-class-identifier.
  # Example: "Juniper-ex3400-24t-AB1234567890" -> "Juniper-ex3400-24t"
  swClient = re.sub(r'(Juniper.*)-[^-]+$', r'\1', sys.argv[5])
  swRelay = sys.argv[6]
  db.set(swIp, swName)
  db.set('ip-{}'.format(swIp), swMac)
  db.set('client-{}'.format(swIp), swClient)
  db.set('mac-{}'.format(swMac), swIp)
  if swRelay != '0.0.0.0':
    db.set('relay-{}'.format(swIp), swRelay)
    sqlidb = sqlite3.connect('/etc/ipplan.db')
    cursor = sqlidb.cursor()
    sql = "SELECT short_name FROM network WHERE ipv4_gateway_txt = ?"
    networkname = cursor.execute(sql, (swRelay, )).fetchone()[0]
    db.set('networkname-{}'.format(swIp), networkname)
  if "Juniper" not in swClient:
    # We don't need any SNMP or base config for Juniper.
    os.system("/scripts/swboot/configure " + swIp + " &")
