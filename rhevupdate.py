#!/usr/bin/env python
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
############################################################
#   Author:	    Denis Prezhevalsky (deniska@redhat.com)
#   Date:           25 July 2015
#   Version:        1.0
#   Description:    python script to update RHEV 3.5
#                   hypervisors
#   Ref:            https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Virtualization/3.5/index.html
############################################################ 
import paramiko
import getpass
import socket
import os
import sys
import argparse
import ConfigParser
import string
import base64
import logging as log
from ovirtsdk.api import API
from ovirtsdk.xml import params

#import urllib2
#import libvirt
#import yum

# variables
_version        = 1.0
_base_filename  = os.path.splitext(__file__)[0]
_engine_addr    = None
_engine_user    = None
_engine_pass    = None
_engine_cacert  = None
_conn_string    = None
_api_url        = None
_ca_url         = None
_datacenters    = []

# logging (INFO/DEBUG)
log.basicConfig(level=log.DEBUG,
                format   =  '%(asctime)s %(levelname)-8s %(message)s',
                datefmt  =  '%d %b %Y %H:%M:%S',
                filename =  _base_filename + ".log",
                filemode =  'a')

log.debug("initializing")

# parse configuration file
log.debug("parsing configuration file " + _base_filename + ".conf");
config = ConfigParser.ConfigParser()
fs = config.read(_base_filename + ".conf")
if len(fs) != 0:
    for section in config.sections():
        if string.lower(section) == 'engine':
            for var in config.options(section):
                if var == 'hostname':
                    _engine_addr = config.get(section, var)
                elif  var == 'username':
                    _engine_user = config.get(section, var)
                elif  var == 'password':
                    _engine_pass = config.get(section, var)
                    _engine_pass = base64.b64decode(_engine_pass);
                elif var == 'cacertpath':
                    _engine_cacert = config.get(section, var)

# command line args
log.debug("parsing command line arguments");
parser = argparse.ArgumentParser(description="Update RHEV hypervisor/s", epilog="Example: %(prog)s -e x.y.z.w -u root -p secret host1 host2...")
parser.add_argument("-l", "--list", action="store_const", const=0, dest="action", help="list datacenter/cluster/host with status")
parser.add_argument("-U", "--update", action="store_const", const=1, dest="action", help="update datacenter/cluster/host")
parser.add_argument("-f", "--file", type=file, help="file with hosts to update")
parser.add_argument("-c", "--cacert", type=file, help="path to CA certificate")
parser.add_argument("-d", "--datacenter", help="datacenter name")
parser.add_argument("-e", "--engine", help="rhev engine address")
parser.add_argument("-u", "--username", help="rhev engine username (yum run privileges)")
parser.add_argument("-p", "--password", help="rhev engine password")
parser.add_argument("-s", "--hypervisor", nargs='+', help="hypervisor/s to apply updates to")
parser.add_argument('--version', action='version', version=str(_version))
parser.add_argument("-v", "--verbose", action="store_true")
args = parser.parse_args()

_action = args.action
if not _action:
    _action = 0

if args.engine:
    _engine_addr = args.engine
elif _engine_addr:
    _engine_addr = _engine_addr
else:
    _engine_addr = raw_input('Engine:   ')

if args.username:
    _engine_user = args.username
if _engine_user:
    _engine_user = _engine_user
else:
    _engine_user = raw_input('Username: ')

if args.password:
    _engine_pass = args.password
if _engine_pass:
    _engine_pass = _engine_pass
else:
    _engine_pass = getpass.getpass("Password: ")

if args.cacert:
    _engine_cacert = args.cacert
elif _engine_cacert:
    _engine_cacert = _engine_cacert
else:
    _engine_cacert = raw_input('CA cert:  ')


# acquire ca from engine if not provided
_ca_name = "ca.crt"
_ca_url  = "http://" + _engine_addr + "/" + _ca_name
if not _engine_cacert or os.path.exists(_engine_cacert) is False:
    log.debug("downloading " + _ca_url)
    try:
        response = urllib2.urlopen(_ca_url)
    except HTTPError as e:
        log.debug("server couldn\'t fulfill the request (error code: " +  e.code + ")")
    except URLError as e:
        log.debug("failed to reach server: " +  e.reason )
    else:
        with open(_ca_name, "wb") as code:
            code.write(response.read())
        _engine_cacert = os.getcwd() + "/" + _ca_name

if os.path.exists(_engine_cacert) is False:
    print("CA certificate is not available or not valid - unable to proceed (see log for details) ")
    log.debug("CA certificate " + _engine_cacert + " is not available or not valid - unable to proceed")
    sys.exit(2)
else:
    log.debug("CA certificate acquired: " + _engine_cacert)

# connect to engine
_api_url = "https://" + _engine_addr + "/api"
try:
    api = API(url = _api_url, username = _engine_user, password = _engine_pass, ca_file = _engine_cacert)
    log.debug("connection established with rhevm api: " + _api_url)
except Exception as e:
    log.debug(str(e))
    sys.exit(3)

try:
    # get datacenter list
    datacenters = api.datacenters.list()
    for dc in datacenters:
        _datacenters.append(dc.name.upper())

    # "list" action
    if _action == 0:
        for datacenter in datacenters:
            print(" %15s: %20s  %15s" % ("datacenter", (datacenter.name).upper(), datacenter.status.state ))
            for cluster in datacenter.clusters.list():
                print(" %15s: %20s" % ("cluster", cluster.name) )
                hosts = api.hosts.list(query = 'cluster=' + cluster.name)
                #hosts = api.hosts.get( id=api.vms.get(obj.name).get_host().get_id() ).get_name()
                #cluster.get_href()
                for host in hosts:
                    print(" %15s: %20s  %15s  %10s  %40s  %25s  %25s" % ("host", host.name, host.status.state, host.summary.active, host.os.get_type() + " " + host.os.version.get_full_version(), host.version.get_full_version(), host.libvirt_version.get_full_version()) )
            print("")

    # "update" action
    elif _action == 1:
        for datacenter in datacenters:
            print(" %15s: %20s  %15s" % ("datacenter", (datacenter.name).upper(), datacenter.status.state ))
        print("")
        userinput = raw_input('Select datacenters to update (space separated, "all" to update everything): ')
        dcs = userinput.split()
        if not dcs:
            print("error: no input - exiting")
            sys.exit(0)
        elif dcs[0].lower() != "all":
            for dc in [(d.strip()) for d in dcs]:
                if dc.upper() not in _datacenters:
                    print("error: " + dc + " is not valid datacenter name or not exists - skipping")
                    dcs.remove(dc)
        else:
            dcs = _datacenters
            print("going to update all datacenters")

        for d in dcs:
            print(d)

except Exception as e:
    log.debug(str(e))
    sys.exit(4)
finally:
    api.disconnect()
    log.debug("connection closed")

# temp exit point
sys.exit(0)


## update os
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

# finish
log.debug("end reached - exiting")
sys.exit(0)
