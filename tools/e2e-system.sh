#!/usr/bin/env bash
# End to end on a fresh Akari system (the dev VM): setup, sign-in, sessions,
# accounts, sudo, ssh, sign-out, delete, akarid restart. Run as root in the VM:
#   tools/devvm.sh ssh sudo /opt/akari/src/tools/e2e-system.sh
# Makes the accounts e2e-admin and e2e-user and removes e2e-user again; the
# passwords are random and never printed.
set -uo pipefail
U=https://127.0.0.1
J=$(mktemp -d); trap 'rm -rf "$J"' EXIT
P1=$(head -c 18 /dev/urandom | base64 | tr -d '/+=')
P2=$(head -c 18 /dev/urandom | base64 | tr -d '/+=')
fails=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fails=$((fails + 1)); }
check() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
api() {  # api JAR METHOD PATH [JSON] → body, status in $J/status
  local jar=$1 m=$2 p=$3 d=${4:-}
  curl -sk -o "$J/body" -w '%{http_code}' -b "$J/$jar" -c "$J/$jar" -X "$m" -H 'Content-Type: application/json' \
       -H "Origin: $U" ${d:+--data "$d"} "$U$p" > "$J/status"
  cat "$J/body"
}
status() { cat "$J/status"; }

for _ in $(seq 1 30); do curl -sfk $U/api/login/state >/dev/null && break; sleep 1; done
echo "Einrichten"
if [[ $(curl -sk $U/api/login/state | python3 -c 'import sys,json; print(json.load(sys.stdin)["setup"])') == True ]]; then
  TOKEN=$(grep -o 'token=[A-Za-z0-9_-]*' /run/issue.d/50-akari.issue | head -1 | cut -d= -f2)
  api a POST /api/login/setup "{\"token\":\"$TOKEN\",\"name\":\"e2e-admin\",\"fullname\":\"E2E Admin\",\"password\":\"$P1\"}" >/dev/null
  check "das erste Konto entsteht mit dem Link von der Konsole" '[[ $(status) == 200 ]]'
else
  echo "  (schon eingerichtet: e2e-admin bekommt ein neues Passwort)"
  echo "e2e-admin:$P1" | chpasswd
  api a POST /api/login "{\"name\":\"e2e-admin\",\"password\":\"$P1\"}" >/dev/null
fi
check "e2e-admin ist ein Linux-Benutzer mit zsh" '[[ $(getent passwd e2e-admin | cut -d: -f7) == /bin/zsh ]]'
check "… in der Gruppe sudo" 'id -nG e2e-admin | grep -qw sudo'
check "… mit eigenem Home (0700)" '[[ $(stat -c %a /home/e2e-admin) == 700 ]]'
check "sudo nimmt sein Passwort" "echo '$P1' | runuser -u e2e-admin -- sudo -S -k true"

echo "Sitzung"
api a GET /api/session >/dev/null
check "angemeldet: /api/session antwortet" '[[ $(status) == 200 ]]'
UID1=$(id -u e2e-admin)
check "akari-session@e2e-admin läuft" 'systemctl is-active -q akari-session@e2e-admin'
check "… als logind-Sitzung mit /run/user/$UID1" '[[ -d /run/user/$UID1 ]] && loginctl list-sessions --no-legend | grep -q e2e-admin'
check "… der Agent-Socket gehört dem Benutzer" '[[ $(stat -c %U /run/user/$UID1/akari/agent.sock) == e2e-admin ]]'
api a GET /api/stats >/dev/null
check "eine Agent-Anfrage geht durch (/api/stats)" '[[ $(status) == 200 ]]'
check "der Agent läuft als e2e-admin, nicht als root" '[[ $(ps -o user= -p $(systemctl show -p MainPID --value akari-session@e2e-admin)) == e2e-admin ]]'
check "LANG kommt aus /etc/default/locale" "tr '\\0' '\\n' < /proc/\$(systemctl show -p MainPID --value akari-session@e2e-admin)/environ | grep -x \"\$(grep '^LANG=' /etc/default/locale)\""

