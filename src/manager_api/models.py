# MySQL table definitions (initial draft)
# Reference: cert_parser.py

from sqlalchemy import Column, Integer, String, DateTime, Boolean, create_engine, BigInteger, Text, Index, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class Cert(Base):
    __tablename__ = 'certs'
    id = Column(Integer, primary_key=True)
    issuer = Column(String(256))
    common_name = Column(String(512))
    not_before = Column(DateTime)
    not_after = Column(DateTime)
    serial_number = Column(String(256))
    subject_alternative_names = Column(Text)  # JSON string
    certificate_fingerprint_sha256 = Column(String(128))
    subject_public_key_hash = Column(String(128))
    public_key_algorithm = Column(String(64))
    key_size = Column(Integer)
    signature_algorithm = Column(String(128))
    ct_log_timestamp = Column(DateTime)
    crl_urls = Column(String(2048))
    ocsp_urls = Column(String(2048))
    vetting_level = Column(String(8))  # 'dv', 'ov', 'ev'

    san_count = Column(Integer)
    issued_on_weekend = Column(Boolean)
    issued_at_night = Column(Boolean)
    organization_type = Column(String(32))
    is_wildcard = Column(Boolean)
    root_ca_issuer_name = Column(String(512))
    is_precertificate = Column(Boolean, default=None)

    log_name = Column(String(64))
    ct_index = Column(BigInteger, default=None)  # index within the log
    ct_log_url = Column(String(256))
    worker_name = Column(String(64))
    created_at = Column(DateTime)
    ct_entry = Column(Text)  # Entire CT log entry as JSON string
    # No DB-level unique constraint; uniqueness is enforced at API level

    # Indexes for performance optimization
    __table_args__ = (
        # For unique certificate identification in /api/logs_summary (optimized for COUNT(DISTINCT issuer, serial_number))
        Index('idx_cert_unique_optimized', 'issuer', 'serial_number'),
        # For log_name filtering
        Index('idx_cert_log_name', 'log_name'),
        # For created_at ordering/filtering
        Index('idx_cert_created_at', 'created_at'),
        # Additional separate indexes for better performance on individual fields
        Index('idx_cert_issuer', 'issuer', mysql_length={'issuer': 100}),
        Index('idx_cert_common_name', 'common_name', mysql_length={'common_name': 100}),
        Index('idx_cert_serial_number', 'serial_number', mysql_length={'serial_number': 100}),
    )

class UploadStat(Base):
    __tablename__ = 'upload_stats'
    id = Column(Integer, primary_key=True)
    log_name = Column(String(64))
    worker_name = Column(String(64))
    date = Column(DateTime)
    count = Column(Integer, default=0)
    issuer = Column(String(256), default=None)
    common_name = Column(String(512), default=None)

    # Indexes for performance optimization
    __table_args__ = (
        # For filter_by queries in /api/worker/upload (using prefix indexes)
        Index('idx_upload_stat_lookup', 'log_name', 'worker_name', 'date', 'issuer', 'common_name', mysql_length={'issuer': 50, 'common_name': 50}),
        # For date-based queries
        Index('idx_upload_stat_date', 'date'),
        # Additional separate indexes for better performance
        Index('idx_upload_stat_log_worker', 'log_name', 'worker_name'),
        Index('idx_upload_stat_issuer', 'issuer', mysql_length={'issuer': 100}),
    )

class WorkerStatus(Base):
    __tablename__ = 'worker_status'
    id = Column(Integer, primary_key=True)
    worker_name = Column(String(64))
    log_name = Column(String(64))
    ct_log_url = Column(String(256))
    start = Column(BigInteger)
    end = Column(BigInteger)
    current = Column(BigInteger)                        # All indices up to this are processed
    last_uploaded_index = Column(BigInteger, default=None)    # Last index where upload succeeded
    status = Column(String(32))  # running, finished, resume_wait, etc
    last_ping = Column(DateTime)
    ip_address = Column(String(64), default=None)
    jp_count = Column(BigInteger, default=0)
    jp_ratio = Column(Integer, default=0)

    # Indexes for performance optimization
    __table_args__ = (
        # For status and ct_log_url filtering in /api/worker/next_task
        Index('idx_worker_status_lookup', 'status', 'ct_log_url'),
        # For log_name filtering
        Index('idx_worker_log_name', 'log_name'),
        # For composite lookup in worker ping/completed/resume endpoints
        Index('idx_worker_task_lookup', 'log_name', 'start', 'end'),
        # For ordering by last_ping in /api/workers_status
        Index('idx_worker_last_ping', 'last_ping'),
        # For status filtering (resume_wait queries)
        Index('idx_worker_status', 'status'),
        # CREATE INDEX idx_workerstatus_logname_status_end ON worker_status (log_name, status, end);
        Index('idx_worker_status_logname_status_end', 'log_name', 'status', 'end'),
    )


