-- =============================================================
-- Parki Capture Reconnaissance — MySQL Schema
-- =============================================================
-- Database: parki_capture
-- Creates tables for cameras, traffic events, and camera health.
-- =============================================================

CREATE DATABASE IF NOT EXISTS parki_capture
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE parki_capture;

-- -----------------------------------------------------------
-- cameras — registered camera devices
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS cameras (
    id                   VARCHAR(64)   NOT NULL PRIMARY KEY,
    name                 VARCHAR(128)  NOT NULL,
    rtsp_url             VARCHAR(512)  NOT NULL,
    latitude             DECIMAL(10,7) DEFAULT NULL,
    longitude            DECIMAL(10,7) DEFAULT NULL,
    location_description VARCHAR(256)  DEFAULT NULL,
    status               ENUM('active','inactive','maintenance') NOT NULL DEFAULT 'active',
    created_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_cameras_status (status)
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- traffic_events — individual vehicle detections
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS traffic_events (
    id              BIGINT        AUTO_INCREMENT PRIMARY KEY,
    camera_id       VARCHAR(64)   NOT NULL,
    event_timestamp DATETIME(3)   NOT NULL,
    vehicle_type    VARCHAR(32)   NOT NULL,
    confidence      FLOAT         NOT NULL,
    speed_estimate  FLOAT         DEFAULT 0,
    direction       VARCHAR(16)   DEFAULT 'unknown',
    bbox_x          FLOAT         DEFAULT 0,
    bbox_y          FLOAT         DEFAULT 0,
    bbox_w          FLOAT         DEFAULT 0,
    bbox_h          FLOAT         DEFAULT 0,
    frame_number    INT           DEFAULT 0,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_te_camera_id      (camera_id),
    INDEX idx_te_timestamp      (event_timestamp),
    INDEX idx_te_vehicle_type   (vehicle_type),
    INDEX idx_te_cam_ts         (camera_id, event_timestamp),

    CONSTRAINT fk_te_camera
        FOREIGN KEY (camera_id) REFERENCES cameras(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- camera_health — periodic health-check results
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS camera_health (
    id          BIGINT      AUTO_INCREMENT PRIMARY KEY,
    camera_id   VARCHAR(64) NOT NULL,
    check_time  DATETIME    NOT NULL,
    status      VARCHAR(32) NOT NULL,
    fps         FLOAT       DEFAULT NULL,
    latency_ms  FLOAT       DEFAULT NULL,

    INDEX idx_ch_camera_id  (camera_id),
    INDEX idx_ch_check_time (check_time),

    CONSTRAINT fk_ch_camera
        FOREIGN KEY (camera_id) REFERENCES cameras(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- fact_traffic_hourly — BI data-mart aggregation table
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_traffic_hourly (
    id             BIGINT       AUTO_INCREMENT PRIMARY KEY,
    hour           DATETIME     NOT NULL,
    camera_id      VARCHAR(64)  NOT NULL,
    vehicle_type   VARCHAR(32)  NOT NULL,
    vehicle_count  INT          NOT NULL DEFAULT 0,
    avg_speed      FLOAT        DEFAULT 0,
    total_events   INT          NOT NULL DEFAULT 0,
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_hourly (hour, camera_id, vehicle_type),
    INDEX idx_fth_hour       (hour),
    INDEX idx_fth_camera_id  (camera_id)
) ENGINE=InnoDB;
