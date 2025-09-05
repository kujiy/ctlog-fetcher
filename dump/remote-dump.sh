ssh shinichi@192.168.0.180 \
  "mysqldump -uroot --single-transaction --master-data=2 --databases ct | gzip -c" \
  > ct_$(date +%Y%m%d).sql.gz
