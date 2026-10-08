/*
 Navicat Premium Dump SQL

 Source Server         : 我的本地库
 Source Server Type    : SQLite
 Source Server Version : 3045000 (3.45.0)
 Source Schema         : main

 Target Server Type    : SQLite
 Target Server Version : 3045000 (3.45.0)
 File Encoding         : 65001

 Date: 07/10/2026 00:15:20
*/

PRAGMA foreign_keys = false;

-- ----------------------------
-- Table structure for devices
-- ----------------------------
DROP TABLE IF EXISTS "devices";
CREATE TABLE "devices" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "room_id" INTEGER,
  "device_type" TEXT,
  "power_watt" REAL,
  "status" TEXT DEFAULT 'off',
  FOREIGN KEY ("room_id") REFERENCES "rooms" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Records of devices
-- ----------------------------
INSERT INTO "devices" VALUES (1, 1, '空调', 1500.0, 'on');
INSERT INTO "devices" VALUES (2, 1, '照明', 200.0, 'on');
INSERT INTO "devices" VALUES (3, 1, '投影', 300.0, 'off');
INSERT INTO "devices" VALUES (4, 2, '空调', 1500.0, 'off');
INSERT INTO "devices" VALUES (5, 2, '照明', 200.0, 'off');
INSERT INTO "devices" VALUES (6, 3, '空调', 3000.0, 'on');
INSERT INTO "devices" VALUES (7, 3, '照明', 500.0, 'on');
INSERT INTO "devices" VALUES (8, 3, '投影', 500.0, 'on');
INSERT INTO "devices" VALUES (9, 4, '空调', 2000.0, 'on');
INSERT INTO "devices" VALUES (10, 4, '照明', 300.0, 'on');
INSERT INTO "devices" VALUES (11, 4, '实验设备', 2500.0, 'on');
INSERT INTO "devices" VALUES (12, 5, '空调', 2000.0, 'off');
INSERT INTO "devices" VALUES (13, 5, '照明', 300.0, 'off');
INSERT INTO "devices" VALUES (14, 5, '实验设备', 2500.0, 'off');
INSERT INTO "devices" VALUES (15, 6, '空调', 4000.0, 'on');
INSERT INTO "devices" VALUES (16, 6, '照明', 800.0, 'on');
INSERT INTO "devices" VALUES (17, 7, '空调', 1200.0, 'on');
INSERT INTO "devices" VALUES (18, 7, '照明', 150.0, 'off');
INSERT INTO "devices" VALUES (19, 8, '空调', 1200.0, 'off');
INSERT INTO "devices" VALUES (20, 8, '照明', 150.0, 'off');

-- ----------------------------
-- Table structure for energy_logs
-- ----------------------------
DROP TABLE IF EXISTS "energy_logs";
CREATE TABLE "energy_logs" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "device_id" INTEGER,
  "record_time" DATETIME,
  "energy_kwh" REAL,
  "occupancy" INTEGER,
  "is_class_hours" INTEGER,
  FOREIGN KEY ("device_id") REFERENCES "devices" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Records of energy_logs
