# CTFPad

## What

A webapp for managing CTFs by teams playing [CTFs](https://en.wikipedia.org/wiki/Wargame_(hacking)). If you're looking for a platform for hosting CTFs use [CTFd](https://ctfd.io).




## Build


For most people, this will suffice:

```
$ git clone https://github.com/hugsy/ctfpad
$ cd ctfpad
### CHANGE THE CREDENTIALS IN docker-compose.yml, Dockerfile, ctftools/settings.py ###
$ docker-compose up -d --build
```


## Gallery

### Dashboard

![dashboard](https://i.imgur.com/4vnCKPo.png)

### View CTF 

![ctf](https://i.imgur.com/3XPxnwB.png)

### Import CTFs from CTFtime

![ctftime](https://i.imgur.com/DFzD5lA.png)

### Challenge

![challenge](https://i.imgur.com/nz2ob76.png)

## Why

I was fed up of not finding a tool to my liking to manage CTFs for teams playing so I wrote one. You should probably not use it 😋 I wrote it quickly because I really couldn't find something that fitted my needs. Some other projects of the sort of collaboration during CTFs:

 - [CTFPad](https://github.com/StratumAuhuur/CTFPad): nice project but NodeJS, so yeah. Also  [`etherpad-lite`](https://yopad.eu) doesn't support MarkDown easily. I like the name, so I took it shamelessly
 - [rizzoma](http://rizzoma.com/): a horrible outdated collaborative platform, poorly suited for CTFs.

I discovered [CodiMD](https://demo.codimd.org), an awesome platform, 100% Markdown, easily integrable. This project is just an eye-candy around using CodiMD as a central platform when doing a challenge collaboratively.

It's a toy project, so there's a lot of TODOs, features will be added (slowly).
