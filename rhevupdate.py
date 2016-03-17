#!/usr/bin/env python
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
############################################################################################
#   Author:	    Denis Prezhevalsky (deniska@redhat.com)
#   Date:           25 July 2015
#   Version:        1.0
#   Description:    - python script to update RHEV 3.5 / 3.6 hypervisors
#                   - will update ONLY active hypervisors
#   Ref:            https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Virtualization/3.5/index.html
#                   https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Virtualization/3.6-Beta/html/REST_API_Guide/index.html
#                   https://access.redhat.com/documentation/en/red-hat-enterprise-virtualization/
#   Known issues:   - remote ssh session can be stuck if yum already running on remote host
#                   - when connection/vpn failed after api connection initiated - timeout wont work
############################################################################################

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
import time
from ovirtsdk.api import API
from ovirtsdk.xml import params

#import urllib2
#import libvirt
#import yum

############################################################################################
# Variables
############################################################################################

_version        = 1.0
_base_filename  = os.path.splitext(__file__)[0]
_engine_addr    = None
_engine_user    = None
_engine_pass    = None
_engine_cacert  = None
_host_user      = None
_host_pass      = None
_wait_timeout   = 60    # in seconds
_ssh_timeout    = 5     # in seconds
_conn_string    = None
_else_api_url   = None
_ca_url         = None
_loglevel       = "info"
_datacenters    = []

############################################################################################
# Functions
############################################################################################

# todo:
# - if total 2 hosts and 1 failed to update & set active - stop update process
# - check for updates prior to switching host into maintenance mode
# - recover/activate host if update failed
# - count failers and stop if too many [done]
def host_bulkupdate(**hostdlist):
    # sort hosts by number of active vms (ascending)
    hosts = sorted(hostdlist, key=lambda i: int(hostdlist[i]))
    count = 0
    for host in hosts:
        if count > 2:
            print("Multiple failers encountered: " + str(count) )
            while True:
                userinput = raw_input(' Proceed (y/n): ')
                userinput = userinput.strip().lower()
                if userinput not in ["y","n"]:
                    continue
                elif userinput == "n":
                    print(" Action canceled - exiting")
                    sys.exit(0)
                else:
                    break
        address = api.hosts.get(name = host).address
        print(host + ": " + str(hostdlist[host]) + " active vms")
        log.info("switching " + host + " into maintenance mode initiated")
        if host_set_maintenance(host, True):
            log.info("switching " + host + " into maintenance mode completed")
            if update(host):
                log.info(host + " waiting for host to come back online")
                timeout = time.time() + float(_wait_timeout)
                # sleep for 10 seconds before pinging
                time.sleep(10)
                while True:
                    response = os.system("ping -c 1 -w2 " + address + " > /dev/null 2>&1")
                    if response == 0:
                        log.info(host + " is online (ping succeeded)")
                        break
                    elif time.time() > timeout:
                        count += 1
                        log.warning("timeout exceeded (" + _wait_timeout + " seconds)" )
                        break
                    else:
                        time.sleep(1)
                if api.hosts.get(name = host).status.state != "maintenance":
                    log.warning("skipping " + host + " - manual intervation required")
                    count += 1
                    continue
                log.info("switching " + host + " into active mode initiated")
                if host_set_maintenance(host, False):
                    log.info("switching " + host + " into active mode completed")
                else:
                    log.error("switching " + host + " into active mode failed - skipping (manual intervation required)")
                    count += 1
            else:
                log.error("failed to update " + host)
                count += 1
                # todo: host still in maintenance mode - bring it back
                log.info("switching " + host + " into active mode initiated")
                if host_set_maintenance(host, False):
                    log.info("switching " + host + " into active mode completed")
                else:
                    log.error("switching " + host + " into active mode failed - skipping (manual intervation required)")
                    count += 1
        else:
            log.error("switching " + host + " into maintenance mode failed - skipping (manual intervation required)")
            count += 1
    return

