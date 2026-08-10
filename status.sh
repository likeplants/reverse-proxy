# status.sh

if sudo lsof -i :443 -sTCP:LISTEN -t >/dev/null; then
    echo "Running: something is listening on port 443"
    sudo lsof -i :443 -sTCP:LISTEN
else
    echo "Stopped: nothing is listening on port 443"
fi
