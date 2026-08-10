# same as: sudo lsof -t -i :443 | xargs sudo kill -9
# replaced: kill -9 $(cat run.pid)

pids=$(sudo lsof -t -i :443)

if [ -n "$pids" ]; then
    echo "Killing process(es): $pids"
    sudo kill -9 $pids
else
	echo "Warning: No process currently running on rort 443 (can not kill)"
fi
