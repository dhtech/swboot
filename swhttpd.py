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

# A switch whose model swboot has no entry for asks again every few
# seconds; it is reported once per switch and model in this many seconds
# (to syslog as an error - dh-swboot-discord posts it in the channel).
UNKNOWN_MODEL_REPEAT = 600


def unknown_model(db, ip, switch, model):
  """Report MODEL of switch IP (named SWITCH) as missing from
  switchconfig/config.yaml - once per switch and model in
  UNKNOWN_MODEL_REPEAT seconds. True when it was reported now."""
  key = 'unknown-model-{}-{}'.format(ip, model)
  if not db.set(key, 1, ex=UNKNOWN_MODEL_REPEAT, nx=True):
    return False
  error("Model", model, "of", ip, "name =", switch,
        "is not in switchconfig/config.yaml: nothing sent, the switch",
        "keeps asking until the model is added there")
  return True


class swbootHttpHandler(http.server.SimpleHTTPRequestHandler):
  def do_GET(self):
    db = redis.Redis()
    ip = self.client_address[0]
    switch = db.get(ip)
    model = db.get('client-{}'.format(ip))
    sw_type = db.get('type-{}'.format(ip))
    if switch is None or model is None:
      log("Switch not found:", ip)
      self.send_error(404, "File not found")
      return None
    switch = switch.decode()
    model = model.decode()
    if sw_type:
        sw_type = sw_type.decode()
    if self.path == "/juniper-confg":
      log("Generating Juniper config for",
          self.client_address[0], "name =", switch)
      f = tempfile.TemporaryFile()
      if sw_type == "TABLE":
          # a generated config needs the model's template; a model
          # swboot has no entry for is said, not a crash
          if model not in config.models:
              unknown_model(db, ip, switch, model)
              self.send_error(404, "File not found")
              f.close()
              return None
          try:
              f.write(config.generate(switch, model).encode())
          except Exception as ex:
              error("Generating config for", ip, "name =", switch,
                    "failed:", str(ex))
              self.send_error(500, "Config could not be generated")
              f.close()
              return None
      elif sw_type == "ACCESS":
          filename = config.static_configs + "/" + switch.lower() + ".txt"
          try:
              with open(filename, "rt") as s:
                  for line in s:
                      f.write(line.encode())
          except FileNotFoundError as err:
              log("File ", filename, " not found")
              self.send_error(404, "File not found")
              return None
          except Exception as ex:
              log("Error occurred : ", str(ex))
              self.send_error(500, "Unknown error")
              return None
      else:
          log("Unknown switch type.")
          self.send_error(404, "File not found")
          return None

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
      if model not in config.models:
        unknown_model(db, ip, switch, model)
        self.send_error(404, "File not found")
        return None
      if 'image' not in config.models[model]:
        error("No JunOS image for model", model, "of", ip, "name =", switch,
              "in switchconfig/config.yaml")
        self.send_error(404, "File not found")
        return None
      log("Sending JunOS file", config.models[model]['image'], "to",
        ip, "name =", switch)
      # All good! Overwrite the requested file path and send our own.
      self.path = config.models[model]['image']
      f = self.send_head()
      if f:
        self.copyfile(f, self.wfile)
        log("Sent JunOS to", ip, "name =", switch)
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

  allow_reuse_address = True

  def __init__(self, address, request_handler_class):
    self.address = address
    self.request_handler_class = request_handler_class
    super().__init__(self.address, self.request_handler_class)

if __name__ == "__main__":
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

