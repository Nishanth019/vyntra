-- Member history, push devices, in-app notifications and per-gym notification settings.

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
  KEY `idx_member_activity_member` (`member_id`, `created_at`),
  KEY `idx_member_activity_account` (`business_account_id`),
  CONSTRAINT `fk_member_activity_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_member_activity_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`),
  CONSTRAINT `fk_member_activity_membership` FOREIGN KEY (`membership_id`) REFERENCES `membership` (`id`),
  CONSTRAINT `fk_member_activity_payment` FOREIGN KEY (`payment_id`) REFERENCES `payment` (`id`),
  CONSTRAINT `fk_member_activity_created_by_business_admin` FOREIGN KEY (`created_by_business_admin_id`) REFERENCES `business_admin` (`id`)
);

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
  KEY `idx_business_admin_device_admin` (`business_admin_id`, `is_active`),
  CONSTRAINT `fk_business_admin_device_admin` FOREIGN KEY (`business_admin_id`) REFERENCES `business_admin` (`id`)
);

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
  KEY `idx_notification_admin` (`business_admin_id`, `business_account_id`, `is_read`),
  KEY `idx_notification_dedupe` (`business_account_id`, `notification_type`, `notification_date`),
  CONSTRAINT `fk_notification_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_notification_business_admin` FOREIGN KEY (`business_admin_id`) REFERENCES `business_admin` (`id`),
  CONSTRAINT `fk_notification_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`)
);

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
);
