# swboot

On-demand switch configuration system.

License is GPLv3 if nothing else is stated.

## Dependencies
    sudo apt-get install redis-server python3-redis libsnmp-dev python3-tempita python3-ipcalc python3-yaml isc-dhcp-server snmp python3-pip build-essential python3-dev python3-six python3-wheel
    pip3 install python3-netsnmp ipcalc passlib

## Config
    sudo /sbin/ifconfig eth1 inet 192.168.8.10 netmask 255.255.255.0

## Install
    cp config-sample.py config.py

## dhcpd.conf
    include "/scripts/swboot/dhcpd.conf";

## Start swtftpd
    sudo python3 swtftpd.py

## Test generation of configuration
    python3 generate.py D20-A WS-C2950T-24

## Boot procedure

The Cisco switches will try to get DHCP and boot via TFTP if no config exists (wr erase).
If you want to have a config stored on the switch it must include "boot host dhcp".

## Default switch conf

For event configs, see SVN allevents/access/default-paste/

In general, something like this will work:

    en
    conf t
    boot host dhcp
    interface vlan 1
    no ip address
    no shut
    !
    snmp-server community public RO
    snmp-server community private RW
    snmp-server system-shutdown
    !
    wr
    !


## Dist switch

    en
    conf t
    ip routing
    !
    ip dhcp snooping vlan 1
    ! Perhaps needed:
    ! ip dhcp snooping information option allow-untrusted
    ip dhcp snooping
    !         
    !         
    interface GigabitEthernet1/0/5
     description DHCP-server
     switchport access vlan 123
     switchport mode access
     spanning-tree portfast
     ip dhcp snooping trust
    !         
    interface GigabitEthernet1/0/20
     spanning-tree portfast
     ip dhcp snooping vlan 1 information option format-type circuit-id string B01-B
    !
    interface Vlan1
     ip address 10.80.10.1 255.255.255.0
     ip helper-address 10.255.253.2
    !
    interface Vlan123
     ip address 10.255.253.5 255.255.255.0
    !
