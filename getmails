#!/bin/sh
# vim:se tw=78 sts=4:
# Copyright (C) 2011-2017 Osamu Aoki <osamu@debian.org>, GPL2+
set -e
if [ "$1" = "-p" ]; then
    para=true
    shift
elif [ "$1" = "--" ]; then
    para=false
    shift
else
    para=false
fi
# check file extension
endwith () {
[ "$1" != "${1%$2}" ] && return 0 || return 1
}
startswith () {
BASE1=${1##*/}
[ "$BASE1" != "${BASE1#$2}" ] && return 0 || return 1
}
UID_BY_ID=$(id -u)
PID_GETMAILS=$(pgrep -U $UID_BY_ID '^getmails$')
if [ "x$PID_GETMAILS" != "x$$" ]; then
	echo "The getmails script is already running as PID=\"$PID_GETMAILS\" ." >&2
	exit 1
fi
configdir=${XDG_CONFIG_HOME:-$HOME/.config}
if [ ! -d "$configdir" ]; then
    getmailrcdir="$HOME/.getmail/config"
else
    getmailrcdir="$configdir/getmail"
fi
if [ -f $getmailrcdir/stop ]; then
    #note: stop needs to be in the config folder now
	echo "Do not run getmail ... (if not, remove $getmailrcdir/stop)" >&2
	exit 1
fi
rcfiles="/usr/bin/getmail"
# Address concerns raised by #863856
#  emacs backup files:   foo~ foo#
#  vim backup files:     foo~ foo.swp
#  generic backup files: foo.bak
# These are excluded but let's allow file names with @
if $para ; then
    pids=""
    for file in $getmailrcdir/* ; do
        if ! endwith "$file" '~' && \
           ! endwith "$file" '#' && \
           ! startswith "$file" 'oldmail-' && \
           ! endwith "$file" '.swp' && \
           ! endwith "$file" '.bak' ; then
	    $rcfiles --rcfile "$file" "$@" &
	    pids="$pids $!"
        fi
    done
    rc=0
    if [ -n "$pids" ]; then
	for pid in $pids ; do
	    wait $pid
	    prc=$?
	    if [ $prc -gt $rc ]; then
		rc=$prc
	    fi
	done
    fi
    exit $rc
else
    for file in $getmailrcdir/* ; do
        if ! endwith "$file" '~' && \
           ! endwith "$file" '#' && \
           ! startswith "$file" 'oldmail-' && \
           ! endwith "$file" '.swp' && \
           ! endwith "$file" '.bak' ; then
    	rcfiles="$rcfiles --rcfile \"$file\""
        fi
    done
    eval "$rcfiles $@"
    exit $?
fi

