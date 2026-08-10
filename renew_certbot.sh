certbot certonly --cert-name reverse-proxy --dns-digitalocean --dns-digitalocean-credentials ./digitalocean.ini -d humusmonitor.de -d "*.humusmonitor.de" -d apistack.eu -d "*.apistack.eu"
#sudo certbot certonly --standalone -d humusmonitor.de -d www.humusmonitor.de -d apistack.eu -d www.apistack.eu -d fieldslope.apistack.eu
