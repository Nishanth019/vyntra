-- Schema of the app's tables (unmanaged by Django). Used to build the test database.

CREATE TABLE `business_type` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `code` varchar(50) NOT NULL,
  `description` varchar(300) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_business_type_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `business_account` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_type_id` bigint unsigned NOT NULL,
  `name` varchar(200) NOT NULL,
  `logo_url` varchar(500) DEFAULT NULL,
  `address` varchar(500) DEFAULT NULL,
  `city` varchar(100) DEFAULT NULL,
  `state` varchar(100) DEFAULT NULL,
  `country` varchar(100) DEFAULT NULL,
  `address_lat` decimal(10,8) DEFAULT NULL,
  `address_lng` decimal(11,8) DEFAULT NULL,
  `contact_no` varchar(20) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `website` varchar(500) DEFAULT NULL,
  `terms_and_conditions` varchar(10000) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_business_account_business_type` (`business_type_id`),
  KEY `idx_business_account_is_active` (`is_active`),
  CONSTRAINT `fk_business_account_business_type` FOREIGN KEY (`business_type_id`) REFERENCES `business_type` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `business_admin` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(200) NOT NULL,
  `email` varchar(255) NOT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `password` varchar(255) NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `last_login_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_business_admin_email` (`email`),
  KEY `idx_business_admin_phone` (`phone`),
  KEY `idx_business_admin_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `business_account_admin` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `business_admin_id` bigint unsigned NOT NULL,
  `role` varchar(30) NOT NULL DEFAULT 'ADMIN',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_business_account_admin` (`business_account_id`,`business_admin_id`),
  KEY `idx_business_account_admin_admin` (`business_admin_id`),
  KEY `idx_business_account_admin_account` (`business_account_id`),
  CONSTRAINT `fk_business_account_admin_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_business_account_admin_admin` FOREIGN KEY (`business_admin_id`) REFERENCES `business_admin` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `member` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `member_code` varchar(100) NOT NULL,
  `created_by_business_admin_id` bigint unsigned NOT NULL,
  `first_name` varchar(100) NOT NULL,
  `last_name` varchar(100) DEFAULT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `date_of_birth` date DEFAULT NULL,
  `gender` varchar(20) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_member_account_code` (`business_account_id`,`member_code`),
  KEY `fk_member_created_by_business_admin` (`created_by_business_admin_id`),
  KEY `idx_member_business_account` (`business_account_id`),
  KEY `idx_member_phone` (`phone`),
  KEY `idx_member_is_active` (`business_account_id`,`is_active`),
  CONSTRAINT `fk_member_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_member_created_by_business_admin` FOREIGN KEY (`created_by_business_admin_id`) REFERENCES `business_admin` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `gym_member` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `member_id` bigint unsigned NOT NULL,
  `emergency_contact_name` varchar(200) DEFAULT NULL,
  `emergency_contact_phone` varchar(20) DEFAULT NULL,
  `height_cm` decimal(5,2) DEFAULT NULL,
  `weight_kg` decimal(5,2) DEFAULT NULL,
  `fitness_goal` varchar(100) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `emergency_contact_address` varchar(500) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_gym_member_member` (`member_id`),
  CONSTRAINT `fk_gym_member_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `staff` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `employee_code` varchar(100) NOT NULL,
  `created_by_business_admin_id` bigint unsigned NOT NULL,
  `first_name` varchar(100) NOT NULL,
  `last_name` varchar(100) DEFAULT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `role` varchar(100) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `salary` decimal(12,2) DEFAULT NULL,
  `joining_date` date DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_staff_account_code` (`business_account_id`,`employee_code`),
  KEY `fk_staff_created_by_business_admin` (`created_by_business_admin_id`),
  KEY `idx_staff_business_account` (`business_account_id`),
  KEY `idx_staff_is_active` (`business_account_id`,`is_active`),
  CONSTRAINT `fk_staff_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_staff_created_by_business_admin` FOREIGN KEY (`created_by_business_admin_id`) REFERENCES `business_admin` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `duration_type` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(50) NOT NULL,
  `code` varchar(20) NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_duration_type_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `membership_plan` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `name` varchar(200) NOT NULL,
  `duration_type_id` bigint unsigned NOT NULL,
  `duration_value` int NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `description` varchar(1000) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_membership_plan_duration_type` (`duration_type_id`),
  KEY `idx_membership_plan_account` (`business_account_id`),
  KEY `idx_membership_plan_is_active` (`business_account_id`,`is_active`),
  CONSTRAINT `fk_membership_plan_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_membership_plan_duration_type` FOREIGN KEY (`duration_type_id`) REFERENCES `duration_type` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `membership` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `member_id` bigint unsigned NOT NULL,
  `membership_plan_id` bigint unsigned NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `discount` decimal(12,2) NOT NULL DEFAULT '0.00',
  PRIMARY KEY (`id`),
  KEY `idx_membership_account` (`business_account_id`),
  KEY `idx_membership_member` (`member_id`),
  KEY `idx_membership_plan` (`membership_plan_id`),
  KEY `idx_membership_end_date` (`end_date`),
  KEY `idx_membership_member_active` (`member_id`,`is_active`),
  CONSTRAINT `fk_membership_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_membership_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`),
  CONSTRAINT `fk_membership_plan` FOREIGN KEY (`membership_plan_id`) REFERENCES `membership_plan` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `payment` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `member_id` bigint unsigned NOT NULL,
  `membership_id` bigint unsigned DEFAULT NULL,
  `pg_bill_id` bigint unsigned DEFAULT NULL,
  `amount` decimal(12,2) NOT NULL,
  `payment_date` timestamp NOT NULL,
  `payment_method` varchar(30) NOT NULL,
  `transaction_reference` varchar(255) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `notes` varchar(1000) DEFAULT NULL,
  `created_by_business_admin_id` bigint unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_payment_created_by_business_admin` (`created_by_business_admin_id`),
  KEY `idx_payment_account` (`business_account_id`),
  KEY `idx_payment_member` (`member_id`),
  KEY `idx_payment_membership` (`membership_id`),
  KEY `idx_payment_pg_bill` (`pg_bill_id`),
  KEY `idx_payment_date` (`payment_date`),
  KEY `idx_payment_account_date` (`business_account_id`,`payment_date`),
  CONSTRAINT `fk_payment_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_payment_created_by_business_admin` FOREIGN KEY (`created_by_business_admin_id`) REFERENCES `business_admin` (`id`),
  CONSTRAINT `fk_payment_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`),
  CONSTRAINT `fk_payment_membership` FOREIGN KEY (`membership_id`) REFERENCES `membership` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `member_attendance` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `member_id` bigint unsigned NOT NULL,
  `attendance_date` date NOT NULL,
  `check_in_time` datetime DEFAULT NULL,
  `check_out_time` datetime DEFAULT NULL,
  `marked_by_admin_id` bigint unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_member_attendance_day` (`member_id`,`attendance_date`),
  KEY `fk_member_attendance_admin` (`marked_by_admin_id`),
  KEY `idx_member_attendance_account_date` (`business_account_id`,`attendance_date`),
  KEY `idx_member_attendance_member` (`member_id`),
  CONSTRAINT `fk_member_attendance_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_member_attendance_admin` FOREIGN KEY (`marked_by_admin_id`) REFERENCES `business_admin` (`id`),
  CONSTRAINT `fk_member_attendance_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `member_activity` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `member_id` bigint unsigned NOT NULL,
  `membership_id` bigint unsigned DEFAULT NULL,
  `payment_id` bigint unsigned DEFAULT NULL,
  `activity_type` varchar(30) NOT NULL,
  `description` varchar(1000) NOT NULL,
  `created_by_business_admin_id` bigint unsigned DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_member_activity_member` (`member_id`,`created_at`),
  KEY `idx_member_activity_account` (`business_account_id`),
  KEY `fk_member_activity_membership` (`membership_id`),
  KEY `fk_member_activity_payment` (`payment_id`),
  KEY `fk_member_activity_created_by_business_admin` (`created_by_business_admin_id`),
  CONSTRAINT `fk_member_activity_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_member_activity_created_by_business_admin` FOREIGN KEY (`created_by_business_admin_id`) REFERENCES `business_admin` (`id`),
  CONSTRAINT `fk_member_activity_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`),
  CONSTRAINT `fk_member_activity_membership` FOREIGN KEY (`membership_id`) REFERENCES `membership` (`id`),
  CONSTRAINT `fk_member_activity_payment` FOREIGN KEY (`payment_id`) REFERENCES `payment` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `business_admin_device` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_admin_id` bigint unsigned NOT NULL,
  `push_token` varchar(255) NOT NULL,
  `platform` varchar(20) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_business_admin_device_token` (`push_token`),
  KEY `idx_business_admin_device_admin` (`business_admin_id`,`is_active`),
  CONSTRAINT `fk_business_admin_device_admin` FOREIGN KEY (`business_admin_id`) REFERENCES `business_admin` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `notification` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `business_admin_id` bigint unsigned NOT NULL,
  `notification_type` varchar(30) NOT NULL,
  `title` varchar(200) NOT NULL,
  `message` varchar(1000) NOT NULL,
  `member_filter` varchar(30) DEFAULT NULL,
  `member_id` bigint unsigned DEFAULT NULL,
  `notification_date` date NOT NULL,
  `is_read` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_notification_admin` (`business_admin_id`,`business_account_id`,`is_read`),
  KEY `idx_notification_dedupe` (`business_account_id`,`notification_type`,`notification_date`),
  KEY `fk_notification_member` (`member_id`),
  CONSTRAINT `fk_notification_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_notification_business_admin` FOREIGN KEY (`business_admin_id`) REFERENCES `business_admin` (`id`),
  CONSTRAINT `fk_notification_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `notification_setting` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `morning_summary` tinyint(1) NOT NULL DEFAULT '1',
  `expiry_reminders` tinyint(1) NOT NULL DEFAULT '1',
  `expired_followups` tinyint(1) NOT NULL DEFAULT '1',
  `dues_reminders` tinyint(1) NOT NULL DEFAULT '1',
  `no_show_alerts` tinyint(1) NOT NULL DEFAULT '1',
  `birthday_alerts` tinyint(1) NOT NULL DEFAULT '1',
  `activity_alerts` tinyint(1) NOT NULL DEFAULT '1',
  `evening_summary` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_notification_setting_account` (`business_account_id`),
  CONSTRAINT `fk_notification_setting_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE `subscription_plan` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(30) NOT NULL,                          -- MONTHLY / QUARTERLY / YEARLY
  `name` varchar(100) NOT NULL,
  `months` int unsigned NOT NULL,
  `price` decimal(10,2) NOT NULL,                       -- in rupees, GST included
  `currency` char(3) NOT NULL DEFAULT 'INR',
  `razorpay_plan_id` varchar(100) DEFAULT NULL,         -- plan_xxx from Razorpay dashboard
  `google_base_plan_id` varchar(100) DEFAULT NULL,      -- base plan id in Play Console (e.g. monthly)
  `sort_order` int NOT NULL DEFAULT '0',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_subscription_plan_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- One row per login: its trial and its current paid plan.
CREATE TABLE `subscription` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_admin_id` bigint unsigned NOT NULL,
  `subscription_plan_id` bigint unsigned DEFAULT NULL,  -- NULL while only on trial
  `status` varchar(20) NOT NULL DEFAULT 'TRIAL',        -- TRIAL / ACTIVE / GRACE / CANCELLED / EXPIRED
  `trial_ends_at` datetime NOT NULL,
  `current_period_start` datetime DEFAULT NULL,
  `current_period_end` datetime DEFAULT NULL,           -- access ends here (+3 days grace if a renewal fails)
  `auto_renew` tinyint(1) NOT NULL DEFAULT '0',
  `provider` varchar(20) DEFAULT NULL,                  -- RAZORPAY / GOOGLE_PLAY / APPLE / MANUAL
  `provider_subscription_id` varchar(255) DEFAULT NULL, -- Razorpay sub_xxx, or Google Play purchase token
  `cancelled_at` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_subscription_admin` (`business_admin_id`),
  KEY `idx_subscription_plan` (`subscription_plan_id`),
  KEY `idx_subscription_status_end` (`status`,`current_period_end`),
  KEY `idx_subscription_provider_ref` (`provider`,`provider_subscription_id`(191)),
  CONSTRAINT `fk_subscription_admin` FOREIGN KEY (`business_admin_id`) REFERENCES `business_admin` (`id`),
  CONSTRAINT `fk_subscription_plan` FOREIGN KEY (`subscription_plan_id`) REFERENCES `subscription_plan` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Every charge (first payment and each renewal), from any provider.
CREATE TABLE `subscription_payment` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `subscription_id` bigint unsigned NOT NULL,
  `subscription_plan_id` bigint unsigned DEFAULT NULL,
  `provider` varchar(20) NOT NULL,                      -- RAZORPAY / GOOGLE_PLAY / APPLE / MANUAL
  `provider_payment_id` varchar(255) NOT NULL,          -- Razorpay pay_xxx, or Google order id (GPA.xxxx..0)
  `amount` decimal(10,2) NOT NULL,
  `currency` char(3) NOT NULL DEFAULT 'INR',
  `status` varchar(20) NOT NULL DEFAULT 'PAID',         -- PAID / REFUNDED / FAILED
  `period_start` datetime DEFAULT NULL,
  `period_end` datetime DEFAULT NULL,
  `paid_at` datetime NOT NULL,
  `raw_response` json DEFAULT NULL,                     -- provider payload, kept for support
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_subscription_payment_provider_ref` (`provider`,`provider_payment_id`(191)),
  KEY `idx_subscription_payment_subscription` (`subscription_id`),
  KEY `idx_subscription_payment_plan` (`subscription_plan_id`),
  CONSTRAINT `fk_subscription_payment_subscription` FOREIGN KEY (`subscription_id`) REFERENCES `subscription` (`id`),
  CONSTRAINT `fk_subscription_payment_plan` FOREIGN KEY (`subscription_plan_id`) REFERENCES `subscription_plan` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- PG business type, expenses and staff salaries (sql/2026-10-25_pg.sql).
