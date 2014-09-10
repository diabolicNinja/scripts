#!/usr/bin/env python
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
############################################################
#   Author:	    Denis Prezhevalsky (deniska@redhat.com)
#   Date:           09 September 2014    
#   Version:        1.0
#   Description:    simple python script to update
#                   remove host
############################################################ 
import paramiko
import getpass
import socket
import os
import sys
import argparse
#import yum

# set options
_version        = 1.0
_engine_addr    = None
_engine_user    = None
_engine_pass    = None

# collect information
parser = argparse.ArgumentParser(description="Update RHEV hypervisor/s", epilog="Example: prog -e x.y.z.w -u root -p secret host1 host2...")
#group = parser.add_mutually_exclusive_group()
#group.add_argument("-q", "--quiet", action="store_true")
parser.add_argument("-v", "--verbose", action="store_true")
parser.add_argument("-f", "--file", type=file, help="file with hosts to update")
parser.add_argument("hypervisor", nargs='+', help="hypervisor/s to apply updates to")
#parser.add_argument("-e", "--engine", required=True, help="rhev engine address")
parser.add_argument("-e", "--engine", help="rhev engine address")
parser.add_argument("-u", "--username", help="rhev engine username (yum run privileges)")
parser.add_argument("-p", "--password", help="rhev engine password")
parser.add_argument('--version', action='version', version=str(_version))
args = parser.parse_args()

if args.engine:
    _engine_addr = args.engine
elif os.getenv('RHEV_ENGINE_ADDRESS', None):
    _engine_addr =  os.getenv('RHEV_ENGINE_ADDRESS')
else:
    print "Error: no engine server specified - exiting"
    sys.exit(1)

if args.username:
    _engine_user = args.username
elif os.getenv('RHEV_ENGINE_USERNAME', None):
    _engine_user = os.getenv('RHEV_ENGINE_USERNAME')

if args.password:
    _engine_pass = args.password
elif os.getenv('RHEV_ENGINE_PASSWORD', None):
    _engine_pass = os.getenv('RHEV_ENGINE_PASSWORD')

print _engine_addr
print _engine_user
print _engine_pass
sys.exit(0)

hostn = os.getenv('HYPHOST_ADDRESS', '')
passw = os.getenv('HYPHOST_PASSWORD', '')
if hostn == '':
    hostn = raw_input('Host: ')
if passw == '':
    passw = getpass.getpass("Password: ")
 
# main
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    try:
        ssh.connect(hostn, username='root', password=passw, timeout=10)
        stdin, stdout, stderr = ssh.exec_command("yum clean all")
        stdin.close()
        for line in stdout.read().splitlines():
            print line
    except socket.error, (errnum, errmsg):
        print "Connection error occured: ", errmsg, " [", errnum, "]"
        sys.exit(10)
    except paramiko.AuthenticationException:
        print "Error: authentication failed"
        sys.exit(11)
finally:
    ssh.close()

sys.exit(0)
