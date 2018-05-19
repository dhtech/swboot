#!/usr/bin/env python
import os
import redis
import sys
import sqlite3

db = redis.Redis()

if sys.argv[1] == "commit":
  swMac = sys.argv[2]
  swIp = sys.argv[3]
  swName = sys.argv[4]
  swClient = sys.argv[5]
  swRelay = sys.argv[6]
  db.set(swIp, swName)
  db.set('ip-{}'.format(swIp), swMac)
  db.set('mac-{}'.format(swMac), swIp)
  if swRelay != '0.0.0.0':
    db.set('relay-{}'.format(SwIp), swRelay)
    sqlidb = sqlite3.connect('/etc/ipplan.db')
    cursor = sqlidb.cursor()
    sql = "SELECT short_name FROM network WHERE ipv4_gateway_txt = ?"
    networkname = cursor.execute(sql, (swRelay, )).fetchone()[0]
    db.set('networkname-{}'.format(swIp), networkname)
  os.system("/scripts/swboot/configure " + swIp + " &")
