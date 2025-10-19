# MySQL table definitions (initial draft)
# Reference: cert_parser.py
from enum import Enum

from sqlalchemy import Column, Integer, String, DateTime, Boolean, create_engine, BigInteger, Text, Index, Float
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

class Cert2(Base):
    __tablename__ = 'cert2'

    # Primary key
    id = Column(Integer, primary_key=True)

    # Basic certificate information (kept from original)
    common_name = Column(String(512))
    ct_log_timestamp = Column(DateTime)
    not_before = Column(DateTime)
    not_after = Column(DateTime)

    # Complete issuer DN field (for unique index)
    issuer = Column(String(256))

    # Certificate metadata
    vetting_level = Column(String(8))  # 'dv', 'ov', 'ev'
    issued_on_weekend = Column(Boolean)
    issued_at_night = Column(Boolean)
    organization_type = Column(String(32))
    is_wildcard = Column(Boolean)
    is_precertificate = Column(Boolean, default=None)
    san_count = Column(Integer)
    subject_alternative_names = Column(Text)  # JSON string

    # Relative fields - calculated by comparison with preceeding certificates
    is_automated_renewal = Column(Boolean, default=None)
    days_before_expiry = Column(Integer, default=None)
    issued_after_expiry = Column(Boolean, default=None)
    reuse_subject_public_key_hash = Column(Integer, default=None)  # 0 or 1, indicates if public key is reused

    # Binary indicators for URL presence (converted from original URL fields)
    has_crl_urls = Column(Integer)  # 0 or 1
    has_ocsp_urls = Column(Integer)  # 0 or 1

    # Individual issuer components
    issuer_cn = Column(String(256))  # Common Name
    issuer_o = Column(String(256))   # Organization
    issuer_ou = Column(String(256))  # Organizational Unit
    issuer_c = Column(String(64))    # Country
    issuer_st = Column(String(128))  # State/Province
    issuer_l = Column(String(128))   # Locality/City

    # Complete subject DN field (for analysis)
    subject = Column(String(512))

    # Individual subject components
    subject_cn = Column(String(256))  # Common Name (same as common_name field)
    subject_o = Column(String(256))   # Organization
    subject_ou = Column(String(256))  # Organizational Unit
    subject_c = Column(String(64))    # Country
    subject_st = Column(String(128))  # State/Province
    subject_l = Column(String(128))   # Locality/City

    # Unique certificate identification fields
    serial_number = Column(String(256))
    certificate_fingerprint_sha256 = Column(String(128))
    subject_public_key_hash = Column(String(128))
    public_key_algorithm = Column(String(64))
    key_size = Column(Integer)
    signature_algorithm = Column(String(128))

    # Technical information
    authority_key_identifier = Column(String(128))  # Authority Key Identifier (AKI) hex string
    subject_key_identifier = Column(String(128))   # Subject Key Identifier (SKI) hex string

    # CT log related fields
    log_name = Column(String(64))
    ct_index = Column(BigInteger, default=None)  # index within the log
    worker_name = Column(String(64))
    created_at = Column(DateTime)
    ct_entry = Column(Text)  # Entire CT log entry as JSON string

    # Indexes for performance optimization
    __table_args__ = (
        # Unique index same as UniqueCertCounter model
        Index('idx_cert2_unique', 'issuer', 'serial_number', 'certificate_fingerprint_sha256', unique=True),
        # Additional performance indexes
        Index('idx_cert2_issuer', 'issuer', mysql_length={'issuer': 100}),
        Index('idx_cert2_common_name', 'common_name', mysql_length={'common_name': 100}),
        Index('idx_cert2_ct_log_timestamp', 'ct_log_timestamp'),
    )


class WorkerStatus(Base):
    __tablename__ = 'worker_status2'
    id = Column(Integer, primary_key=True)
    worker_name = Column(String(64))
    log_name = Column(String(64))
    ct_log_url = Column(String(256))
    start = Column(BigInteger)
    end = Column(BigInteger)
    current = Column(BigInteger)                        # All indices up to this are processed
    last_uploaded_index = Column(BigInteger, default=None)    # Last index where upload succeeded
    status = Column(String(32))  # JobStatus - running, finished, resume_wait, etc
    last_ping = Column(DateTime)
    created_at = Column(DateTime)  # When the task was created
    duration_sec = Column(Integer, nullable=True)  # Total duration in seconds (for completed tasks)
    ip_address = Column(String(64), default=None)
    total_retries = Column(Integer, default=0)
    max_retry_after = Column(Integer, default=0)  # Rate limiting wait time in seconds
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


