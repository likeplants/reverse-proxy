bash kill443.sh
nohup python reverse_proxy_server.py > nohup.out 2>&1 & echo $! > run.pid
