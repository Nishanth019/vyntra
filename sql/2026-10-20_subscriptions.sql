-- Subscriptions: a 15-day free trial per login, then monthly / quarterly / yearly plans
-- paid through Razorpay (website) or Google Play Billing (Android app).
-- The subscription belongs to the login that owns a business account (role OWNER);
-- every admin of that account gets access through the owner's subscription.

-- Plans you sell. Prices are editable later in Django admin.
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


-- ---------------------------------------------------------------------------
-- Data setup (run once, after the tables above)
-- ---------------------------------------------------------------------------

-- 1) Plans. SET THE MONTHLY PRICE before running: quarterly = 10% off, yearly = 20% off.
SET @monthly = 499.00;
INSERT INTO `subscription_plan` (`code`, `name`, `months`, `price`, `google_base_plan_id`, `sort_order`) VALUES
  ('MONTHLY',   'Monthly',   1,  @monthly,                         'monthly',   1),
  ('QUARTERLY', 'Quarterly', 3,  ROUND(@monthly * 3 * 0.90, 0),    'quarterly', 2),
  ('YEARLY',    'Yearly',    12, ROUND(@monthly * 12 * 0.80, 0),   'yearly',    3);

-- 2) Mark the creator (earliest admin) of every business account as its OWNER.
UPDATE `business_account_admin` baa
JOIN (
  SELECT `business_account_id`, MIN(`id`) AS `first_id`
  FROM `business_account_admin`
  GROUP BY `business_account_id`
) firsts ON firsts.`first_id` = baa.`id`
SET baa.`role` = 'OWNER';

-- 3) Existing logins get a 15-day trial starting today.
INSERT INTO `subscription` (`business_admin_id`, `status`, `trial_ends_at`)
SELECT ba.`id`, 'TRIAL', DATE_ADD(UTC_TIMESTAMP(), INTERVAL 15 DAY)
FROM `business_admin` ba
LEFT JOIN `subscription` s ON s.`business_admin_id` = ba.`id`
WHERE s.`id` IS NULL;
