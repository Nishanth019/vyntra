import pymysql

# Pure-Python MySQL driver in place of mysqlclient, so it installs on Vercel without MySQL C libraries.
pymysql.install_as_MySQLdb()
