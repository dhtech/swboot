#!/usr/bin/env python
import os
import redis
import sys

db = redis.Redis()

if sys.argv[1] == "commit":
  ip = sys.argv[2]
  sw = sys.argv[3]
  relay = sys.argv[5]
  db.set(ip, sw)
  if relay != '0.0.0.0':
    db.set('relay-%s' % ip, relay)
  os.system("/scripts/swboot/configure " + ip + " &")
