#!/usr/bin/env python3

import netsnmp
import config
import sys

if len(sys.argv) < 3:
  print("Usage:", sys.argv[0], " D29-A WS-C2950T-24")
  sys.exit(1)

switch = sys.argv[1]
model = sys.argv[2]

print(config.generate(switch, model))