def host_set_maintenance(hostname, set_maintenance = True):
    # status values: 
    # down, error, initializing, installing, install_failed, maintenance, 
    # non_operational, non_responsive, pending_approval, preparing_for_maintenance, 
    # connecting, reboot, unassigned and up
    host = api.hosts.get(name = hostname)
    # set maintenance
    # (consider to check for "unassigned" state as well)
    if host.status.state == "up" and set_maintenance:
        host.deactivate()
        timeout = time.time() + float(_wait_timeout)
        while api.hosts.get(name = hostname).status.state != "maintenance":
            if time.time() > timeout:
                log.error("timeout exceeded (" + _wait_timeout + " seconds)" )
                return False
            else:
                time.sleep(1)
    elif host.status.state == "maintenance" and set_maintenance:
        log.debug(hostname + " is already in maintenance mode")
    elif host.status.state == "preparing_for_maintenance" and set_maintenance:
        log.debug(hostname + " is in middle of switching to maintenance mode")
        timeout = time.time() + float(_wait_timeout)
        while api.hosts.get(name = hostname).status.state != "maintenance":
            if time.time() > timeout:
                log.error("timeout exceeded (" + _wait_timeout + " seconds)" )
                return False
            else:
                time.sleep(1)
    elif host.status.state == "reboot" and set_maintenance:
        timeout = time.time() + float(_wait_timeout)
        while api.hosts.get(name = hostname).status.state != "maintenance" or api.hosts.get(name = hostname).status.state != "up":
            if time.time() > timeout:
                log.error("timeout exceeded (" + _wait_timeout + " seconds)" )
                return False
            else:
                time.sleep(1)
        if host.status.state == "up":
            host.deactivate()
            timeout = time.time() + float(_wait_timeout)
            while api.hosts.get(name = hostname).status.state != "maintenance":
                if time.time() > timeout:
                    log.error("timeout exceeded (" + _wait_timeout + " seconds)" )
                    return False
                else:
                    time.sleep(1)

    # set active
    elif host.status.state == "up" and not set_maintenance:
        log.debug(hostname + " is already in active mode")
    elif host.status.state == "maintenance" and not set_maintenance:
        host.activate()
        timeout = time.time() + float(_wait_timeout)
        while api.hosts.get(name = hostname).status.state != "up":
            if time.time() > timeout:
                log.error("timeout exceeded (" + _wait_timeout + " seconds)" )
                return False
            else:
                time.sleep(1)
    elif host.status.state == "preparing_for_maintenance" and not set_maintenance:
        log.debug(hostname + " is in middle of switching to maintenance mode")
        host.activate()
        timeout = time.time() + float(_wait_timeout)
        while api.hosts.get(name = hostname).status.state != "up":
            if time.time() > timeout:
                log.error("timeout exceeded (" + _wait_timeout + " seconds)" )
                return False
            else:
                time.sleep(1)
    elif host.status.state == "reboot" and not set_maintenance:
        timeout = time.time() + float(_wait_timeout)
        while api.hosts.get(name = hostname).status.state != "maintenance" or api.hosts.get(name = hostname).status.state != "up":
            if time.time() > timeout:
                log.error("timeout exceeded (" + _wait_timeout + " seconds)" )
                return False
            else:
                time.sleep(1)
        if host.status.state == "maintenance":
            host.activate()
            timeout = time.time() + float(_wait_timeout)
            while api.hosts.get(name = hostname).status.state != "up":
                if time.time() > timeout:
                    log.error("timeout exceeded (" + _wait_timeout + " seconds)" )
                    return False
                else:
                    time.sleep(1)

    # failure
    else:
        log.error(hostname + " is in invalide state: " + host.status.state)
        return False
    return True

