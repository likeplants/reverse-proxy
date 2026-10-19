
#!/bin/bash
set -Eeuo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo bash $0"
    exit 1
fi

DUMMY_IF="dummy0"
DUMMY_IP="192.168.255.254"
ROUTE_TABLE="111"
RULE_PRIORITY="1000"
SSHL_CONFIG="/etc/default/sslh"
BACKUP="/etc/default/sslh.backup"
DROPIN_DIR="/etc/systemd/system/sslh.service.d"
DROPIN="$DROPIN_DIR/override.conf"
SERVICE_FILE="/etc/systemd/system/sslh-transparent-setup.service"

echo "1. Loading dummy driver..."
modprobe dummy

echo "2. Configuring dummy interface..."
ip link show "$DUMMY_IF" >/dev/null 2>&1 ||
    ip link add "$DUMMY_IF" type dummy
ip addr replace "$DUMMY_IP/32" dev "$DUMMY_IF"
ip link set "$DUMMY_IF" up

echo "3. Configuring transparent routing..."
ip route replace local 0.0.0.0/0 dev "$DUMMY_IF" table "$ROUTE_TABLE"

if ! ip rule show | grep -Eq "^[[:space:]]*${RULE_PRIORITY}:.*from ${DUMMY_IP}(/32)? .*lookup ${ROUTE_TABLE}"; then
    ip rule add priority "$RULE_PRIORITY" from "$DUMMY_IP/32" table "$ROUTE_TABLE"
fi

if [[ "${1:-}" == "--setup-only" ]]; then
    echo "Setup-only mode complete."
    exit 0
fi

echo "4. Backing up sslh configuration..."
if [[ ! -e "$BACKUP" ]]; then
    cp -a "$SSHL_CONFIG" "$BACKUP"
fi

echo "5. Configuring sslh transparent mode..."
cat > "$SSHL_CONFIG" <<'EOF'
DAEMON=/usr/sbin/sslh
DAEMON_OPTS="--user sslh --listen 0.0.0.0:443 --transparent --ssh 192.168.255.254:22 --ssl 192.168.255.254:8443"
EOF

echo "6. Configuring systemd capabilities and dependency..."
mkdir -p "$DROPIN_DIR"

cat > "$DROPIN" <<'EOF'
[Unit]
Requires=sslh-transparent-setup.service
After=sslh-transparent-setup.service

[Service]
CapabilityBoundingSet=CAP_SETGID CAP_SETUID CAP_NET_BIND_SERVICE CAP_NET_RAW
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_RAW
EOF

echo "7. Installing boot-time routing service..."
SCRIPT_PATH="$(readlink -f "$0")"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=SSlh transparent proxy routing setup
Before=sslh.service

[Service]
Type=oneshot
ExecStart=/bin/bash "$SCRIPT_PATH" --setup-only
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

echo "8. Reloading systemd and enabling routing service..."
systemctl daemon-reload
systemctl enable sslh-transparent-setup.service

echo "9. Starting routing setup service..."
systemctl start sslh-transparent-setup.service

echo "10. Restarting sslh..."
systemctl restart sslh

echo "11. Verifying service..."
if ! systemctl is-active --quiet sslh; then
    echo "ERROR: sslh failed to start. Recent logs:"
    journalctl -u sslh -n 40 --no-pager
    exit 1
fi

systemctl --no-pager --full status sslh

echo
echo "12. Verifying running arguments..."
ps -eo args | grep '[s]slh'

echo
echo "Routing rules:"
ip rule show
ip route show table "$ROUTE_TABLE"

echo
echo "SUCCESS: Configuration applied."
echo "Boot-time routing service installed and enabled."

