#!/usr/bin/env python3
import sys, logging
import redis
import syslog
import socket
import re
import tempfile
import http.server
import socketserver
import time

import config

def log(*args):
  print(time.strftime("%Y-%m-%d %H:%M:%S") + ':', ' '.join(args))
  syslog.syslog(syslog.LOG_INFO, ' '.join(args))

def error(*args):
  print(time.strftime("%Y-%m-%d %H:%M:%S") + ': ERROR:', ' '.join(args))
  syslog.syslog(syslog.LOG_ERR, ' '.join(args))

class swbootHttpHandler(http.server.SimpleHTTPRequestHandler):
  def do_GET(self):
    db = redis.Redis()
    switch = db.get(self.client_address[0]).decode()
    model = db.get('client-{}'.format(self.client_address[0])).decode()
    if switch == None or model == None:
      log("Switch not found:", self.client_address[0])
      self.send_error(404, "File not found")
      return None
    if self.path == "/juniper-confg":
      log("Generating Juniper config for",
          self.client_address[0], "name =", switch)
      f = tempfile.TemporaryFile()
      f.write(config.generate(switch, model).encode())
      content_length = f.tell()
      f.seek(0)

      self.send_response(200)
      self.send_header("Content-type", "application/octet-stream")
      self.send_header("Content-Length", content_length)
      self.end_headers()
      self.copyfile(f, self.wfile)
      log("Config sent to", self.client_address[0], "name =", switch)

      f.close()
      return
    elif self.path == "/juniper.tgz":
      log("Sending JunOS file", config.models[model]['image'], "to",
        self.client_address[0], "name =", switch)
      if (model in config.models) and ('image' in config.models[model]):
        # All good! Overwrite the requested file path and send our own.
        self.path = config.models[model]['image']
        f = self.send_head()
        if f:
          self.copyfile(f, self.wfile)
          log("Sent JunOS to", self.client_address[0], "name =", switch)
          f.close()
    else:
      log("Unknown file:", self.path)
      self.send_error(404, "File not found")
  
  # We write our own logs.
  def log_request(self, code='-', size='-'):
    pass
  def log_error(self, format, *args):
    pass

class swbootTCPServer(socketserver.ForkingTCPServer):
  def server_bind(self):
    self.socket.bind(self.server_address)

log("swhttpd started")

try:
  httpd = swbootTCPServer(("", 80), swbootHttpHandler)
  httpd.serve_forever()
except socket.error as err:
  sys.stderr.write("Socket error: %s\n" % str(err))
  sys.exit(1)
except KeyboardInterrupt:
  sys.stderr.write("\n")
except Exception as err:
  sys.stderr.write("Something went wrong: %s\n" % err)