def update(hostname):
    host    = api.hosts.get(name = hostname)
    address = api.hosts.get(name = hostname).address
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        try:
            log.info("connecting to " + address + " via ssh");
            ssh.connect(address, username=_host_user, password=_host_pass, timeout=_ssh_timeout)

            # yum clean all
            stdin, stdout, stderr = ssh.exec_command("yum clean all")
            stdin.close()
            retcode = stdout.channel.recv_exit_status()
            if retcode == 0:
                log.info(hostname + ": cleaning yum cache succeeded")
            else:
                log.error(hostname + ": cleaning yum cache failed")

            # yum check-update
            stdin, stdout, stderr = ssh.exec_command("yum check-update")
            stdin.close()
            retcode = stdout.channel.recv_exit_status()
            ## 100 - there are available packages
            if retcode == 100:
                log.info(hostname + ": updates are available")
            ## 0 - no available updates
            elif retcode == 0:
                log.info(hostname + ": no updates found - skipping")
                # should it be False?
                return False
            ## 1 - error
            elif retcode == 1:
                log.error(hostname + ": [error] checking for updates failed on ")
                for line in stderr.read().splitlines():
                    log.error(hostname + " [error]: " + line)
                return False
            ## unknown 
            else:
                log.error(hostname + ": unknown output while checking for updates - skipping")
                return False

            # yum update
            log.info(hostname + ": yum update initiated")
            stdin, stdout, stderr = ssh.exec_command("yum update -y")
            #stdin, stdout, stderr = ssh.exec_command("yum update gnutls -y")
            stdin.close()
            retcode = stdout.channel.recv_exit_status()
            for line in stdout.read().splitlines():
                log.debug(hostname + ": " + line)
            if retcode != 0:
                log.error(hostname + ": yum update failed [exit code: " + str(retcode) + "]")
                for line in stderr.read().splitlines():
                    log.error(hostname + " [error]: " + line)
                return False
            # on success - reboot
            log.info(hostname + ": yum update completed successfully ")
            stdin, stdout, stderr = ssh.exec_command("/sbin/reboot -f > /dev/null 2>&1 &")
            stdin.close()
            retcode = stdout.channel.recv_exit_status()
            if retcode != 0:
                log.error(hostname + ": failed to reboot [exit code: " + str(retcode) + "]")
                return False
            log.info(hostname + ": reboot successfully initiated ")
            return True
        except socket.error, (errnum, errmsg):
            log.error("failed to connect: " + errmsg + " [" + errnum + "]")
            sys.exit(10)
        except paramiko.AuthenticationException:
            log.error("failed to connect: authentication failed")
            sys.exit(11)
    finally:
        ssh.close()

############################################################################################
# Main
############################################################################################

# logging format
log.basicConfig(level    = log.INFO,
                format   = '%(asctime)s %(levelname)-8s %(message)s',
                datefmt  = '%d %b %Y %H:%M:%S',
                filename = _base_filename + ".log",
                filemode = 'a')

log.info("initializing")

# parse configuration file
log.debug("parsing configuration file " + _base_filename + ".conf");
config = ConfigParser.ConfigParser()
fs = config.read(_base_filename + ".conf")
if len(fs) != 0:
    for section in config.sections():
        if string.lower(section) == 'general':
            for var in config.options(section):
                if var == 'wait_timeout':
                    _wait_timeout = config.get(section, var)
                elif var == 'loglevel':
                    _loglevel = config.get(section, var)
        if string.lower(section) == 'engine':
            for var in config.options(section):
                if var == 'hostname':
                    _engine_addr = config.get(section, var)
                elif var == 'username':
                    _engine_user = config.get(section, var)
                elif var == 'password':
                    _engine_pass = config.get(section, var)
                    _engine_pass = base64.b64decode(_engine_pass);
                elif var == 'cacertpath':
                    _engine_cacert = config.get(section, var)
        if string.lower(section) == 'host':
            for var in config.options(section):
                if var == 'username':
                    _host_user = config.get(section, var)
                elif var == 'password':
                    _host_pass = config.get(section, var)
                    _host_pass = base64.b64decode(_host_pass);
                elif var == 'ssh_timeout':
                    _ssh_timeout = config.get(section, var)

# change logging level
if _loglevel.lower() == "debug":
    log.getLogger().setLevel(log.DEBUG)
elif _loglevel.lower() == "error":
    log.getLogger().setLevel(log.ERROR)
elif _loglevel.lower() == "warning":
    log.getLogger().setLevel(log.WARNING)
else:
    log.getLogger().setLevel(log.INFO)

# command line args
log.debug("parsing command line arguments");
parser = argparse.ArgumentParser(description="Update RHEV hypervisor/s", epilog="Example: %(prog)s -e engine-address -u username -p password")
#parser = argparse.ArgumentParser(description="Update RHEV hypervisor/s", epilog="Example: %(prog)s -e engine-address -u username -p password -s host1 host2...")
parser.add_argument("-l", "--list", action="store_const", const=0, dest="action", help="list datacenter/cluster/host with status")
parser.add_argument("-U", "--update", action="store_const", const=1, dest="action", help="initiate hypervisor update")
#parser.add_argument("-f", "--file", type=file, help="file with hosts to update")
parser.add_argument("-c", "--cacert", type=file, help="path to CA certificate")
parser.add_argument("-e", "--engine", help="rhev engine address")
parser.add_argument("-u", "--username", help="rhev engine username (yum run privileges)")
parser.add_argument("-p", "--password", help="rhev engine password")
#parser.add_argument("-s", "--hypervisor", nargs='+', help="hypervisor/s to apply updates to")
#parser.add_argument('-d', "--datacenter", nargs = '*', help = 'datacenter1 datacenter2 ...', dest="datacenter", default = argparse.SUPPRESS)
#parser.add_argument("-d", "--datacenter", help="datacenter name")
parser.add_argument('--version', action='version', version=str(_version))
#parser.add_argument("-v", "--verbose", action="store_true")
args = parser.parse_args()

