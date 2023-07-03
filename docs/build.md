# Build an instance

## Basic setup

```bash
$ git clone https://github.com/hugsy/ctfhub
$ cd ctfhub
$ cp .env.example .env
### CHANGE THE CREDENTIALS IN .env ###
$ nano .env
### BUILD EXCALIDRAW USING .env VARIABLES ###
$ docker compose up -d --build
```

## SSL + nginx reverse-proxy on Docker

A standard secure way to deploy an instance of CTFHub is to use it over an SSL layer, and behind a reverse proxy.
Using [Let's Encrypt]() you can easily generate a valid SSL certificate, which can be used with an nginx container acting as a reverse-proxy. A boilerplate template was provided to you in `scripts/nginx`, which you can use in combination of the [instructions to generate local SSL certificates](../conf/certs/README.md). Then run `docker compose` with multiple files as such:

```bash
$ cp scripts/proxy/.env.nginx-proxy.example scripts/proxy/.env
$ nano scripts/proxy/.env
### Edit the file to your need
$ docker compose -f scripts/proxy/docker-compose.yml -f ./docker-compose.yml up -d --build
```

Note that the example env file have default variables that may not suit your environment. Adjust them to your needs.

## Deploy your instance for Excalidraw

In `scripts/excalidraw` :

```bash
$ cd scripts/excalidraw
$ cp .env.example .env
$ nano .env
### edit .env to match your configuration
$ cd ../..
$ nano .env
### update the CTFHUB_EXCALIDRAW_URL setting to point to your local excalidraw
```

Note that the example env file have default variables that may not suit your environment. Adjust them to your needs.

## Receive Discord notifications

Create a [HTTP Webhook](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) on your Discord and paste that link to the setting `CTFHUB_DISCORD_WEBHOOK_URL` in your `.env` file.

## Receive Email notifications

Edit your `.env` and populate the following fields:

```conf
CTFHUB_EMAIL_SERVER_HOST=''                                 # smtp.gmail.com or mailgun, or sendgrid etc.
CTFHUB_EMAIL_SERVER_PORT=0
CTFHUB_EMAIL_USERNAME=''
CTFHUB_EMAIL_PASSWORD=''
```

With the appropriate values


## Migration

If you're migrating from the first versions called `ctpad`, check out see [PR #83](https://github.com/hugsy/ctfhub/pull/83) to migrate the data to the new environment, search the `Setup > Migration` part.

