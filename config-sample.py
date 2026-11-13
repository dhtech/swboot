#!/usr/bin/env python3

import config
import ipcalc
import ipplan
import swsecrets
import sys
import os
import tempita
import yaml
from tempita import bunch
from collections import namedtuple
from passlib.hash import sha512_crypt
import hashlib

f = open(os.path.join(os.path.dirname(sys.argv[0]), 'switchconfig/config.yaml'), 'r')
yaml_conf = yaml.safe_load(f)

# The secrets (swsecrets.py): the radius key, the local login, the enable
# password, the SNMP read community and the salt of the SNMP write
# community. They are read from this JSON file - they are not written
# here. Set secrets_file to None to give them below instead (a test rig).
# Note: To add new variables, the generate function will need to
# be modified as well
secrets_file = swsecrets.SECRETS_FILE
radius = ""
username = ""
password = ""
enable = ""
snmp_ro = ""
snmp_salt = ""
if secrets_file:
  globals().update(swsecrets.load(secrets_file))

# NOTE(bluecmd): 2950 doesn't support VLAN aware context, which means that
# WhereAmI and dhmon needs v2. No reason to have v3 in that case.
#snmp_user = ""
#snmp_auth = ""
#snmp_priv = ""
wifi_vlanid = yaml_conf['wifi']['vlan_id']

# Enable this if we cannot set special option82 tags
franken_net_switches = [ ]

# If you have franken net, you need snmpv3 credentials to dist
# NOTE: THERE IS NO NEED TO USE THIS IF is_franken_net == False
snmpv3_username = ''
snmpv3_auth = ''
snmpv3_priv = ''

models = {}
for model in yaml_conf['models']:
  data = bunch(template=model['path'],eth=model['ports'])
  if 'image' in model:
    data.image = model['image']
  models.update({model['name']: data})

wifi_switches = yaml_conf['wifi']['switches']

# Files to be served as they are to all devices
static_files = {}
for sf in yaml_conf['static_files']:
  static_files.update(sf)

# Folder containing static configurations to be served as-is by switchboot (ACCESS;)
static_configs = None
if "static_configs" in yaml_conf:
    static_configs = yaml_conf["static_configs"]


# The site this server serves, as the plan names it (the part before the
# "@" of its networks' names, e.g. "EVENT"). The plan holds every site;
# a switch is told about the servers of THIS one only. None: this
# machine's own site, by its name in the plan (or /etc/swboot/site).
site = None

# ===============================================================
# Do not change below this if you do not know what you're doing!
# ===============================================================

def served_site():
  return config.site or ipplan.own_site()

# ipplan_host('myhost.event.dreamhack.se')
#   returns Host object with name, ipv4, and ipv6 properties from ipplan
#   database
Host = ipplan.Host
def ipplan_host(hostname):
  return ipplan.host(hostname)

# ipplan_package('mypackage')
#   returns array of Host objects containing the hosts OF THIS SITE with
#   the given package from ipplan database
def ipplan_package(package):
  return ipplan.package(package, served_site())

def generate(switch, model_id):
  model = config.models[model_id]

  mgmt, vlanid = parse_metadata(switch)
  if mgmt is None:
    raise Exception("The switch " + switch + " was not found in ipplan")
  if not config.radius:
    raise Exception("Radius key not set")
  if not config.username:
    raise Exception("Username not set")
  if not config.password:
    raise Exception("User-password not set")
  if not config.enable:
    raise Exception("Enable password not set")
  if not config.snmp_ro:
    raise Exception("SNMP ro not set")
  if not config.snmp_salt:
    raise Exception("SNMP salt not set")

  #
  # Template function definition
  #
  cfg = tempita.Template(open(model.template).read())
  cfg_subbed = cfg.substitute(
            hostname=switch,
            model=model,
            mgmt_ip=mgmt['ip'],
            mgmt_mask=mgmt['mask'],
            mgmt_mask_cidr=mgmt['mask_cidr'],
            mgmt_gw=mgmt['gw'],
            mgmt_vlanid=mgmt['vlanid'],
            vlanid=vlanid,
            wifi_switches=config.wifi_switches,
            wifi_vlanid=config.wifi_vlanid,
            password=config.password,
            password_sha512=sha512_crypt.hash(config.password),
            enable=config.enable,
            enable_sha512=sha512_crypt.hash(config.enable),
            radius=config.radius,
            snmp_ro=config.snmp_ro,
            snmp_rw=hashlib.sha1((config.snmp_salt + mgmt['ip']).encode()).hexdigest(),
            ipplan_host=lambda h: ipplan_host(h),
            ipplan_pkg=lambda p: ipplan_package(p),
#           snmp_user=config.snmp_user,
#           snmp_auth=config.snmp_auth,
#           snmp_priv=config.snmp_priv
            )
  # We make the Juniper config a script, to be able to add the crontab.
  if "Juniper" in model_id:
    jcfg = tempita.Template(open(os.path.join(os.path.dirname(sys.argv[0]), 'juniper.sh.template')).read())
    cfg_subbed = jcfg.substitute(config=cfg_subbed)
  return cfg_subbed

def parse_metadata(switch):
  found = ipplan.switch(switch, served_site())
  if found is None:
    return None, None

  network = ipcalc.Network(found.network)

  mgmt = {}
  mgmt['ip'] = found.ip
  mgmt['mask'] = str(network.netmask())
  mgmt['mask_cidr'] = str(network.subnet())
  mgmt['gw'] = str(network.host_first())
  mgmt['vlanid'] = found.mgmt_vlan

  return mgmt, found.vlan

if __name__ == '__main__':
  if len(sys.argv) == 3 and sys.argv[1] == 'dump-snmp-rw':
    mgmt, _ = parse_metadata(sys.argv[2])
    print(hashlib.sha1(config.snmp_salt + mgmt['ip']).hexdigest())
  else:
    print(generate("D23-A", "WS-C2950T-24"))
