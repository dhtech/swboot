#!/usr/bin/env python
import os
import redis
import sys
import sqlite3

db = redis.Redis()

if sys.argv[1] == "commit":
  ip = sys.argv[2]
  sw = sys.argv[3]
  relay = sys.argv[5]
  db.set(ip, sw)
  if relay != '0.0.0.0':
    db.set('relay-%s' % ip, relay)
    sqlidb = sqlite3.connect('/etc/ipplan.db')
    cursor = sqlidb.cursor()
    sql = "SELECT short_name FROM network WHERE ipv4_gateway_txt = ?"
    networkname = cursor.execute(sql, (relay, )).fetchone()[0]
    db.set('networkname-%s' % ip, networkname)
  os.system("/scripts/swboot/configure " + ip + " &")
