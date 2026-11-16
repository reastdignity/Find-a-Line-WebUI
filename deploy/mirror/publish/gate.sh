#!/bin/sh
# The publishing account's command gate (sshd_config: ForceCommand). Whatever the key asks to run,
# sshd runs this instead, with the request in SSH_ORIGINAL_COMMAND. Allowed, and nothing else:
#   /usr/lib/ssh/sftp-server   the SFTP server (rclone's transfers, renames, listings, free space);
#                              files it writes get mode 644, folders 755 (umask 022): readable by
#                              the file server's uid 101
#   sha256sum <one path>       the sha256 of one regular file whose resolved path lies under
#                              /mirror (rclone's server-side hash, sha256sum_command = sha256sum)
# Everything else is refused with "refused" on stderr and exit status 1: a shell, any other
# command, an empty command, a path outside /mirror (also through "..", or through a symlink the
# account made over SFTP), a device, a FIFO or a folder (sha256sum of /dev/zero would never end),
# more than one path, shell syntax, a line break, a request longer than MAX_REQUEST bytes.
#
# rclone (backend/sftp, quoteOrEscapeShellPath, shell_type = unix) writes the path with a backslash
# before every character outside [A-Za-z0-9_.,:/@-] and non-ASCII bytes, so a name with a space,
# ";", "$" or "'" arrives as "a\ b\;c\$d\'e". An unescaped character outside that set means
# shell syntax or a second argument: refused.
set -u

MIRROR=/mirror
MAX_REQUEST=4096

refuse() {
    echo "refused" >&2
    exit 1
}

request=${SSH_ORIGINAL_COMMAND-}
newline='
'
case $request in *"$newline"* | *"$(printf '\r')"*) refuse ;; esac
[ ${#request} -le $MAX_REQUEST ] || refuse

case $request in
    /usr/lib/ssh/sftp-server)
        exec /usr/lib/ssh/sftp-server -u 022
        ;;
    "sha256sum "*)
        escaped=${request#sha256sum }
        [ -n "$escaped" ] || refuse
        # Only escaped pairs, the safe characters and non-ASCII bytes
        rest=$(printf '%s' "$escaped" | sed 's/\\.//g' | tr -d 'A-Za-z0-9_.,:/@-' | LC_ALL=C tr -d '\200-\377')
        [ -z "$rest" ] || refuse
        case $escaped in *\\) refuse ;; esac
        path=$(printf '%s' "$escaped" | sed 's/\\\(.\)/\1/g')
        case $path in "$MIRROR"/*) ;; *) refuse ;; esac
        case "$path/" in */../* | */./* | *//*) refuse ;; esac
        resolved=$(readlink -f -- "$path" 2> /dev/null) || refuse
        case $resolved in "$MIRROR"/*) ;; *) refuse ;; esac
        [ -f "$resolved" ] && [ ! -L "$resolved" ] || refuse
        exec sha256sum "$resolved"
        ;;
esac
refuse
