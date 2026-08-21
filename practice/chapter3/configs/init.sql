-- PostgreSQL 초기화 스크립트
-- Chapter 3: 데이터 파이프라인 아키텍처 설계

-- 감사 로그용 확장
-- CREATE EXTENSION IF NOT EXISTS pgaudit;

-- 암호화용 확장
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 민원 데이터 테이블
CREATE TABLE IF NOT EXISTS complaints (
    id SERIAL PRIMARY KEY,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL,
    citizen_id VARCHAR(50),  -- 마스킹된 ID
    issue_type VARCHAR(50) NOT NULL,
    region_code VARCHAR(10),
    content_length INTEGER,
    priority VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 재난 경보 테이블
CREATE TABLE IF NOT EXISTS disaster_alerts (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(50) UNIQUE NOT NULL,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL,
    disaster_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    affected_area VARCHAR(200),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 교통 데이터 테이블
CREATE TABLE IF NOT EXISTS traffic_data (
    id SERIAL PRIMARY KEY,
    sensor_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    road_section VARCHAR(50),
    speed INTEGER,
    volume INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 환경 측정 테이블
CREATE TABLE IF NOT EXISTS environment_data (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(50) NOT NULL,
    measured_at TIMESTAMP WITH TIME ZONE NOT NULL,
    pm25 DECIMAL(6, 2),
    pm10 DECIMAL(6, 2),
    o3 DECIMAL(6, 4),
    temperature DECIMAL(5, 2),
    humidity DECIMAL(5, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 감사 로그 테이블
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    operation VARCHAR(10) NOT NULL,  -- INSERT, UPDATE, DELETE
    user_name VARCHAR(50),
    old_data JSONB,
    new_data JSONB,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_complaints_event_time ON complaints(event_time);
CREATE INDEX IF NOT EXISTS idx_complaints_region ON complaints(region_code);
CREATE INDEX IF NOT EXISTS idx_disaster_alerts_event_time ON disaster_alerts(event_time);
CREATE INDEX IF NOT EXISTS idx_traffic_data_timestamp ON traffic_data(timestamp);
CREATE INDEX IF NOT EXISTS idx_environment_data_measured_at ON environment_data(measured_at);

-- 읽기 전용 사용자 (보고서용)
-- CREATE USER reporter WITH PASSWORD 'report_password';
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO reporter;

COMMENT ON TABLE complaints IS '공공 민원 데이터';
COMMENT ON TABLE disaster_alerts IS '재난 경보 데이터';
COMMENT ON TABLE traffic_data IS '교통 센서 데이터';
COMMENT ON TABLE environment_data IS '환경 측정 데이터';
COMMENT ON TABLE audit_log IS '감사 로그';
