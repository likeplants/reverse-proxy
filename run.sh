bash kill8443.sh
#nohup python reverse_proxy_server.py > nohup.out 2>&1 & echo $! > run.pid
nohup uv run reverse_proxy_server.py > nohup.out 2>&1 & echo $! > run.pid
