server {
    server_name syscall-relayer.syscall-sdk.com;

    location / {
        proxy_pass http://192.168.1.250:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/syscall-relayer.syscall-sdk.com/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/syscall-relayer.syscall-sdk.com/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot

}

server {
    if ($host = syscall-relayer.syscall-sdk.com) {
        return 301 https://$host$request_uri;
    } # managed by Certbot


    listen 80;
    server_name syscall-relayer.syscall-sdk.com;
    return 404; # managed by Certbot

}
