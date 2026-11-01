#!/bin/bash
# Find-a-Line: the notice of an SSH login (docs/monitoring.md, D4; docs/deployment.md, section 15).
# deploy/vps.sh installs it as /usr/local/sbin/findaline-ssh-login (root's, 0755, the checkout's
# path in place of @REPO@) and adds one line to /etc/pam.d/sshd:
#   session optional pam_exec.so quiet /usr/local/sbin/findaline-ssh-login
# sshd runs it as root when a session opens and closes (PAM_TYPE); on open_session it
# - posts "SSH login: <user> from <address> on <server>" to the ntfy topic of the alerts (the URL
#   in the checkout's secrets/ntfy_url, as Grafana's), in the background with a 5 s limit, so
#   the login never waits for ntfy;
# - counts the login in /var/lib/findaline-monitoring/ssh.json ({"time": <the last login>,
#   "logins": <in total>}, no user or address; Telegraf's input file), under flock.
# It never fails a login: `optional` in PAM ignores its exit status, it always exits 0, and every
# step that could wait has a limit (the lock 2 s; curl runs detached).
PATH=/usr/local/bin:/usr/bin:/bin   # pam_exec passes no PATH of its own
NTFY_URL_FILE=@REPO@/secrets/ntfy_url
OUT=/var/lib/findaline-monitoring

[ "${PAM_TYPE:-}" = open_session ] || exit 0

# Printable characters only (both come from PAM: the account and the client's address or name)
clean() { printf '%s' "$1" | tr -cd '[:alnum:]._:@%-' | cut -c1-80; }
user=$(clean "${PAM_USER:-unknown}")
from=$(clean "${PAM_RHOST:-unknown}")
server=$(hostname)

url=$(tr -d '\r\n' < "$NTFY_URL_FILE" 2>/dev/null)
if [[ $url =~ ^https?://[^[:space:]]+$ ]]; then
    setsid curl -fsS -m 5 -o /dev/null -H "Title: SSH login on $server" -H "Tags: key" \
        -d "SSH login: $user from $from on $server" "$url" </dev/null >/dev/null 2>&1 &
fi

if [ -d "$OUT" ]; then
    (
        flock -w 2 9 || exit 0
        logins=$(sed -n 's/.*"logins": *\([0-9][0-9]*\).*/\1/p' "$OUT/ssh.json" 2>/dev/null)
        tmp=$(mktemp "$OUT/.ssh.json.XXXXXX") || exit 0
        printf '{"time": %s, "logins": %s}\n' "$(date +%s)" "$(( ${logins:-0} + 1 ))" > "$tmp" \
            && chmod 644 "$tmp" && mv -f "$tmp" "$OUT/ssh.json"
        rm -f "$tmp"
    ) 9>>"$OUT/.ssh.lock" 2>/dev/null
fi
exit 0
