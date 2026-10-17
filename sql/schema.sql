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
