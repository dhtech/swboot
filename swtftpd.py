#!/usr/bin/env python
import sys, logging
import tftpy
import tempfile
import redis
import syslog
import netsnmp
import traceback
import re
import os
import time

import config
import swcommon

db = redis.Redis()

def log(*args):
  print time.strftime("%Y-%m-%d %H:%M:%S") + ':', ' '.join(args)
  syslog.syslog(syslog.LOG_INFO, ' '.join(args))

def error(*args):
  print time.strftime("%Y-%m-%d %H:%M:%S") + ': ERROR:', ' '.join(args)
  syslog.syslog(syslog.LOG_ERR, ' '.join(args))

def file_callback(file_to_transfer, raddress, rport):
  return swcommon.select_file(file_to_transfer, raddress)

server = tftpy.TftpServer('/scripts/swboot/ios', file_callback)
tftplog = logging.getLogger('tftpy.TftpClient')
tftplog.setLevel(logging.WARN)
log("swtftpd started")
try:
  server.listen("", 69)
except tftpy.TftpException, err:
  sys.stderr.write("%s\n" % str(err))
  sys.exit(1)
except KeyboardInterrupt:
  sys.stderr.write("\n")
