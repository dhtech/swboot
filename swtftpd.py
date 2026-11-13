#!/usr/bin/env python3
import sys, logging
import tftpy
import tempfile
import redis
import syslog
import swsnmp
import traceback
import re
import os
import time

import config

db = redis.Redis()

def log(*args):
  print(time.strftime("%Y-%m-%d %H:%M:%S") + ':', ' '.join(args))
  syslog.syslog(syslog.LOG_INFO, ' '.join(args))

def error(*args):
  print(time.strftime("%Y-%m-%d %H:%M:%S") + ': ERROR:', ' '.join(args))
  syslog.syslog(syslog.LOG_ERR, ' '.join(args))

def sw_reload(ip):
  error("Reloading switch")
  try:
    os.system("/scripts/swboot/reload " + ip + " &")
  except:
    error("Exception in reload:", traceback.format_exc())

def generate(out, ip, switch):
  model = db.get('client-{}'.format(ip)).decode()
  if model == 'cisco':
    # Get Cisco model name (two tries)
    for i in range(2):
      session = swsnmp.v2(ip, 'private')
      model = swsnmp.get(session, '.1.3.6.1.2.1.47.1.1.1.1.13.1')

      if model == None:
        model = swsnmp.get(session, '.1.3.6.1.2.1.47.1.1.1.1.13.1001')
    
  if model == None:
    sw_reload(ip)
    error("Could not get model for switch" , ip)
    return

  if not model in config.models:
    sw_reload(ip)
    error("Template for model " + model + " not found")
    return

  # Throws exception if something bad happens
  try:
    txt = config.generate(switch, model)
    out.write(txt.encode())
  except:
    sw_reload(ip)
    error("Exception in generation for %s :" % switch, traceback.format_exc())
    out.close()
    return None

  return out
  
def base(out, switch):
  out.write("snmp-server community private rw\n".encode())
  out.write("hostname BASE\n".encode())
  out.write("no vlan 2-4094\n".encode())
  out.write("end\n\n".encode())

def resolve_option82(relay, option82):
  module = int(option82[0], 16)
  port = int(option82[1], 16)
  print('Switch on "%s" attached to module "%s" and port "%s"' % (
      relay, module, port))
  session = swsnmp.v3(relay, config.snmpv3_username, config.snmpv3_auth,
                      config.snmpv3_priv)
  names = swsnmp.walk(session, '.1.3.6.1.2.1.31.1.1.1.1')
  if names is None:
    print('ERROR: Unable to talk to relay "%s" for description lookup' % relay)
    return None

  for iface, name in names:
    if (name == 'Gi%d/%d' % (module, port) or
        name == 'Gi%d/0/%d' % (module, port)):
      print('Found switch on interface "%s"' % name)
      described = swsnmp.get(
        session, '.1.3.6.1.4.1.9.2.2.1.1.28.%d' % int(iface))
      # the description is "<6 characters><switch name>"
      return None if described is None else described[6:]

def file_callback(file_to_transfer, raddress, rport):
  if file_to_transfer in config.static_files:
    return open(config.static_files[file_to_transfer], 'rb')

  global db
  option82 = db.get(raddress).decode()
  if option82 is None:
    error('No record of switch', raddress, 'in Redis, ignoring ..')
    return None

  # If we do not have any franken switches, do not execute this horrible code path
  if not config.franken_net_switches:
    switch = option82
  else:
    # In this sad universe we have switches with different capabilities, so we
    # need to figure out who sent the request. We use the Gateway Address
    # (a.k.a. relay address) for this.
    relay = db.get('relay-%s' % raddress).decode()
    if relay not in config.franken_net_switches:
      # Puh, cris averted - not a franken switch.
      switch = option82
    else:
      # If the relay is set to 0.0.0.0 something is wrong - this shouldn't
      # be the case anymore, but used to happen when dhcp-hook didn't filter
      # this.
      if relay == '0.0.0.0':
        error('Ignoring non-relayed DHCP request from', raddress)
        return None
      switch = resolve_option82(relay, option82.split(':'))

  if switch is None:
    error('Unable to identifiy switch', raddress)
    return None
    
  print('Switch is "%s"' % switch)
  db.set('switchname-%s' % raddress, switch)

  if (file_to_transfer == "network-confg" or
      file_to_transfer == "Switch-confg"):
    f = tempfile.TemporaryFile()
    log("Generating base config", file_to_transfer,
        "for", raddress,"config =", switch)
    base(f, switch)
    f.seek(0)
    return f

  if file_to_transfer == "juniper.tgz":
    model = db.get('client-{}'.format(raddress)).decode()
    if (model in config.models) and ('image' in config.models[model]):
      return open(config.models[model]['image'], 'rb')

  sw_type = db.get('type-%s' % raddress)
  if sw_type:
    sw_type = sw_type.decode()

  if sw_type and sw_type == "ACCESS":
    if file_to_transfer.lower().endswith("-confg"):
      filename = config.static_configs + "/" + switch.lower() + ".txt"
      try:
        with open(filename, "rt") as s:
          f = tempfile.TemporaryFile()
          log("Sending static config for", raddress,"config =", switch)
          for line in s:
            f.write(line.encode())
          f.seek(0)
          return f
      except FileNotFoundError as err:
        error('File ', filename, ' not found')
        return None
      except Exception as ex:
        error('Uknown error occurred')
        return None
    else:
          error("Unknown file to transfer for switch ",switch)
          return None

  if not re.match('[A-Z]+[0-9][0-9]-[A-C]', switch):
    sw_reload(raddress)
    error("Switch", raddress, "does not match regexp, invalid option 82? Received ", option82, " as option 82")
    return None

  f = tempfile.TemporaryFile()
  if file_to_transfer.lower().endswith("-confg"):
    log("Generating config for", raddress,"config =", switch)
    if generate(f, raddress, switch) == None:
      return None
  else:
    error("Switch", raddress, "config =", switch, "tried to get file",
        file_to_transfer)
    f.close()
    return None

  f.seek(0)
  return f

log("swtftpd started")
server = tftpy.TftpServer('/srv/tftp', file_callback)
tftplog = logging.getLogger('tftpy.TftpClient')
tftplog.setLevel(logging.WARN)
try:
  server.listen("192.168.40.10", 69)
except tftpy.TftpException as err:
  sys.stderr.write("%s\n" % str(err))
  sys.exit(1)
except KeyboardInterrupt:
  sys.stderr.write("\n")
