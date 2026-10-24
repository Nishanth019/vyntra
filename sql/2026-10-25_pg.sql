-- PG / hostel as a second business type, plus expenses and staff salaries for every business.
-- DRAFT FOR REVIEW: not applied anywhere yet.
--
-- Safe for existing users:
--   * only new tables, plus nullable columns on `payment` and `staff` (old code never reads them);
--   * nothing is renamed, dropped or made NOT NULL on existing tables;
--   * the PG business type is hidden from older app builds by the API (see the note on business_type below).
--
-- One business account = one PG building, the same as one gym. An owner adds more PGs the same way
-- they add more gyms. Tenants are rows in `member` (like gym members); PG-only details live in
-- `pg_tenant`, the same 1-to-1 pattern as `gym_member`.

-- ---------------------------------------------------------------------------------------------
-- Business type. Older APKs list every active type on the home screen, so the API only returns
-- PG to app builds that send the header `X-Vyntra-Features: pg`. Old builds keep seeing Gym only.
INSERT INTO `business_type` (`name`, `code`, `description`) VALUES
  ('PG / Hostel', 'PG', 'Paying guest, hostel and co-living');

-- ---------------------------------------------------------------------------------------------
-- PG settings, one row per PG business account (created with the account).
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

-- ---------------------------------------------------------------------------------------------
-- Rooms and the beds in them. A bed is occupied when an ACTIVE or NOTICE tenancy points at it
-- (derived, not stored, so it can never drift).
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

-- ---------------------------------------------------------------------------------------------
-- PG-only tenant details, 1-to-1 with `member` (like `gym_member`).
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

-- ---------------------------------------------------------------------------------------------
-- A tenant's stay on a bed (the PG version of `membership`). Shifting beds updates pg_bed_id and
-- logs it in member_activity; a new tenancy is only started when someone comes back after leaving.
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

-- ---------------------------------------------------------------------------------------------
-- Rent bills. The morning job creates the next bill on each tenancy's due day; the first bill is
-- created when the tenant is added (prorated or full). One bill per tenancy per period, so a re-run
-- never duplicates.
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

-- Lines on a bill: rent, one-off charges, electricity.
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

-- Rent payments reuse the existing `payment` table (receipts, insights and summaries keep working).
-- Nullable, so every existing gym payment stays exactly as it is.
ALTER TABLE `payment`
  ADD COLUMN `pg_bill_id` bigint unsigned DEFAULT NULL AFTER `membership_id`,
  ADD KEY `idx_payment_pg_bill` (`pg_bill_id`),
  ADD CONSTRAINT `fk_payment_pg_bill` FOREIGN KEY (`pg_bill_id`) REFERENCES `pg_bill` (`id`);

-- ---------------------------------------------------------------------------------------------
-- Security deposit ledger. Held = COLLECT − REFUND − DEDUCT; still to collect = deposit_amount − COLLECT.
-- Deposits are not income; a DEDUCT (kept at checkout for damage etc.) is.
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

-- ---------------------------------------------------------------------------------------------
-- Expenses, for every business type (gym rent, electricity, equipment; PG groceries, repairs...).
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

-- ---------------------------------------------------------------------------------------------
-- Staff salaries, for every business type. New staff columns are nullable: existing staff rows and
-- old app builds are unaffected.
ALTER TABLE `staff`
  ADD COLUMN `salary` decimal(12,2) DEFAULT NULL,
  ADD COLUMN `joining_date` date DEFAULT NULL;

-- One row per staff member per month. Marking it paid creates one `expense` (category SALARY),
-- linked here so it is counted once (mypgmanager counts it twice).
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

-- ---------------------------------------------------------------------------------------------
-- Later, with their features (not in this migration): pg_charge (recurring/split charges),
-- pg_meter_reading (electricity), pg_join_request + member_document (QR self-registration and ID
-- photos), complaint, notice, pg_food_menu. Daily guests are also later.
