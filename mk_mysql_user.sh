#!/bin/bash

USER=$1
PW=$2

mysql -e "CREATE USER '${USER}'@'localhost' IDENTIFIED BY '${PW}';"
mysql -e "GRANT ALL PRIVILEGES ON * . * TO '${USER}'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"