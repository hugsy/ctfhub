#!/bin/bash -ex

echo 'Logging in to heroku'
heroku login

echo 'Creating the ctfpad and hedgedoc apps and a postgres db in the Europe region'

CTFPAD_URL=$(heroku apps:create --region eu | cut -d' ' -f1)
HEDGEDOC_URL=$(heroku apps:create --region eu | cut -d' ' -f1)
WHITEBOARD_URL=$(heroku apps:create --region eu | cut -d' ' -f1)

CTFPAD_NAME=$(echo $CTFPAD_URL | cut -d/ -f3 | cut -d. -f1)
HEDGEDOC_NAME=$(echo $HEDGEDOC_URL | cut -d/ -f3 | cut -d. -f1)
WHITEBOARD_NAME=$(echo $WHITEBOARD_URL | cut -d/ -f3 | cut -d. -f1)

heroku addons:create -a $CTFPAD_NAME heroku-postgresql:hobby-dev
DATABASE_URL=$(heroku config -a $CTFPAD_NAME -s | grep DATABASE_URL | cut -d\' -f2)


echo 'Installing ctfpad'
cd $(mktemp -d)

git clone https://github.com/hugsy/ctfpad .

DB=(`python -c "from urllib.parse import urlparse
u = urlparse('$DATABASE_URL')
print(u.username, u.password, u.hostname, u.port, u.path.strip('/'))"`)

heroku config:set -a $CTFPAD_NAME CTFPAD_HOSTNAME=$(echo $CTFPAD_URL | cut -d/ -f3)
heroku config:set -a $CTFPAD_NAME CTFPAD_PORT=443
heroku config:set -a $CTFPAD_NAME CTFPAD_USE_SSL=0
heroku config:set -a $CTFPAD_NAME CTFPAD_DB_USER=${DB[0]}
heroku config:set -a $CTFPAD_NAME CTFPAD_DB_PASSWORD=${DB[1]}
heroku config:set -a $CTFPAD_NAME CTFPAD_DB_HOST=${DB[2]}
heroku config:set -a $CTFPAD_NAME CTFPAD_DB_PORT=${DB[3]}
heroku config:set -a $CTFPAD_NAME CTFPAD_DB_NAME=${DB[4]}
heroku config:set -a $CTFPAD_NAME CTFPAD_SECRET_KEY=$(openssl rand -base64 32)
heroku config:set -a $CTFPAD_NAME HEDGEDOC_URL=${HEDGEDOC_URL%/}
heroku config:set -a $CTFPAD_NAME WHITEBOARD_URL=${WHITEBOARD_URL%/}

echo 'python-3.9.1' > runtime.txt

cat > Procfile <<'EOF'
release: python manage.py migrate
web: python manage.py runserver 0.0.0.0:$PORT --noreload
EOF

# uncomment to import previous db
#ADDON=$(heroku pg:info | grep Add-on: | cut -d: -f2)
#heroku pg:push postgres://ctfpad:p4ssw0rd@localhost:5432/ctfpad $ADDON

heroku git:remote -a $CTFPAD_NAME

git checkout -b hero master
git add Procfile runtime.txt
git commit -a -m Heroku\ files
git push heroku hero:master


echo 'Installing hedgedoc'
cd $(mktemp -d)

git clone https://github.com/hedgedoc/hedgedoc.git .
git checkout -b fix 1.7.2

heroku config:set -a $HEDGEDOC_NAME CMD_DB_URL=$DATABASE_URL
heroku config:set -a $HEDGEDOC_NAME CMD_DOMAIN=$(echo $HEDGEDOC_URL | cut -d/ -f3)
heroku config:set -a $HEDGEDOC_NAME CMD_URL_ADDPORT=false
heroku config:set -a $HEDGEDOC_NAME CMD_PROTOCOL_USESSL=true
heroku config:set -a $HEDGEDOC_NAME CMD_ALLOW_ANONYMOUS=false
heroku config:set -a $HEDGEDOC_NAME CMD_ALLOW_FREEURL=true
heroku config:set -a $HEDGEDOC_NAME CMD_IMAGE_UPLOAD_TYPE=filesystem
heroku config:set -a $HEDGEDOC_NAME CMD_COOKIE_POLICY=none

cat > bin/heroku << EOA
#!/bin/bash

set -e

cat << EOF > .sequelizerc
var path = require('path');

module.exports = {
    'config':          path.resolve('config.json'),
    'migrations-path': path.resolve('lib', 'migrations'),
    'models-path':     path.resolve('lib', 'models')
}
EOF

cat << EOF > config.json
{
  "production": {
    "url": "$DATABASE_URL",
    "dbURL": "$DATABASE_URL",
    "dialectOptions": {
      "ssl": {
        "require": true,
        "rejectUnauthorized": false
      }
    },
    "db": {
      "dialectOptions": {
        "ssl": {
          "require": true,
          "rejectUnauthorized": false
        }
      }
    }
  }
}
EOF

EOA

heroku git:remote -a $HEDGEDOC_NAME

git commit -m fix bin/heroku
git push heroku fix:master


echo 'Installing whiteboard'
cd $(mktemp -d)

git clone https://github.com/cracker0dks/whiteboard .
git checkout master

heroku git:remote -a $WHITEBOARD_NAME

git push heroku master


echo "All done. Visit $CTFPAD_URL"
