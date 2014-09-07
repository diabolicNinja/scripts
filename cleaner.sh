#!/bin/bash
 
################################################
#
#       FILE CLEANER
#
#       Written by: Denis Prezhevalsky
#       Mail:       denis@prezhevalsky.com
#
################################################
 
BASEDIR='/home'
RETENTION=14            # days
MINQUOTA=500            # Kb
LOGFILE="/var/log/cleaning.log"
MAILS='denisp@prezhevalsky'
SRVNAME=`/bin/hostname 2> /dev/null`
EXCLUDES="/home/backup_dir /home/someotherdir"
MYPID=$$
 
################################################
# FUNCTIONS
################################################
 
function write2log() {
        local argv=${1}
        if [ -z "${argv}" ]; then
                echo >> ${LOGFILE}
        else
                local TODAY=`date +"%F %T"`
                echo "[${TODAY}] [PID ${MYPID}] : ${argv}" >> ${LOGFILE}
        fi
}
 
function sendreport() {
        local arg_title=${1}
        for ML_ADDR in ${MAILS}; do
                grep "PID ${MYPID}]" ${LOGFILE} | mailx -s "${arg_title}" ${ML_ADDR}
        done
}
 
################################################
# MAIN
################################################
 
write2log "CLEANUP SESSION STARTED"
write2log "Base directory: ${BASEDIR}"
write2log "Retention: ${RETENTION} day/s"
write2log "Quota min: ${MINQUOTA}Kb"
 
# get list of dirs with usage > MINQUOTA
declare -a BLACKLIST
declare -a DIRS
 
HOMES=`find ${BASEDIR} -maxdepth 1 -mindepth 1 -type d 2> /dev/null`
 
# remove excludes
for item in ${HOMES}; do
        ctrl=0
        for x in ${EXCLUDES}; do
                if [ ${x} == ${item} ]; then
                        write2log "excluding ${item}"
                        ctrl=1
                        break
                fi
        done
        if [ ${ctrl} -eq 0 ]; then
                # add to array
                DIRS+=(${item})
        fi
done
 
for homedir in ${DIRS[@]}; do
        dirsize=`du -s ${homedir} 2> /dev/null | awk '{print $1}'`
        if [ ${dirsize} -le ${MINQUOTA} ]; then
                write2log "skipping ${homedir} - usage ${dirsize}Kb"
                continue
        fi
        BLACKLIST+=(${homedir})
done
 
# clean
for userdir in ${BLACKLIST[@]}; do
        if [ ${BLACKLIST} == "/" ]; then
                continue
        fi
        write2log "checking ${userdir} directory"
        FLIST=`find ${userdir}* -mtime +${RETENTION} -type f -size +10k -exec ls {} \; 2> /dev/null`
        for xfile in ${FLIST}; do
                rm -rf ${xfile}
                write2log "${xfile} removed"
        done
done
 
write2log "CLEANUP SESSION ENDED"
 
sendreport "${SRVNAME} cleanup report"
 
exit 0
 
################################################
# END
################################################
