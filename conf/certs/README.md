Place your TLS certificate + private key(s) for your domain here like

```
./<domain>/fullchain.pem
./<domain>/privkey.pem
```

Then edit `../nginx/nginx.conf` to update the path to the chain/key.