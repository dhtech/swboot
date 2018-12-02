import config
import yaml
import sys

f = file('switchconfig/switches.yaml', 'r')
switches_yaml = yaml.load(f)

def create_config(switches_yaml, dest_path):
	for model,locations in switches_yaml['models'].iteritems():
		for location in locations:
			
			filename = str(location) + "_" + str(model) + '.cfg'
			
			try:
				with open(dest_path + filename, 'w') as file_out:
					file_out.write(config.generate(location, model))
					print "Created file: " + filename
			except IOError:
				sys.exit('Unable to create file. Write permissions?')

create_config(switches_yaml, sys.argv[1])