class WorkerStatusAggs(Base):
    __tablename__ = 'worker_status_aggs'
    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime, index=True)
    end_time = Column(DateTime, index=True)
    total_worker_status_count = Column(Integer, default=0)
    # count of each JobStatus, including NULL
    completed = Column(Integer, default=0)
    running = Column(Integer, default=0)
    dead = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    resume_wait = Column(Integer, default=0)
    skipped = Column(Integer, default=0)

    worker_name_count = Column(Integer, default=0)  # distinct worker_name count
    log_name_count = Column(Integer, default=0)  # distinct log_name count
    jp_count_sum = Column(BigInteger, default=0)


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


#
# class UniqueCert(Base):
#     __tablename__ = 'unique_certs'
#     id = Column(Integer, primary_key=True)
#     issuer = Column(String(256))
#     common_name = Column(String(512))
#     not_before = Column(DateTime)
#     not_after = Column(DateTime)
#     serial_number = Column(String(256))
#     subject_alternative_names = Column(Text)
#     certificate_fingerprint_sha256 = Column(String(128))
#     subject_public_key_hash = Column(String(128))
#     public_key_algorithm = Column(String(64))
#     key_size = Column(Integer)
#     signature_algorithm = Column(String(128))
#     ct_log_timestamp = Column(DateTime)   # TODO: Changed to DateTime
#     crl_urls = Column(String(2048))
#     ocsp_urls = Column(String(2048))
#     vetting_level = Column(String(8))
#     san_count = Column(Integer)
#     issued_on_weekend = Column(Boolean)
#     issued_at_night = Column(Boolean)
#     organization_type = Column(String(32))
#     is_wildcard = Column(Boolean)
#     root_ca_issuer_name = Column(String(512))
#     is_precertificate = Column(Boolean, default=None)
#     log_name = Column(String(64))
#     ct_index = Column(Integer, default=None)
#     ct_log_url = Column(String(256))
#     worker_name = Column(String(64))
#     created_at = Column(DateTime)
#     ct_entry = Column(Text)
#     inserted_at = Column(DateTime)
#
#     __table_args__ = (
#         Index('idx_unique_cert_unique', 'issuer', 'serial_number', unique=True),
#         Index('idx_unique_cert_created_at', 'created_at'),
#         Index('idx_unique_cert_inserted_at', 'inserted_at'),
#     )

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
    status = Column(String(32), nullable=False)  # enum: LogFetchProgressStatus
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('idx_log_fetch_progress_cat_log', 'category', 'log_name', unique=True),
        Index('idx_log_fetch_progress_status', 'status'),
    )

class LogFetchProgressStatus(Enum):
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"



class LogFetchProgressHistory(Base):
    __tablename__ = 'log_fetch_progress_history'
    id = Column(Integer, primary_key=True)
    snapshot_timestamp = Column(DateTime, nullable=False)
    category = Column(String(64), index=True, nullable=False)
    log_name = Column(String(64), index=True, nullable=False)
    min_completed_end = Column(BigInteger, nullable=True)
    sth_end = Column(BigInteger, nullable=True)
    fetch_rate = Column(Float, nullable=True)
    status = Column(String(32), nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('idx_log_fetch_progress_history_log_name', 'log_name'),
        Index('idx_log_fetch_progress_history_snapshot', 'snapshot_timestamp'),
    )


# class UniqueCertCounter(Base):
#     __tablename__ = 'unique_cert_counter'
#     id = Column(Integer, primary_key=True)
#     issuer = Column(String(256), nullable=True)
#     serial_number = Column(String(256), nullable=False)
#     certificate_fingerprint_sha256 = Column(String(128), nullable=False)
#     __table_args__ = (
#         Index('idx_unique_cert_counter_unique', 'issuer', 'serial_number', 'certificate_fingerprint_sha256', unique=True),
#     )



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