CREATE TABLE `pg_property` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `property_type` varchar(20) NOT NULL DEFAULT 'PG',         -- PG / HOSTEL / COLIVING
  `gender` varchar(10) NOT NULL DEFAULT 'COED',              -- MALE / FEMALE / COED
  `facilities` json DEFAULT NULL,                            -- ["WIFI","FOOD","PARKING",...]
  `default_due_day` tinyint unsigned NOT NULL DEFAULT '1',   -- 1..28, suggested for new tenants
  `prorate_first_bill` tinyint(1) NOT NULL DEFAULT '1',      -- default for new tenants joining mid-month
  `notice_period_days` int unsigned NOT NULL DEFAULT '30',
  `eb_unit_price` decimal(8,2) DEFAULT NULL,                 -- ₹ per electricity unit (Phase 2)
  `upi_id` varchar(100) DEFAULT NULL,                        -- put in WhatsApp rent reminders
  `house_rules` varchar(5000) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pg_property_account` (`business_account_id`),
  CONSTRAINT `fk_pg_property_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `pg_room` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `room_number` varchar(30) NOT NULL,
  `floor` varchar(30) DEFAULT NULL,                          -- "Ground", "1", "2"
  `is_ac` tinyint(1) NOT NULL DEFAULT '0',
  `rent_per_bed` decimal(12,2) NOT NULL,                     -- monthly, pre-fills the tenant's rent
  `amenities` json DEFAULT NULL,                             -- ["ATTACHED_BATH","BALCONY","GEYSER",...]
  `notes` varchar(500) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pg_room_number` (`business_account_id`,`room_number`),
  CONSTRAINT `fk_pg_room_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `pg_bed` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `pg_room_id` bigint unsigned NOT NULL,
  `label` varchar(20) NOT NULL,                              -- "1", "2", "A"
  `is_active` tinyint(1) NOT NULL DEFAULT '1',               -- 0 when the room's bed count is reduced
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pg_bed_label` (`pg_room_id`,`label`),
  KEY `idx_pg_bed_account` (`business_account_id`),
  CONSTRAINT `fk_pg_bed_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_pg_bed_room` FOREIGN KEY (`pg_room_id`) REFERENCES `pg_room` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `pg_tenant` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `member_id` bigint unsigned NOT NULL,
  `occupation` varchar(200) DEFAULT NULL,                    -- job or college
  `permanent_address` varchar(500) DEFAULT NULL,
  `id_type` varchar(20) DEFAULT NULL,                        -- AADHAAR / PAN / PASSPORT / DL / VOTER
  `id_last4` varchar(4) DEFAULT NULL,                        -- only the last 4 digits, never the full number
  `emergency_contact_name` varchar(200) DEFAULT NULL,
  `emergency_contact_phone` varchar(20) DEFAULT NULL,
  `emergency_contact_relation` varchar(50) DEFAULT NULL,
  `vehicle_number` varchar(20) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pg_tenant_member` (`member_id`),
  CONSTRAINT `fk_pg_tenant_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `pg_tenancy` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `member_id` bigint unsigned NOT NULL,
  `pg_bed_id` bigint unsigned NOT NULL,
  `rent` decimal(12,2) NOT NULL,                             -- monthly (a bill is rent x billing_cycle_months)
  `billing_cycle_months` tinyint unsigned NOT NULL DEFAULT '1', -- 1 / 3 / 6 / 12
  `due_day` tinyint unsigned NOT NULL,                       -- 1..28
  `start_date` date NOT NULL,
  `status` varchar(10) NOT NULL DEFAULT 'ACTIVE',            -- ACTIVE / NOTICE / ENDED
  `notice_date` date DEFAULT NULL,                           -- when they told you they're leaving
  `expected_end_date` date DEFAULT NULL,                     -- planned leaving date
  `end_date` date DEFAULT NULL,                              -- actual checkout
  `leave_reason` varchar(500) DEFAULT NULL,
  `deposit_amount` decimal(12,2) NOT NULL DEFAULT '0.00',    -- agreed deposit (collections in pg_deposit_entry)
  `advance_balance` decimal(12,2) NOT NULL DEFAULT '0.00',   -- overpayment, used up by the next bill
  `created_by_business_admin_id` bigint unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_pg_tenancy_account_status` (`business_account_id`,`status`),
  KEY `idx_pg_tenancy_member` (`member_id`),
  KEY `idx_pg_tenancy_bed_status` (`pg_bed_id`,`status`),
  CONSTRAINT `fk_pg_tenancy_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_pg_tenancy_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`),
  CONSTRAINT `fk_pg_tenancy_bed` FOREIGN KEY (`pg_bed_id`) REFERENCES `pg_bed` (`id`),
  CONSTRAINT `fk_pg_tenancy_created_by` FOREIGN KEY (`created_by_business_admin_id`) REFERENCES `business_admin` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `pg_bill` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `pg_tenancy_id` bigint unsigned NOT NULL,
  `member_id` bigint unsigned NOT NULL,                      -- copy of the tenancy's member, for fast lists
  `period_start` date NOT NULL,
  `period_end` date NOT NULL,
  `due_date` date NOT NULL,
  `total` decimal(12,2) NOT NULL,                            -- sum of pg_bill_item amounts
  `discount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `paid` decimal(12,2) NOT NULL DEFAULT '0.00',              -- kept in step with linked payments
  `status` varchar(10) NOT NULL DEFAULT 'UNPAID',            -- UNPAID / PARTIAL / PAID / VOID
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pg_bill_period` (`pg_tenancy_id`,`period_start`),
  KEY `idx_pg_bill_account_status` (`business_account_id`,`status`),
  KEY `idx_pg_bill_account_due` (`business_account_id`,`due_date`),
  KEY `idx_pg_bill_member` (`member_id`),
  CONSTRAINT `fk_pg_bill_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_pg_bill_tenancy` FOREIGN KEY (`pg_tenancy_id`) REFERENCES `pg_tenancy` (`id`),
  CONSTRAINT `fk_pg_bill_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `pg_bill_item` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `pg_bill_id` bigint unsigned NOT NULL,
  `item_type` varchar(20) NOT NULL,                          -- RENT / CHARGE / ELECTRICITY / ADJUSTMENT
  `description` varchar(255) NOT NULL,                       -- "Rent 10–31 Oct (22 days)", "Key deposit"
  `amount` decimal(12,2) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_pg_bill_item_bill` (`pg_bill_id`),
  CONSTRAINT `fk_pg_bill_item_bill` FOREIGN KEY (`pg_bill_id`) REFERENCES `pg_bill` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `pg_deposit_entry` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `pg_tenancy_id` bigint unsigned NOT NULL,
  `entry_type` varchar(10) NOT NULL,                         -- COLLECT / REFUND / DEDUCT
  `amount` decimal(12,2) NOT NULL,
  `entry_date` date NOT NULL,
  `payment_method` varchar(30) DEFAULT NULL,
  `reason` varchar(500) DEFAULT NULL,                        -- for deductions, e.g. "Broken cupboard"
  `created_by_business_admin_id` bigint unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_pg_deposit_account_date` (`business_account_id`,`entry_date`),
  KEY `idx_pg_deposit_tenancy` (`pg_tenancy_id`),
  CONSTRAINT `fk_pg_deposit_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_pg_deposit_tenancy` FOREIGN KEY (`pg_tenancy_id`) REFERENCES `pg_tenancy` (`id`),
  CONSTRAINT `fk_pg_deposit_created_by` FOREIGN KEY (`created_by_business_admin_id`) REFERENCES `business_admin` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `expense` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `category` varchar(30) NOT NULL,                           -- RENT / ELECTRICITY / WATER / INTERNET / SALARY / MAINTENANCE / REPAIRS / EQUIPMENT / GROCERIES / CLEANING / SUPPLIES / MARKETING / TAXES / OTHER
  `amount` decimal(12,2) NOT NULL,
  `expense_date` date NOT NULL,
  `description` varchar(255) NOT NULL,
  `vendor` varchar(200) DEFAULT NULL,
  `payment_method` varchar(30) DEFAULT NULL,
  `notes` varchar(1000) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_by_business_admin_id` bigint unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_expense_account_date` (`business_account_id`,`expense_date`),
  CONSTRAINT `fk_expense_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_expense_created_by` FOREIGN KEY (`created_by_business_admin_id`) REFERENCES `business_admin` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `staff_salary` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `staff_id` bigint unsigned NOT NULL,
  `salary_month` date NOT NULL,                              -- first day of the month
  `amount` decimal(12,2) NOT NULL,
  `paid_on` date DEFAULT NULL,                               -- NULL = not paid yet
  `payment_method` varchar(30) DEFAULT NULL,
  `expense_id` bigint unsigned DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_staff_salary_month` (`staff_id`,`salary_month`),
  KEY `idx_staff_salary_account_month` (`business_account_id`,`salary_month`),
  CONSTRAINT `fk_staff_salary_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_staff_salary_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`),
  CONSTRAINT `fk_staff_salary_expense` FOREIGN KEY (`expense_id`) REFERENCES `expense` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
