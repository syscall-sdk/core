server {
    server_name syscall-sdk.com www.syscall-sdk.com;

    location / {
        # Cible : Votre Docker sur le port 8090
        proxy_pass http://192.168.1.250:8090;

        # Headers indispensables
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/syscall-sdk.com/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/syscall-sdk.com/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot


}

server {
    if ($host = www.syscall-sdk.com) {
        return 301 https://$host$request_uri;
    } # managed by Certbot


    if ($host = syscall-sdk.com) {
        return 301 https://$host$request_uri;
    } # managed by Certbot


    listen 80;
    server_name syscall-sdk.com www.syscall-sdk.com;
    return 404; # managed by Certbot

}