echo "Konten"
api a POST /api/accounts "{\"name\":\"e2e-user\",\"fullname\":\"E2E User\",\"password\":\"$P2\",\"admin\":false}" >/dev/null
check "ein zweites Konto entsteht" '[[ $(status) == 200 ]] && getent passwd e2e-user'
check "… ohne sudo" '! id -nG e2e-user | grep -qw sudo'
api b POST /api/login "{\"name\":\"e2e-user\",\"password\":\"falsch-falsch\"}" >/dev/null
check "ein falsches Passwort kommt nicht herein" '[[ $(status) == 401 ]]'
api b POST /api/login "{\"name\":\"root\",\"password\":\"$P1\"}" >/dev/null
check "root kommt nie herein" '[[ $(status) == 401 ]]'
api b POST /api/login "{\"name\":\"e2e-user\",\"password\":\"$P2\"}" >/dev/null
check "das richtige schon (PAM)" '[[ $(status) == 200 ]] && systemctl is-active -q akari-session@e2e-user'
api b PATCH /api/accounts/me '{"fullname":"E2E Zwei"}' >/dev/null
check "der volle Name landet in /etc/passwd" 'getent passwd e2e-user | grep -q "E2E Zwei"'
check "die Anmeldeseite zeigt beide" "curl -sk $U/api/login/state | grep -q e2e-user"

echo "SSH"
api b POST /api/ssh/password "{\"allow\":true,\"password\":\"$P2\"}" >/dev/null
check "e2e-user erlaubt sein Passwort über ssh" '[[ $(status) == 200 ]] && grep -q "Match User e2e-user" /etc/ssh/sshd_config.d/akari.conf'
check "sshd: Passwort für e2e-user" 'sshd -T -C user=e2e-user,host=x,addr=192.0.2.1 | grep -x "passwordauthentication yes"'
check "sshd: kein Passwort für e2e-admin" 'sshd -T -C user=e2e-admin,host=x,addr=192.0.2.1 | grep -x "passwordauthentication no"'
check "sshd: root nie" 'sshd -T -C user=root,host=x,addr=192.0.2.1 | grep -x "permitrootlogin no"'
check "sshd: der Rest von sshd_config gilt weiter" 'sshd -T -C user=e2e-user,host=x,addr=192.0.2.1 | grep -q "^subsystem sftp"'
check "ssh.service läuft noch" 'systemctl is-active -q ssh'
check "/api/ssh sieht ihn" "[[ \$(api a GET /api/ssh | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[\"running\"] and bool(d[\"fingerprints\"]))') == True ]]"

echo "Abmelden, löschen, Neustart"
api b POST /api/logout '{"mode":"end"}' >/dev/null
sleep 1
check "Abmelden beendet die Sitzung von e2e-user" '! systemctl is-active -q akari-session@e2e-user'
api a DELETE /api/accounts/e2e-user >/dev/null
check "e2e-user ist gelöscht, samt Home" '[[ $(status) == 200 ]] && ! getent passwd e2e-user && [[ ! -d /home/e2e-user ]]'
check "… und nicht mehr in akari.conf" '! grep -q e2e-user /etc/ssh/sshd_config.d/akari.conf'
systemctl restart akarid; sleep 2
check "nach einem Neustart von akarid läuft die Sitzung von e2e-admin weiter" 'systemctl is-active -q akari-session@e2e-admin'
api a POST /api/login "{\"name\":\"e2e-admin\",\"password\":\"$P1\"}" >/dev/null
check "… und die Anmeldung findet sie wieder" '[[ $(status) == 200 ]] && [[ $(api a GET /api/stats >/dev/null; status) == 200 ]]'

echo "Apps"
DID=$(api a POST /api/session/desktop '{"name":"E2E"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["desktop"]["id"])')
api a POST /api/display/xterm '{"w":800,"h":600}' >/dev/null
check "xterm startet auf einem Desktop" '[[ $(status) == 200 ]]'
sleep 3
check "… in Xvnc, als e2e-admin" 'pgrep -u e2e-admin -x Xvnc && pgrep -u e2e-admin -x xterm'
api a POST /api/logout '{"mode":"end"}' >/dev/null
sleep 1
check "Abmelden beendet Xvnc und xterm" '! pgrep -u e2e-admin -x Xvnc && ! pgrep -u e2e-admin -x xterm'
check "… und die logind-Sitzung" '! loginctl list-sessions --no-legend | grep e2e-admin | grep -qv manager'

echo
[[ $fails == 0 ]] && echo "alles gut" || echo "$fails Fehler"
exit $fails