-- ----------------------------
INSERT INTO "energy_logs" VALUES (1, 1, '2026-10-06 08:00:00', 1.5, 55, 1);
INSERT INTO "energy_logs" VALUES (2, 2, '2026-10-06 08:00:00', 0.2, 55, 1);
INSERT INTO "energy_logs" VALUES (3, 6, '2026-10-06 08:00:00', 3.0, 110, 1);
INSERT INTO "energy_logs" VALUES (4, 7, '2026-10-06 08:00:00', 0.5, 110, 1);
INSERT INTO "energy_logs" VALUES (5, 9, '2026-10-06 08:00:00', 2.0, 40, 1);
INSERT INTO "energy_logs" VALUES (6, 10, '2026-10-06 08:00:00', 0.3, 40, 1);
INSERT INTO "energy_logs" VALUES (7, 11, '2026-10-06 08:00:00', 2.5, 40, 1);
INSERT INTO "energy_logs" VALUES (8, 1, '2026-10-06 12:00:00', 1.5, 0, 0);
INSERT INTO "energy_logs" VALUES (9, 2, '2026-10-06 12:00:00', 0.2, 0, 0);
INSERT INTO "energy_logs" VALUES (10, 6, '2026-10-06 12:00:00', 3.0, 5, 0);
INSERT INTO "energy_logs" VALUES (11, 7, '2026-10-06 12:00:00', 0.5, 5, 0);
INSERT INTO "energy_logs" VALUES (12, 14, '2026-10-06 12:00:00', 4.0, 0, 0);
INSERT INTO "energy_logs" VALUES (13, 15, '2026-10-06 12:00:00', 0.8, 0, 0);
INSERT INTO "energy_logs" VALUES (14, 16, '2026-10-06 12:00:00', 1.2, 2, 0);
INSERT INTO "energy_logs" VALUES (15, 1, '2026-10-06 14:00:00', 1.5, 58, 1);
INSERT INTO "energy_logs" VALUES (16, 2, '2026-10-06 14:00:00', 0.2, 58, 1);
INSERT INTO "energy_logs" VALUES (17, 9, '2026-10-06 14:00:00', 2.0, 42, 1);
INSERT INTO "energy_logs" VALUES (18, 10, '2026-10-06 14:00:00', 0.3, 42, 1);
INSERT INTO "energy_logs" VALUES (19, 11, '2026-10-06 14:00:00', 2.5, 42, 1);
INSERT INTO "energy_logs" VALUES (20, 14, '2026-10-06 14:00:00', 4.0, 80, 1);
INSERT INTO "energy_logs" VALUES (21, 15, '2026-10-06 14:00:00', 0.8, 80, 1);
INSERT INTO "energy_logs" VALUES (22, 6, '2026-10-06 20:00:00', 3.0, 30, 0);
INSERT INTO "energy_logs" VALUES (23, 7, '2026-10-06 20:00:00', 0.5, 30, 0);
INSERT INTO "energy_logs" VALUES (24, 16, '2026-10-06 20:00:00', 1.2, 15, 0);
INSERT INTO "energy_logs" VALUES (25, 17, '2026-10-06 20:00:00', 0.15, 15, 0);
INSERT INTO "energy_logs" VALUES (26, 1, '2026-10-06 23:00:00', 1.5, 0, 0);
INSERT INTO "energy_logs" VALUES (27, 6, '2026-10-06 23:00:00', 3.0, 0, 0);
INSERT INTO "energy_logs" VALUES (28, 7, '2026-10-06 23:00:00', 0.5, 0, 0);
INSERT INTO "energy_logs" VALUES (29, 14, '2026-10-06 23:00:00', 4.0, 0, 0);
INSERT INTO "energy_logs" VALUES (30, 15, '2026-10-06 23:00:00', 0.8, 0, 0);

-- ----------------------------
-- Table structure for rooms
-- ----------------------------
DROP TABLE IF EXISTS "rooms";
CREATE TABLE "rooms" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "name" TEXT NOT NULL,
  "building" TEXT,
  "capacity" INTEGER,
  "room_type" TEXT
);

-- ----------------------------
-- Records of rooms
-- ----------------------------
INSERT INTO "rooms" VALUES (1, 'A-101', '教学楼A', 60, '教室');
INSERT INTO "rooms" VALUES (2, 'A-102', '教学楼A', 60, '教室');
INSERT INTO "rooms" VALUES (3, 'A-201', '教学楼A', 120, '阶梯教室');
INSERT INTO "rooms" VALUES (4, 'B-101', '教学楼B', 45, '实验室');
INSERT INTO "rooms" VALUES (5, 'B-102', '教学楼B', 45, '实验室');
INSERT INTO "rooms" VALUES (6, 'C-301', '图书馆C', 200, '自习室');
INSERT INTO "rooms" VALUES (7, 'D-101', '行政楼D', 20, '办公室');
INSERT INTO "rooms" VALUES (8, 'D-102', '行政楼D', 20, '办公室');

/*
-- ----------------------------
-- Table structure for sqlite_sequence
-- ----------------------------
DROP TABLE IF EXISTS "sqlite_sequence";
CREATE TABLE "sqlite_sequence" (
  "name",
  "seq"
);

-- ----------------------------
-- Records of sqlite_sequence
-- ----------------------------
INSERT INTO "sqlite_sequence" VALUES ('rooms', 8);
INSERT INTO "sqlite_sequence" VALUES ('devices', 20);
INSERT INTO "sqlite_sequence" VALUES ('energy_logs', 30);
*/

-- ----------------------------
-- Auto increment value for devices
-- ----------------------------
UPDATE "sqlite_sequence" SET seq = 20 WHERE name = 'devices';

-- ----------------------------
-- Auto increment value for energy_logs
-- ----------------------------
UPDATE "sqlite_sequence" SET seq = 30 WHERE name = 'energy_logs';

-- ----------------------------
-- Auto increment value for rooms
-- ----------------------------
UPDATE "sqlite_sequence" SET seq = 8 WHERE name = 'rooms';

PRAGMA foreign_keys = true;
