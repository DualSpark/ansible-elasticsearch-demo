#!/bin/bash
#~KIBANA_URL=
#~KIBANA_PASSWORD=
#~ELASTICSEARCH_ELB_DNS_NAME=
#~ELASTICSEARCH_BACKUP_BUCKET=
#~ELASTICSEARCH_SNAPSHOT_NAME=
sudo apt-get update -y
sudo apt-get install apache2-utils nginx -y
wget $KIBANA_URL --output-document /tmp/kibana-3.1.0.tar.gz 
sudo mkdir -p /opt/kibana
sudo tar xvf /tmp/kibana-3.1.0.tar.gz -C /tmp
sudo cp -R /tmp/kibana-3.1.0/* /opt/kibana/
sudo chown www-data:www-data /opt/kibana/* -R
sudo htpasswd -bc /opt/kibana/.htpasswd kibanauser $KIBANA_PASSWORD
sudo sed -i "s/:9200/\/elasticsearch/g" /opt/kibana/config.js

cat > /tmp/nginx.conf << EOF
user www-data; 
worker_processes 2;
pid /var/run/nginx.pid;
events {
    worker_connections  1024;
}
http {
    gzip on;
    gzip_disable "msie6";
    include       mime.types;
    default_type  application/xml;
    log_format upstreamlog '[\$time_local] - \$remote_addr - \$elasticsearch_path\$is_args\$args - \$upstream_response_time - \$request_time - \$body_bytes_sent - \$uri - \$proxy_port';
    error_log /var/log/nginx/notice.log notice;
    server { 
        listen 81;
        return 200;
        access_log off;
    }
    server {
        listen       80;
        auth_basic "Restricted";
        auth_basic_user_file /opt/kibana/.htpasswd;
        resolver 169.254.169.253;
        location / {
            root /opt/kibana;
            index index.html index.htm;
        }
        location ~^/elasticsearch/(?<elasticsearch_path>.*)\$ {
            access_log /var/log/nginx/upstream.log upstreamlog;
            proxy_pass http://$ELASTICSEARCH_ELB_DNS_NAME:9200/\$elasticsearch_path\$is_args\$args;
            proxy_pass_request_headers      on;
            access_log on;
        }
    }
}
EOF

sudo mv /tmp/nginx.conf /etc/nginx/nginx.conf
sudo service nginx restart
