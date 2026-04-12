-- =============================================================
-- Parki BI Datamart – Star Schema DDL
-- =============================================================

CREATE DATABASE IF NOT EXISTS parki_datamart
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE parki_datamart;

-- -----------------------------------------------------------
-- Dimension: Time
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_time (
    time_id      INT AUTO_INCREMENT PRIMARY KEY,
    hour         TINYINT  NOT NULL,
    day          TINYINT  NOT NULL,
    day_of_week  TINYINT  NOT NULL COMMENT '1=Sun … 7=Sat (MySQL DAYOFWEEK)',
    week         TINYINT  NOT NULL,
    month        TINYINT  NOT NULL,
    quarter      TINYINT  NOT NULL,
    year         SMALLINT NOT NULL,
    is_weekend   BOOLEAN  NOT NULL DEFAULT FALSE,
    is_peak_hour BOOLEAN  NOT NULL DEFAULT FALSE,
    UNIQUE KEY uq_time (year, month, day, hour),
    INDEX idx_time_year_month (year, month),
    INDEX idx_time_dow (day_of_week)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------
-- Dimension: Vehicle Type
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_vehicle_type (
    vehicle_type_id INT AUTO_INCREMENT PRIMARY KEY,
    type_name       VARCHAR(50)  NOT NULL UNIQUE,
    category        VARCHAR(50)  NOT NULL,
    description     VARCHAR(255) NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------
-- Dimension: Camera
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_camera (
    camera_id         INT AUTO_INCREMENT PRIMARY KEY,
    camera_name       VARCHAR(100) NOT NULL,
    status            VARCHAR(20)  NOT NULL DEFAULT 'active',
    installation_date DATE         NULL,
    INDEX idx_camera_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------
-- Dimension: Location
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_location (
    location_id INT AUTO_INCREMENT PRIMARY KEY,
    latitude    DECIMAL(10, 7) NOT NULL,
    longitude   DECIMAL(10, 7) NOT NULL,
    zone_name   VARCHAR(100)   NOT NULL DEFAULT '',
    road_name   VARCHAR(150)   NOT NULL DEFAULT '',
    road_type   VARCHAR(50)    NOT NULL DEFAULT '',
    city        VARCHAR(100)   NOT NULL DEFAULT '',
    district    VARCHAR(100)   NOT NULL DEFAULT '',
    INDEX idx_location_zone (zone_name),
    INDEX idx_location_road (road_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------
-- Fact: Traffic Events
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_traffic_events (
    event_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    time_id          INT NOT NULL,
    vehicle_type_id  INT NOT NULL,
    camera_id        INT NOT NULL,
    location_id      INT NOT NULL,
    vehicle_count    INT NOT NULL DEFAULT 0,
    avg_speed        DECIMAL(6, 2) DEFAULT NULL,
    max_speed        DECIMAL(6, 2) DEFAULT NULL,
    min_speed        DECIMAL(6, 2) DEFAULT NULL,
    total_events     INT NOT NULL DEFAULT 0,
    congestion_level DECIMAL(4, 2) DEFAULT 0.00,

    CONSTRAINT fk_fact_time
        FOREIGN KEY (time_id) REFERENCES dim_time(time_id),
    CONSTRAINT fk_fact_vehicle_type
        FOREIGN KEY (vehicle_type_id) REFERENCES dim_vehicle_type(vehicle_type_id),
    CONSTRAINT fk_fact_camera
        FOREIGN KEY (camera_id) REFERENCES dim_camera(camera_id),
    CONSTRAINT fk_fact_location
        FOREIGN KEY (location_id) REFERENCES dim_location(location_id),

    INDEX idx_fact_time     (time_id),
    INDEX idx_fact_camera   (camera_id),
    INDEX idx_fact_vehicle  (vehicle_type_id),
    INDEX idx_fact_location (location_id),
    INDEX idx_fact_congestion (congestion_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================================
-- Initial Dimension Data
-- =============================================================

-- Vehicle types
INSERT IGNORE INTO dim_vehicle_type (type_name, category, description) VALUES
    ('car',          'light',         'Passenger car'),
    ('motorcycle',   'light',         'Motorcycle / scooter'),
    ('pickup_truck', 'light',         'Pickup truck'),
    ('suv',          'light',         'Sport utility vehicle'),
    ('van',          'light',         'Van / minivan'),
    ('bus',          'heavy',         'City or intercity bus'),
    ('truck',        'heavy',         'Heavy goods truck'),
    ('semi_trailer', 'heavy',         'Semi-trailer / articulated truck'),
    ('bicycle',      'non_motorized', 'Bicycle'),
    ('pedestrian',   'non_motorized', 'Pedestrian (detected)');

-- -----------------------------------------------------------
-- Time dimension: 2024-01-01 through 2026-12-31, every hour
-- Generated via a stored procedure for portability.
-- -----------------------------------------------------------
DELIMITER //

CREATE PROCEDURE IF NOT EXISTS populate_dim_time()
BEGIN
    DECLARE cur_date DATE DEFAULT '2024-01-01';
    DECLARE end_date DATE DEFAULT '2026-12-31';
    DECLARE cur_hour INT;
    DECLARE v_dow    INT;
    DECLARE v_week   INT;
    DECLARE v_qtr    INT;

    WHILE cur_date <= end_date DO
        SET cur_hour = 0;
        SET v_dow  = DAYOFWEEK(cur_date);           -- 1=Sun … 7=Sat
        SET v_week = WEEK(cur_date, 3);              -- ISO week
        SET v_qtr  = QUARTER(cur_date);

        WHILE cur_hour < 24 DO
            INSERT IGNORE INTO dim_time
                (hour, day, day_of_week, week, month, quarter, year, is_weekend, is_peak_hour)
            VALUES (
                cur_hour,
                DAY(cur_date),
                v_dow,
                v_week,
                MONTH(cur_date),
                v_qtr,
                YEAR(cur_date),
                v_dow IN (1, 7),                     -- Sunday or Saturday
                cur_hour BETWEEN 7 AND 9 OR cur_hour BETWEEN 17 AND 19
            );
            SET cur_hour = cur_hour + 1;
        END WHILE;

        SET cur_date = DATE_ADD(cur_date, INTERVAL 1 DAY);
    END WHILE;
END //

DELIMITER ;

CALL populate_dim_time();
DROP PROCEDURE IF EXISTS populate_dim_time;
