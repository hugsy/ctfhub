Place your TLS certificate + private key(s) for your domain here like

```
./<domain>/fullchain.pem
./<domain>/privkey.pem
```

Then edit `../nginx/nginx.conf` to update the path to the chain/key.


Note:
-----

For local development, you can use [mkcert](https://github.com/FiloSottile/mkcert) to generate the certificates.

```
# If this is the first time you are using mkcert, create a local CA:
mkcert -install

# Generate a new certificates with the different subdomains:
mkcert ctfpad.mydomain.com hedgedoc.mydomain.com excalidraw.mydomain.com collab.excalidraw.mydomain.com

# Move the generated certificates to the certs folder. Assuming you are at the repository root folder:
mkdir -p ./conf/certs/ctpdad.mydomain.com
mv ctfpad.mydomain.com*-key.pem ./conf/certs/ctpdad.mydomain.com/privkey.pem
mv ctfpad.mydomain.com*.pem ./conf/certs/ctpdad.mydomain.com/fullchain.pem
```

If `ctfpad.mydomain.com` is in your `/etc/hosts` files, then you'll be able to access the app on this DNS.
