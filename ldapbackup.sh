#!/bin/bash
############################################################
#
# ldapbackup.sh
#       - shell script to backup & compress openldap
#         in LDIF format (portability)
#
#       Authour: Denis Prezhevalsky
#       Date:    21 October 2009
#
############################################################
# set -x
############################################################

# Global variables

############################################################

# Hostname
MYNAME=`/bin/hostname`

# Maximum number of backups to keep
# It always leave MAX_BKPS+1 backups, because
# first it checks for limit, remove old backups
# and after create new one
MAX_BKPS=30

# How many local diskspace in kB should be free
# 1 GB = 1048576 kB
SIZE=1048576

# Backup folder
BKP_FOLDER="/var/backups/ldap"

# Backup name
BKP_NAME=`/bin/date +%Y%m%d`-`/bin/date +%H%M%S`.${MYNAME}.ldif

# Log file
BKP_LOG="${BKP_FOLDER}/ldapbkp.log"

# Datestamp configuration
T2DAY=`/bin/date +%F`
T2DAY_TIME=`/bin/date +%H-%M-%S`

# LDAP backup utility
LDAPDUMP="/usr/local/openldap/sbin/slapcat"
LDAPCONF="/usr/local/openldap/etc/openldap/slapd.conf"

# Mails to notify
# delimited by space
TO_MAIL="user@gmail.com"

# Local var
LOG_LINES=0

############################################################
# Functions
############################################################

function check_free_space() {
        # check free space
        AVAL_KB=`/bin/df -P / | grep / | awk '{print $4}'`
        if [ ${SIZE} -eq ${AVAL_KB} -o ${SIZE} -gt ${AVAL_KB} ];
        then
                return 28       # No space left on device
        fi
        return 0
}

function write_to_log() {
        D_NOW=`/bin/date +%F`
        T_NOW=`/bin/date +%T`
        echo "${D_NOW} ${T_NOW}: $1" >> ${BKP_LOG}
        LOG_LINES=`expr ${LOG_LINES} + 1`
}

function compress() {
        # check for empty name
        #
        if [ "$1." == "." ];
        then
                write_to_log "compress failed - empty or no filename has been provided"
                return 22       # Invalid argument
        fi
        if [[ ! -f ${BKP_FOLDER}/${1} ]];
        then
                write_to_log "compress failed - file not exists"
                return 22       # Invalid argument
        fi
        /bin/gzip ${BKP_FOLDER}/${1}
        ERR_CODE=$?
        if [ "${ERR_CODE}" -eq "0" ];
        then
                return 0        # Success
        elif [ "${ERR_CODE}" -eq "2" ];
        then
                write_to_log "compress failed - filename \"$1\" not found"
                return 22       # Invalid argument
        else
                write_to_log "compress failed - unknown error ${ERR_CODE}"
        fi
        return 5                # Input/output error
}

function clean_old_backups() {
        if [ "$1." == "." ];
        then
                write_to_log "clean_old_backups failed - empty or no directory has been provided"
                return 22       # Invalid argument
        fi

        DUMPCOUNT=`ls ${1}/ | grep .gz | wc -l | sed -e 's/ //g'`
        if [[ ${DUMPCOUNT} -gt ${MAX_BKPS} ]];
        then
                HEADCOUNT=`expr ${DUMPCOUNT} - ${MAX_BKPS}`
                DELETEFILES=`ls -tr ${1}/*.gz | head -${HEADCOUNT}`
                write_to_log "clean_old_backups - removing old backups: ${DELETEFILES}"
                /bin/rm -rf ${DELETEFILES}
        fi
}

function ldap_backup() {
        #slapcat -v -f /usr/local/openldap/etc/openldap/slapd.conf -l $(date +%Y%m%d).ldif
        ${LDAPDUMP} -v -f ${LDAPCONF} -l  ${BKP_FOLDER}/${BKP_NAME} > /dev/null 2>&1
        ERR_CODE=$?
        if [ "${ERR_CODE}" -eq "0" ];
        then
                return 0        # Success
        else
                return 1        # Failer
        fi
}

function send_mail() {
        for ML_ADDR in ${TO_MAIL}
        do
                /usr/bin/tail -${LOG_LINES} ${BKP_LOG} | /bin/mail -s "DB - mysql backup job" ${ML_ADDR}
        done
}

############################################################
# Main
############################################################

# check for arguments first
#
if [ $# -ne 0 ]; then
        echo 1>&2 Usage: $0
        exit 127
fi

write_to_log "Backup started"

# check for backup destination folder
# if not exists, create it
#
if [[ ! -d ${BKP_FOLDER} ]];
then
        /bin/mkdir -m 700 -p ${BKP_FOLDER}
fi

# check for ldap utility
#
if [[ ! -f ${LDAPDUMP} ]];
then
        write_to_log "failed to find ldap utility (default: ${LDAPDUMP})"
        exit 2
fi

# check for ldap config
#
if [[ ! -f ${LDAPCONF} ]];
then
        write_to_log "failed to find ldap config (default: ${LDAPCONF})"
        exit 2
fi

#
# check free space on disk
#
check_free_space
if [ "$?" -eq "28" ];
then
        write_to_log "check_free_space() - diskspace limit has been reached (LIMIT: ${SIZE}kB AVALIABLE: ${AVAL_KB}kB) - exiting"
        write_to_log "Backup finished"
        send_mail
        echo "No free diskspace left - exiting"
        exit 28
fi

#
# backup ldap data
#
clean_old_backups ${BKP_FOLDER}

ldap_backup

if [ "$?" -eq "0" ];
then
        write_to_log "OpenLDAP - backup successfull"
        #
        # compress created backup
        #
        compress ${BKP_NAME}
        if [ "$?" -eq "0" ];
        then
                write_to_log "file \"${BKP_NAME}\" - compression successfull"
                echo "Done: ${BKP_FOLDER}/${BKP_NAME}.gz"
        else
                write_to_log "file \"${BKP_NAME}\" - compression failed"
                echo "Failed to compress ${BKP_NAME}"
        fi
else
        write_to_log "file \"${BKP_NAME}\" - backup failed"
        echo "Failed to backup \"${BKP_NAME}\" database"
fi

write_to_log "Backup finished"

send_mail

############################################################
# End
############################################################
exit 0
