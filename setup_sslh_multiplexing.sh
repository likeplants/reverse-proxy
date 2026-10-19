#!/bin/bash
echo "sudo apt update"
echo "sudo apt install sslh"
echo "sudo vim /etc/default/sslh"
echo "sudo systemctl enable sslh"
echo "sudo systemctl restart sslh"
echo "sudo systemctl status sslh"
echo "sudo ss -lntp | grep -E ':22|:443|:8443'"
