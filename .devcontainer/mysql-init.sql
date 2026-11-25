-- README_CoCa.md grants the CCS user permission to create all application
-- schemas. MySQL's MYSQL_USER default grant only covers MYSQL_DATABASE.
GRANT ALL PRIVILEGES ON *.* TO 'ccs'@'%';
FLUSH PRIVILEGES;
