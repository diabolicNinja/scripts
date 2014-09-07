#!/bin/sh

############################################################
#
# mysqlbackup.sh
#       - shell script to backup & compress mysql
#         database
#
#       Authour: Denis Prezhevalsky
#       Date:    08 July 2008
#
############################################################

# set -x

############################################################
# Global variables
############################################################

# Maximum number of backups to keep
# It always leave MAX_BKPS+1 backups, because
# first it checks for limit, remove old backups
# and after create new one
MAX_BKPS=30

# 10 GB = 10485760 kB
SIZE=10485760

# Backup folder
BKP_FOLDER="/var/backups/mysql"

# Log file
BKP_LOG="${BKP_FOLDER}/mysqlbkp.log"

# Datestamp configuration
T2DAY=`/bin/date +%F`
T2DAY_TIME=`/bin/date +%H-%M-%S`

# Mysql root password
MYSQL_PASS="secret"

# Mysql backup utility
MYSQLDUMP="/usr/bin/mysqldump"

# Error utility
MYSQLPERR="/usr/bin/perror"


# List of databases to backup
# delimited by space
DBS="mysql wikidb"

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

function mysql_db_backup() {
        # check for empty name
        #
        if [ "$1." == "." ];
        then
                return 22       # Invalid argument
        fi

        # dump mysql database
        #
        DB_BACKUP_NAME="$1_${T2DAY}_${T2DAY_TIME}.sql"
        /usr/bin/mysqldump --quote-names --opt -u root --password=${MYSQL_PASS} $1 > ${BKP_FOLDER}/${1}/${DB_BACKUP_NAME}

        # check for errors/success
        #
        ERR_CODE=$?
        DB=${DB_BACKUP_NAME}
        if [ "${ERR_CODE}" -eq "0" ];
        then
                return 0        # Success
        elif [ "${ERR_CODE}" -eq "2" ];
        then
                /bin/rm -rf ${BKP_FOLDER}/${1}/${DB_BACKUP_NAME}
                write_to_log "mysql_db_backup failed - database name \"$1\" not found"
                return 22       # Invalid argument
        else
                if [[ -f ${MYSQLPERR} ]];
                then
                        P_ERR=`${MYSQLPERR} ${ERR_CODE}`
                        P_ERR="(${P_ERR})"
                fi
                write_to_log "mysql_db_backup failed - unknown error ${P_ERR}"
        fi
        return 5                # Input/output error
}

function compress() {
        # check for empty name
        #
        if [ "$1." == "." ];
        then
                write_to_log "compress failed - empty or no filename has been provided"
                return 22       # Invalid argument
        fi
        if [ "$2." == "." ];
        then
                write_to_log "compress failed - empty or no database name has been provided"
                return 22       # Invalid argument
        fi
        if [[ ! -f ${BKP_FOLDER}/${2}/${1} ]];
        then
                write_to_log "compress failed - file not exists"
                return 22       # Invalid argument
        fi
        /bin/gzip ${BKP_FOLDER}/${2}/${1}
        ERR_CODE=$?

        if [ "${ERR_CODE}" -eq "0" ];
        then
                return 0        # Success
        elif [ "${ERR_CODE}" -eq "2" ];
        then
                write_to_log "compress failed - filename \"$1\" not found"
                return 22       # Invalid argument
        else
                if [[ -f ${MYSQLPERR} ]];
                then
                        P_ERR=`${MYSQLPERR} ${ERR_CODE}`
                        P_ERR="(${P_ERR})"
                fi
                write_to_log "compress failed - unknown error ${P_ERR}"
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



function send_mail() {
        for ML_ADDR in ${TO_MAIL}
        do
                /usr/bin/tail -${LOG_LINES} ${BKP_LOG} | /bin/mail -s "DB - mysql backup job" -r dprezhev@redhat.com ${ML_ADDR}
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

# check for mysqldump utility
#
if [[ ! -f ${MYSQLDUMP} ]];
then
        write_to_log "failed to find mysqldump utility (default: ${MYSQLDUMP})"
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
# backup mysql database
#
for DB in ${DBS}
do
        DBO=${DB}
        # check if folder for each database exists
        #
        if [[ ! -d ${BKP_FOLDER}/${DB} ]];
        then
                /bin/mkdir -m 700 -p ${BKP_FOLDER}/${DB}
        fi

        clean_old_backups ${BKP_FOLDER}/${DB}
        mysql_db_backup ${DB}
        if [ "$?" -eq "0" ];
        then
                write_to_log "database \"${DBO}\" - backup successfull"
                #
                # compress created backup
                #
                compress ${DB} ${DBO}
                if [ "$?" -eq "0" ];
                then
                        write_to_log "file \"${DB}\" - compression successfull"
                        echo "Done: ${BKP_FOLDER}/${DBO}/${DB}.gz"
                else
                        write_to_log "file \"${DB}\" - compression failed"
                        echo "Failed to compress ${DB}"
                fi
        else
                write_to_log "database \"${DB}\" - backup failed"
                echo "Failed to backup \"${DBO}\" database"
        fi
done

write_to_log "Backup finished"
send_mail

############################################################
# End
############################################################

exit 0