#print(args)

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
        log.error("server couldn\'t fulfill the request (error code: " +  e.code + ")")
    except URLError as e:
        log.error("failed to reach server: " +  e.reason )
    else:
        with open(_ca_name, "wb") as code:
            code.write(response.read())
        _engine_cacert = os.getcwd() + "/" + _ca_name

if os.path.exists(_engine_cacert) is False:
    print("CA certificate is not available or not valid - unable to proceed (see log for details) ")
    log.error("CA certificate " + _engine_cacert + " is not available or not valid - unable to proceed")
    sys.exit(2)
else:
    log.info("CA certificate acquired: " + _engine_cacert)

# connect to engine
_api_url = "https://" + _engine_addr + "/api"
try:
    api = API(url = _api_url, username = _engine_user, password = _engine_pass, ca_file = _engine_cacert)
    log.info("connection established with rhevm api: " + _api_url)
except Exception as e:
    log.error(str(e))
    sys.exit(3)

try:
    # get datacenter list
    datacenters = api.datacenters.list()

    # "list" action
    if _action == 0:
        for datacenter in datacenters:
            print(" %15s: %20s  %15s" % ("datacenter", (datacenter.name).upper(), datacenter.status.state ))
            for cluster in datacenter.clusters.list():
                print(" %15s: %20s" % ("cluster", cluster.name) )
                hosts = api.hosts.list(query = 'cluster=' + cluster.name)
                for host in hosts:
                    print(" %15s: %20s  %15s  %10s  %40s  %25s  %25s" % ("host", host.name, host.status.state, host.summary.active, host.os.get_type() + " " + host.os.version.get_full_version(), host.version.get_full_version(), host.libvirt_version.get_full_version()) )
            print("")

    # "update" action
    elif _action == 1:
        print
        print(" Available datacenters:")
        for i in range(0, len(datacenters)):
            counter = i + 1
            print(" %1s. %s" % (counter, datacenters[i].name))
        print("")

        # user's input
        userinput = raw_input(' Select (space separated or "all" for everything): ')
        selected = userinput.split()
        if not selected:
            print(" [error]: no input - exiting")
            sys.exit(0)
        for item in selected:
            item = item.strip().lower()
            if item != "all":
                if item.isdigit() and 0 <= (int(item) - 1) < len(datacenters):
                    _datacenters.append(datacenters[(int(item) - 1)].name)
                else:
                    print(" [warning]: " + item + " not valid selection - skipping")
            else:
                print("going to update all datacenters")
                for dc in datacenters:
                    _datacenters.append(dc.name)
        
        print
        print(" Selected:")
        for dc in _datacenters:
            print(" - " + dc)
        while True:
            userinput = raw_input(' Proceed (y/n): ')
            userinput = userinput.strip().lower()
            if userinput not in ["y","n"]:
                continue
            elif userinput == "n":
                print(" Action canceled - exiting")
                sys.exit(0)
            else:
                # finally starting updates
                break

        # update itself
        print
        for datacenter in _datacenters:
            print(" Updating " + datacenter + ":")
            datacenter = api.datacenters.get(datacenter)
            print(" %15s: %20s" % ("status", datacenter.status.state ))
            for cluster in datacenter.clusters.list():
                hosts2update = {}
                print(" %15s: %20s" % ("cluster", cluster.name) )
                hosts = api.hosts.list(query = 'cluster=' + cluster.name)
                for host in hosts:
                    # add only rhel-h active hosts
                    if host.status.state == "up" and host.os.get_type().lower() == "rhel":
                        hosts2update[host.name] = host.summary.active
                print
            host_bulkupdate(**hosts2update)

except Exception as e:
    log.error("[error]: [line " + format(sys.exc_info()[-1].tb_lineno) + "] " + str(e) )
    sys.exit(4)
finally:
    api.disconnect()
    log.info("connection closed")

###########################################################################################
# Post
###########################################################################################
log.info("end reached - exiting")

sys.exit(0)
###########################################################################################
# END
###########################################################################################
