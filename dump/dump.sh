date
mysqldump -uroot --single-transaction --master-data=2 --databases ct | gzip > ct.sql.gz
date
echo done.