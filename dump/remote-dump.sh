mysqldump -h 192.168.0.180 -u root --single-transaction --master-data=2 --databases ct \
| mysql -u root
