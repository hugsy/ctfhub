# CTFPad

## What

A webapp for managing CTFs by teams playing [CTFs](https://en.wikipedia.org/wiki/Wargame_(hacking)). If you're looking for a platform for hosting CTFs use [CTFd](https://github.com/ctfd/ctfd).


## Build


For most people, this will suffice:

```
$ git clone https://github.com/hugsy/ctfpad
$ cd ctfpad
$ cp .env.example .env
### CHANGE THE CREDENTIALS IN .env ###
$ nano .env
### BUILD EXCALIDRAW USING .env VARIABLES ###
$ make build
$ docker compose up -d --build
```

If you want to use SSL locally, follow the [instructions to generate local SSL certificates](./conf/README.md)
and run:

```
$ cp .env.nginx-proxy.example .env
$ docker compose -f docker-compose-proxy.yml -f docker-compose.yml up -d --build

```

## Features

A non-exhaustive list of features:

 - Full Django + Python 3 code
 - Clean (Bootstrap) interface
 - Key-in-hands setup via [`docker-compose`](https://docs.docker.com/compose)
 - Fully built on top of [HedgeDoc](https://github.com/hedgedoc/hedgedoc): smart markdown note mechanism, with [tons of features](https://demo.hedgedoc.org/features)
 - Possibility to create and play private CTFs
 - Internal statistic system to track members' involment + basic ranking system
 - [Jitsi](https://meet.jit.si) integration: instantly jump on video chat with your team mate
 - CTFTime integration: import CTF (+ data) from CTFTime in 2 clicks
 - Dark mode (duh!)
 - Basic search engine
 - Self-hosted [Excalidraw](https://github.com/excalidraw/excalidraw) integration: draw & share ideas with your team mates
 - Discord notifications
 - ...and more to come...

## Community ##

[![Discord](https://img.shields.io/badge/Discord-CTFPad-green)](https://discord.gg/5HmwPxy3HP) 

## Gallery

_Note_: the development of CTFPad is very active, the screenshots below might not reflect the exact state of the tool.

### Dashboard

![dashboard](https://i.imgur.com/vWvgjQ1.png)

### View CTF

![ctf](https://i.imgur.com/kEJo9Jj.png)
![ctf2](https://i.imgur.com/fe3vvfC.png)

### Import CTFs from CTFtime

![ctftime](https://i.imgur.com/TnOupMe.png)


### Challenge

![challenge1](https://i.imgur.com/YRvXs3u.png)


### Statistics

![stats](https://i.imgur.com/PGsPztU.png)





## Why

I was fed up of not finding a tool to my liking to manage CTFs for teams playing so I wrote one. You should probably not use it 😋 I wrote it quickly because I really couldn't find something that fitted my needs. Some other projects of the sort of collaboration during CTFs:

 - [CTFPad](https://github.com/StratumAuhuur/CTFPad): nice project but NodeJS, so yeah. Also  [`etherpad-lite`](https://yopad.eu) doesn't support MarkDown easily. I like the name, so I took it shamelessly
 - [rizzoma](http://rizzoma.com/): a horrible outdated collaborative platform, poorly suited for CTFs.

I discovered [HedgeDoc](https://demo.hedgedoc.org/features?both) (aka. old CodiMD), an awesome platform, 100% Markdown, easily integrable. This project is just an eye-candy around using HedgeDoc as a central platform when doing a challenge collaboratively.

It's a toy project, so there's a lot of TODOs, features will be added (slowly).

### Notes

Flag images are downloaded from https://flagpedia.net/
