-- WhatsApp reminders to members (Meta WhatsApp Cloud API). Per-business switches, and a log of every message
-- (also used so a member gets each reminder once a day, and to cap messages per business per month).

CREATE TABLE `whatsapp_setting` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '0',
  `expiry_reminders` tinyint(1) NOT NULL DEFAULT '1',
  `expired_followups` tinyint(1) NOT NULL DEFAULT '1',
  `dues_reminders` tinyint(1) NOT NULL DEFAULT '1',
  `payment_receipts` tinyint(1) NOT NULL DEFAULT '1',
  `birthday_wishes` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_whatsapp_setting_account` (`business_account_id`),
  CONSTRAINT `fk_whatsapp_setting_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `whatsapp_message` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `business_account_id` bigint unsigned NOT NULL,
  `member_id` bigint unsigned DEFAULT NULL,
  `message_type` varchar(30) NOT NULL,                 -- EXPIRY / EXPIRED / DUES / PAYMENT / BIRTHDAY
  `phone` varchar(20) NOT NULL,
  `template` varchar(100) NOT NULL,
  `status` varchar(20) NOT NULL,                       -- SENT / FAILED
  `provider_message_id` varchar(255) DEFAULT NULL,     -- wamid.xxx from Meta
  `error` varchar(1000) DEFAULT NULL,
  `sent_date` date NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_whatsapp_message_dedupe` (`member_id`,`message_type`,`sent_date`),
  KEY `idx_whatsapp_message_account_date` (`business_account_id`,`sent_date`),
  CONSTRAINT `fk_whatsapp_message_business_account` FOREIGN KEY (`business_account_id`) REFERENCES `business_account` (`id`),
  CONSTRAINT `fk_whatsapp_message_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
