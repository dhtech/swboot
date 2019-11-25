import config
import ipcalc
import sqlite3
import sys
import tempita
import yaml
from tempita import bunch
from collections import namedtuple
import hashlib

f = open('switchconfig/config.yaml', 'r')
yaml_conf = yaml.load(f)

# Note: To add new variables, the generate function will need to 
# be modified as well
radius = ""
username = ""
password = ""
enable = ""
snmp_ro = ""
snmp_salt = ""

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


# ===============================================================
# Do not change below this if you do not know what you're doing!
# ===============================================================

# ipplan_host('myhost.event.dreamhack.se')
#   returns Host object with name, ipv4, and ipv6 properties from ipplan
#   database
Host = namedtuple('Host', 'name ipv4 ipv6')
def ipplan_host(hostname):
  sql = '''SELECT h.name, h.ipv4_addr_txt as ipv4, h.ipv6_addr_txt as ipv6 
           FROM host as h 
           WHERE h.name = ?;'''

  db = sqlite3.connect('/etc/ipplan.db')
  db.row_factory = sqlite3.Row

  cursor = db.cursor()

  row = cursor.execute(sql, (hostname,)).fetchone()
  if row is None:
    raise Exception("No IPv4 address found for host %s not in ipplan" % hostname)

  return Host(name=row['name'], ipv4=row['ipv4'], ipv6=row['ipv6'])

# ipplan_package('mypackage')
#   returns array of Host objects containing hosts with the given package from
#   ipplan database
def ipplan_package(package):
  sql = '''SELECT h.name, h.ipv4_addr_txt as ipv4, h.ipv6_addr_txt as ipv6 
           FROM host as h 
           INNER JOIN package as p ON p.node_id = h.node_id 
           WHERE p.name = ?;'''

  db = sqlite3.connect('/etc/ipplan.db')
  db.row_factory = sqlite3.Row

  cursor = db.cursor()

  hosts = []
  for row in cursor.execute(sql, (package,)):
    hosts.append(Host(name=row['name'], ipv4=row['ipv4'], ipv6=row['ipv6']))

  return sorted(set(hosts), key=lambda e: e.name)

def generate(switch, model_id):
  model = config.models[model_id]

  mgmt, vlanid = parse_metadata(switch)
  if mgmt is None:
    raise Exception("The switch " + switch + " was not found in ipplan")
  if radius is None:
    raise Exception("Radius key not set")
  if username is None:
    raise Exception("Username not set")
  if password is None:
    raise Exception("User-password not set")
  if enable is None:
    raise Exception("Enable password not set")
  if snmp_ro is None:
    raise Exception("SNMP ro not set")
  if snmp_salt is None:
    raise Exception("SNMP salt not set")

  #
  # Template function definition
  #
  cfg = tempita.Template(file(model.template).read())
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
            enable=config.enable,
            radius=config.radius,
            snmp_ro=config.snmp_ro,
            snmp_rw=hashlib.sha1(config.snmp_salt + mgmt['ip']).hexdigest(),
            ipplan_host=lambda h: ipplan_host(h),
            ipplan_pkg=lambda p: ipplan_package(p),
#           snmp_user=config.snmp_user,
#           snmp_auth=config.snmp_auth,
#           snmp_priv=config.snmp_priv
            )
  # We make the Juniper config a script, to be able to add the crontab.
  if "Juniper" in model_id:
	  jcfg = tempita.Template(file('juniper.sh.template').read())
	  cfg_subbed = jcfg.substitute(config=cfg_subbed)
  return cfg_subbed

def parse_metadata(switch):
  sql = '''SELECT n_mgmt.ipv4_txt, h.ipv4_addr_txt, n_mgmt.ipv4_gateway_txt, 
n_mgmt.vlan, n.vlan FROM active_switch as s, network as n, host as h, 
network as n_mgmt WHERE s.switch_name LIKE ? AND n.node_id = s.node_id
AND h.name = s.switch_name AND n_mgmt.node_id = h.network_id'''

  db = sqlite3.connect('/etc/ipplan.db')
  cursor = db.cursor()

  row = cursor.execute(sql, ('%s%%' % switch.lower(),)).fetchone()
  if row is None:
    return None, None

  network_str, mgmt_ip, gateway, mgmt_vlan, vlan = row

  network = ipcalc.Network(network_str)

  mgmt = {}
  mgmt['ip'] = mgmt_ip
  mgmt['mask'] = str(network.netmask())
  mgmt['mask_cidr'] = str(network.netmask())
  mgmt['gw'] = str(network.host_first())
  mgmt['vlanid'] = mgmt_vlan

  return mgmt, vlan

if __name__ == '__main__':
  if len(sys.argv) == 3 and sys.argv[1] == 'dump-snmp-rw':
    mgmt, _ = parse_metadata(sys.argv[2])
    print(hashlib.sha1(config.snmp_salt + mgmt['ip']).hexdigest())
  else:
    print(generate("D23-A", "WS-C2950T-24"))
