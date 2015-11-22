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

import config

db = redis.Redis()

def log(*args):
  print ' '.join(args)
  syslog.syslog(syslog.LOG_INFO, ' '.join(args))

def error(*args):
  print 'ERROR:', ' '.join(args)
  syslog.syslog(syslog.LOG_ERR, ' '.join(args))

def sw_reload(ip):
  error("Reloading switch")
  try:
    os.system("/scripts/swboot/reload " + ip + " &")
  except:
    error("Exception in reload:", traceback.format_exc())

def generate(out, ip, switch):
  # Get Cisco model name (two tries)
  for i in xrange(2):
    var = netsnmp.Varbind('.1.3.6.1.2.1.47.1.1.1.1.13.1')
    model = netsnmp.snmpget(var, Version=2, DestHost=ip, Community='private')[0]

    if model == None:
      var = netsnmp.Varbind('.1.3.6.1.2.1.47.1.1.1.1.13.1001')
      model = netsnmp.snmpget(var, Version=2, DestHost=ip, Community='private')[0]
    
  if model == None:
    sw_reload(ip)
    error("Could not get model for switch" , ip)
    return

  if not model in config.models:
    sw_reload(ip)
    error("Template for model " + model_id + " not found")
    return

  # Throws exception if something bad happens
  try:
    txt = config.generate(switch, model)
    out.write("! Config for " + switch + "\n")
    out.write(txt)
  except:
    sw_reload(ip)
    error("Exception in generation for %s :" % switch, traceback.format_exc())
    out.close()
    return None

  return out
  
def base(out, switch):
  out.write("snmp-server community private rw\n")
  out.write("hostname BASE\n")
  out.write("no vlan 2-4094\n")
  out.write("end\n\n")

def snmpv3_command(var, host, cmd):
  return cmd(var, Version=3, DestHost=host,
      SecName=config.snmpv3_username, SecLevel='authPriv',
      AuthProto='SHA', AuthPass=config.snmpv3_auth,
      PrivProto='AES128', PrivPass=config.snmpv3_priv)

def resolve_option82(relay, option82):
  module = int(option82[0], 16)
  port = int(option82[1], 16)
  print 'Switch on "%s" attached to module "%s" and port "%s"' % (
      relay, module, port)
  var = netsnmp.VarList(netsnmp.Varbind('.1.3.6.1.2.1.31.1.1.1.1'))
  if snmpv3_command(var, relay, netsnmp.snmpwalk) is None:
    print 'ERROR: Unable to talk to relay "%s" for description lookup' % relay
    return None

  for result in var:
    iface = result.tag.split('.')[-1]
    name = result.val
    if (name == 'Gi%d/%d' % (module, port) or
        name == 'Gi%d/0/%d' % (module, port)):
      print 'Found switch on interface "%s"' % name
      var = netsnmp.Varbind(
        '.1.3.6.1.4.1.9.2.2.1.1.28.%d' % int(iface))
      return snmpv3_command(var, relay, netsnmp.snmpget)[0][6:]

def file_callback(context):
  if context.file_to_transfer in config.static_files:
    return file(config.static_files[context.file_to_transfer])

  global db
  option82 = db.get(context.host)
  if option82 is None:
    error('No record of switch', context.host, 'in Redis, ignoring ..')
    return None

  ip = context.host
  # If we do not have any franken switches, do not execute this horrible code path
  if not config.franken_net_switches:
    switch = option82
  else:
    # In this sad universe we have switches with different capabilities, so we
    # need to figure out who sent the request. We use the Gateway Address
    # (a.k.a. relay address) for this.
    relay = db.get('relay-%s' % ip)
    if relay not in config.franken_net_switches:
      # Puh, cris averted - not a franken switch.
      switch = option82
    else:
      # If the relay is set to 0.0.0.0 something is wrong - this shouldn't
      # be the case anymore, but used to happen when dhcp-hook didn't filter
      # this.
      if relay == '0.0.0.0':
        error('Ignoring non-relayed DHCP request from', ip)
        return None
      switch = resolve_option82(relay, option82.split(':'))

  if switch is None:
    error('Unable to identifiy switch', ip)
    return None
    
  print 'Switch is "%s"' % switch
  db.set('switchname-%s' % ip, switch)

  if (context.file_to_transfer == "network-confg" or
      context.file_to_transfer == "Switch-confg"):
    f = tempfile.TemporaryFile()
    log("Generating base config", context.file_to_transfer,
        "for", context.host,"config =", switch)
    base(f, switch)
    f.seek(0)
    return f

  if not re.match('[A-Z]{1,2}[0-9][0-9]-[A-C]', switch):
    sw_reload(ip)
    error("Switch", ip, "does not match regexp, invalid option 82?")
    return None

  f = tempfile.TemporaryFile()
  if context.file_to_transfer.lower().endswith("-confg"):
    log("Generating config for", ip,"config =", switch)
    if generate(f, ip, switch) == None:
      return None
  else:
    error("Switch", ip, "config =", switch, "tried to get file",
        context.file_to_transfer)
    f.close()
    return None

  f.seek(0)
  return f

log("swtftpd started")
tftpy.setLogLevel(logging.WARNING)
server = tftpy.TftpServer(file_callback)
try:
  server.listen("192.168.40.10", 69)
except tftpy.TftpException, err:
  sys.stderr.write("%s\n" % str(err))
  sys.exit(1)
except KeyboardInterrupt:
  pass

