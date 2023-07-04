# Using SSL Certificates for a reverse-proxy

## Development usage

For local development, you can use [mkcert](https://github.com/FiloSottile/mkcert) to generate the certificates.

Example with default settings working with the provided `nginx.conf`:


```bash
# If this is the first time you are using mkcert, create a local CA:
mkcert -install

# Generate a new certificates with the different subdomains:
mkcert ctfhub.mydomain.com hedgedoc.mydomain.com excalidraw.mydomain.com collab.excalidraw.mydomain.com

# Move the generated certificates to the certs folder. Assuming you are at the repository root folder:
mkdir -p ./conf/certs/ctfdad.mydomain.com
mv ctfhub.mydomain.com*-key.pem ./conf/certs/ctfdad.mydomain.com/privkey.pem
mv ctfhub.mydomain.com*.pem ./conf/certs/ctfdad.mydomain.com/fullchain.pem
```

If `ctfhub.mydomain.com` is in the `/etc/hosts` file of your machine, then go to `https://ctfhub.mydomain.com` and enjoy the app!


## Production usage

### Using Let's Encrypt

Generate your LetsEncrypt keys and certificates

```bash
sudo apt-get update && sudo apt-get install certbot # if not already installed
sudo certbot certonly --manual --preferred-challenges=dns
```

Follow the prompt. Certificates will be generated in `/etc/letsencrypt/live/<domain>` in the containers, which can be found in `./certs` on your host.

Use that path to update the nginx configuration file (in `../nginx/nginx.conf`) and run `docker compose up` including the docker-compose file from this folder.

### Using your own certificates

Place your TLS certificate + private key(s) for your domain here like

```
./<domain>/fullchain.pem
./<domain>/privkey.pem
```

Then edit `../nginx/nginx.conf` to update the path to the chain/key.