class CTLogSTH(Base):
    __tablename__ = 'ct_log_sth'
    id = Column(Integer, primary_key=True, autoincrement=True)
    log_name = Column(String(64), index=True, nullable=False)
    ct_log_url = Column(String(256), nullable=False)
    tree_size = Column(BigInteger, nullable=False)
    sth_timestamp = Column(DateTime, nullable=False)
    fetched_at = Column(DateTime, nullable=False)

    # Indexes for performance optimization
    __table_args__ = (
        # For ct_log_url filtering and fetched_at ordering in get_tree_size()
        Index('idx_sth_url_fetched', 'ct_log_url', 'fetched_at'),
        # For log_name and fetched_at grouping in /api/logs_summary and /api/logs_progress
        Index('idx_sth_log_fetched', 'log_name', 'fetched_at'),
    )



class UniqueCert(Base):
    __tablename__ = 'unique_certs'
    id = Column(Integer, primary_key=True)
    issuer = Column(String(256))
    common_name = Column(String(512))
    not_before = Column(DateTime)
    not_after = Column(DateTime)
    serial_number = Column(String(256))
    subject_alternative_names = Column(Text)
    certificate_fingerprint_sha256 = Column(String(128))
    subject_public_key_hash = Column(String(128))
    public_key_algorithm = Column(String(64))
    key_size = Column(Integer)
    signature_algorithm = Column(String(128))
    ct_log_timestamp = Column(DateTime)   # TODO: Changed to DateTime
    crl_urls = Column(String(2048))
    ocsp_urls = Column(String(2048))
    vetting_level = Column(String(8))
    san_count = Column(Integer)
    issued_on_weekend = Column(Boolean)
    issued_at_night = Column(Boolean)
    organization_type = Column(String(32))
    is_wildcard = Column(Boolean)
    root_ca_issuer_name = Column(String(512))
    is_precertificate = Column(Boolean, default=None)
    log_name = Column(String(64))
    ct_index = Column(Integer, default=None)
    ct_log_url = Column(String(256))
    worker_name = Column(String(64))
    created_at = Column(DateTime)
    ct_entry = Column(Text)
    inserted_at = Column(DateTime)

    __table_args__ = (
        Index('idx_unique_cert_unique', 'issuer', 'serial_number', unique=True),
        Index('idx_unique_cert_created_at', 'created_at'),
        Index('idx_unique_cert_inserted_at', 'inserted_at'),
    )

class WorkerLogStat(Base):
    __tablename__ = 'worker_log_stats'
    id = Column(Integer, primary_key=True)
    log_name = Column(String(64), index=True, nullable=False)
    worker_name = Column(String(64), index=True, nullable=False)
    worker_total_count = Column(BigInteger, default=0)
    jp_count_sum = Column(BigInteger, default=0)
    last_updated = Column(DateTime)
    # Add other necessary statistics if needed

    # Indexes for performance optimization
    __table_args__ = (
        # For composite lookup in update_worker_status_and_summary()
        Index('idx_worker_log_stat_lookup', 'log_name', 'worker_name'),
        # For worker_name grouping in /api/worker_ranking
        Index('idx_worker_log_stat_worker', 'worker_name'),
    )





class LogFetchProgress(Base):
    __tablename__ = 'log_fetch_progress'
    id = Column(Integer, primary_key=True)
    category = Column(String(64), index=True, nullable=False)
    log_name = Column(String(64), index=True, nullable=False)
    min_completed_end = Column(BigInteger, nullable=True)
    sth_end = Column(BigInteger, nullable=True)
    fetch_rate = Column(Float, nullable=True)  # 取得率
    status = Column(String(32), nullable=False)  # "completed" or "in_progress"
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('idx_log_fetch_progress_cat_log', 'category', 'log_name', unique=True),
        Index('idx_log_fetch_progress_status', 'status'),
    )

# Example DB connection
#engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/ct')
# Base.metadata.create_all(engine)
# Session = sessionmaker(bind=engine)
# session = Session()

if __name__ == "__main__":
    # Test table creation
    engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/ct')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
