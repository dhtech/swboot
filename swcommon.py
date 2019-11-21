
#!/usr/bin/env python
import tempfile
import syslog
import redis
import netsnmp
import os
import re
import traceback
import time

import config

db = redis.Redis()

def log(*args):
  print time.strftime("%Y-%m-%d %H:%M:%S") + ':', ' '.join(args)
  syslog.syslog(syslog.LOG_INFO, ' '.join(args))

def error(*args):
  print time.strftime("%Y-%m-%d %H:%M:%S") + ': ERROR:', ' '.join(args)
  syslog.syslog(syslog.LOG_ERR, ' '.join(args))

def sw_reload(ip):
  error("Reloading switch")
  try:
    os.system("/scripts/swboot/reload " + ip + " &")
  except:
    error("Exception in reload:", traceback.format_exc())

def generate(out, ip, switch):
  model = db.get('client-{}'.format(ip))
  if model == None:
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

def select_file(file_to_transfer, ip):
  if file_to_transfer in config.static_files:
    return file(config.static_files[file_to_transfer])

  global db
  switch = db.get(ip)
  if switch is None:
    error('No record of switch', ip, 'in Redis, ignoring ..')
    return None

  log('Switch is ', switch)
  db.set('switchname-%s' % ip, switch)
  
  model = db.get('client-{}'.format(ip))

  if not re.match('^([A-Z]{1,2}[0-9][0-9]-[A-C]|DIST:[A-Z]{1,2}-[A-Z]-[A-Z]+-S[TW])$', switch):
    sw_reload(ip)
    error("Switch", ip, "does not match regexp, invalid option 82? Received '", switch, "' as option 82")
    return None

  # Dist config.
  if "DIST:" in switch and file_to_transfer.lower().endswith("-confg"):
    if re.match(r'^[a-zA-Z0-9:-]+$', switch) and os.path.isfile('distconfig/%s' % switch[5:]):
      log("Sending config to", switch)
      f = open('distconfig/%s' % switch[5:])
      return f
    error('Dist config not found', ip)
    return None

  # Juniper config.
  if file_to_transfer == "juniper-confg":
    log("Generating Juniper config for", ip, "name =", switch)
    f = tempfile.TemporaryFile()
    f.write(config.generate(switch, model))
    f.seek(0)
    return f

  # Switch base config.
  if (file_to_transfer == "network-confg" or
      file_to_transfer == "Switch-confg"):
    log("Generating config for", ip, "name =", switch)
    f = tempfile.TemporaryFile()
    base(f, switch)
    f.seek(0)
    return f

  # Juniper image.
  if file_to_transfer == "juniper.tgz":
    if (model in config.models) and ('image' in config.models[model]):
      log("Sending JunOS image to ", ip, "name =", switch)
      return file(config.models[model]['image'])
    log("Missing image file for", ip, "name =", switch)

  # Final config for non-Juniper switches.
  if file_to_transfer.lower().endswith("-confg"):
    f = tempfile.TemporaryFile()
    log("Generating config for", ip,"config =", switch)
    if generate(f, ip, switch) == None:
      return None
    f.seek(0)
    return f

  error("Switch", ip, "config =", switch, "tried to get file",
    file_to_transfer)
  return None

