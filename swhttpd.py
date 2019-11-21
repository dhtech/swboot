#!/usr/bin/env python
import sys, logging
import syslog
import socket
import SimpleHTTPServer
import SocketServer
import time

import config
import swcommon

def log(*args):
  print time.strftime("%Y-%m-%d %H:%M:%S") + ':', ' '.join(args)
  syslog.syslog(syslog.LOG_INFO, ' '.join(args))

def error(*args):
  print time.strftime("%Y-%m-%d %H:%M:%S") + ': ERROR:', ' '.join(args)
  syslog.syslog(syslog.LOG_ERR, ' '.join(args))

class swbootHttpHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
  def do_GET(self):
    # self.path is the path of the requested file.
    file_handle = swcommon.select_file(self.path.lstrip("/"), self.client_address[0])

    if file_handle == None:
      log("Switch not found:", self.client_address[0])
      self.send_error(404, "File not found")
      return None

    # Go to the end of the file to get the length of it.
    file_handle.seek(0, 2)
    content_length = file_handle.tell()
    file_handle.seek(0)

    self.send_response(200)
    self.send_header("Content-type", "application/octet-stream")
    self.send_header("Content-Length", content_length)
    self.end_headers()
    self.copyfile(file_handle, self.wfile)

  # We write our own logs.
  def log_request(self, code='-', size='-'):
    pass
  def log_error(self, format, *args):
    pass

class swbootTCPServer(SocketServer.ForkingTCPServer):
  def server_bind(self):
    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.socket.bind(self.server_address)

try:
  httpd = swbootTCPServer(("", 80), swbootHttpHandler)
  log("swhttpd started")
  httpd.serve_forever()
except socket.error, err:
  sys.stderr.write("Socket error: %s\n" % str(err))
  sys.exit(1)
except KeyboardInterrupt:
  sys.stderr.write("\n")
except Exception, err:
  sys.stderr.write("Something went wrong: %s\n" % err)


