#!/bin/bash -e

echo 'Logging in to heroku'
heroku login

echo 'Installing ctfpad'
cd /tmp
mkdir ctfpad && cd ctfpad

git clone https://github.com/hugsy/ctfpad .

heroku apps:create ctfp4d
heroku addons:create heroku-postgresql:hobby-dev
eval $(heroku config -s | grep DATABASE_URL)

DB=$(python -c "from urllib.parse import urlparse;u=urlparse('$DATABASE_URL');print(u.username,u.password,u.hostname,u.port,u.path.strip('/'))")

heroku config:set CTFPAD_HOSTNAME=ctfp4d.herokuapp.com
heroku config:set CTFPAD_DB_USER=$(echo $DB | cut -d' ' -f1)
heroku config:set CTFPAD_DB_PASSWORD=$(echo $DB | cut -d' ' -f2)
heroku config:set CTFPAD_DB_HOST=$(echo $DB | cut -d' ' -f3)
heroku config:set CTFPAD_DB_PORT=$(echo $DB | cut -d' ' -f4)
heroku config:set CTFPAD_DB_NAME=$(echo $DB | cut -d' ' -f5)
heroku config:set HEDGEDOC_URL=https://h3dgedoc.herokuapp.com
heroku config:set CTFPAD_USE_SSL=0

echo 'python-3.9.1' > runtime.txt

cat > Procfile <<'EOF'
release: python manage.py migrate
web: python manage.py runserver 0.0.0.0:$PORT --noreload
EOF

# uncomment to import previous db
#ADDON=$(heroku pg:info | grep Add-on:| cut -d: -f2)
#heroku pg:push postgres://ctfpad:p4ssw0rd@localhost:5432/ctfpad $ADDON

git push heroku master

echo 'Installing hedgedoc'
cd /tmp
mkdir hedgedoc && cd hedgedoc
git clone https://github.com/hedgedoc/hedgedoc.git .
git checkout -b fix 1.7.2

heroku create h3dgedoc

heroku config:set DATABASE_URL=$DATABASE_URL
heroku config:set CMD_DB_URL=$DATABASE_URL
heroku config:set CMD_DOMAIN=h3dgedoc.herokuapp.com
heroku config:set CMD_URL_ADDPORT=false
heroku config:set CMD_PROTOCOL_USESSL=true
heroku config:set CMD_ALLOW_ANONYMOUS=false
heroku config:set CMD_ALLOW_FREEURL=true
heroku config:set CMD_IMAGE_UPLOAD_TYPE=filesystem
heroku config:set CMD_COOKIE_POLICY=none


cat > bin/heroku <<'EOA'
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

git commit -m fix bin/heroku
git push heroku fix:master
heroku logs --tail
