# Vyntra API Reference

All responses below are real output from the current code, captured against a test database.

## Setup

The curls below use `http://localhost:8084` and a token for admin `1`. Replace the token with your own `access_token` from signup or login.

## Conventions

- **Base path:** `/api/v1/`
- **Auth:** every endpoint except signup, login and logout needs the JWT. Send it either as a header, `Authorization: Bearer <token>`, or as the `access_token` cookie that signup and login set (`HttpOnly`, `SameSite=Lax`, 180 days). With curl, add `-c cookies.txt` to login and `-b cookies.txt` to later calls instead of the header.
- **IDs go in query params**, e.g. `?business_account_id=1&member_id=5`. Business account detail is the one exception and uses `/business-accounts/{id}/`.
- **Tenant check:** every `business_account_id` is checked against the logged-in admin's active `business_account_admin` mapping. If there's no mapping, the response is `403`.
- **Updates are partial `PUT`s:** send only the fields you want to change. NOT NULL fields can't be set to `null` or `""`.
- **Paginated lists** (members, staff, plans, attendance) return `{"count", "next", "previous", "results"}`, 20 per page, and take `&page=N`. `count` is the total across all pages, so use it for dashboard numbers.
- **Unpaginated lists** (business types, duration types, business accounts, admins) return `{"results": [...]}`.
- **Dates** are `YYYY-MM-DD`. **Datetimes** are ISO 8601 in UTC, e.g. `2026-10-03T08:30:00Z`.

## Errors

| Status | When | Body |
|---|---|---|
| `400` | Validation failed | `{"field": ["message"]}` or `{"non_field_errors": [...]}` |
| `401` | Missing, invalid or expired token; wrong login | `{"detail": "Authentication credentials were not provided."}` |
| `403` | Admin has no access to this business account | `{"detail": "You do not have access to this business account."}` |
| `404` | Record not found, or it belongs to another business | `{"detail": "No ... matches the given query."}` |
| `405` | Method not supported on that URL | `{"detail": "Method \"PATCH\" not allowed."}` |

---

## 1. Auth

### Signup — `POST /auth/signup/`

Creates only a `business_admin`, with no business account. Returns the token and also sets the `access_token` cookie.

```bash
curl -X POST "http://localhost:8084/api/v1/auth/signup/" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Nishanth Bhukya",
    "mobile_no": "9876543210",
    "email": "nishanth@example.com",
    "password": "Str0ng!pass9"
  }'
```

**Response `201`**

```json
{
  "admin": {
    "id": 1,
    "full_name": "Nishanth Bhukya",
    "mobile_no": "9876543210",
    "email": "nishanth@example.com",
    "is_active": true,
    "last_login_at": null,
    "created_at": "2026-10-03T09:29:11.553732Z"
  },
  "access_token": "eyJhbGciOiJI..."
}
```

### Signup — validation error

```bash
curl -X POST "http://localhost:8084/api/v1/auth/signup/" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "X",
    "mobile_no": "9876543210",
    "email": "nishanth@example.com",
    "password": "123"
  }'
```

**Response `400`**

```json
{
  "mobile_no": [
    "An account with this mobile number already exists."
  ],
  "email": [
    "An account with this email already exists."
  ],
  "password": [
    "This password is too short. It must contain at least 8 characters.",
    "This password is too common.",
    "This password is entirely numeric."
  ]
}
```

### Login — `POST /auth/login/`

`login` can be the email (case-insensitive) or the mobile number. Sets the `access_token` cookie.

```bash
curl -X POST "http://localhost:8084/api/v1/auth/login/" \
  -H "Content-Type: application/json" \
  -d '{
    "login": "nishanth@example.com",
    "password": "Str0ng!pass9"
  }'
```

**Response `200`**

```json
{
  "admin": {
    "id": 1,
    "full_name": "Nishanth Bhukya",
    "mobile_no": "9876543210",
    "email": "nishanth@example.com",
    "is_active": true,
    "last_login_at": "2026-10-03T09:29:11.723917Z",
    "created_at": "2026-10-03T09:29:11.553732Z"
  },
  "access_token": "eyJhbGciOiJI..."
}
```

### Login — wrong credentials

```bash
curl -X POST "http://localhost:8084/api/v1/auth/login/" \
  -H "Content-Type: application/json" \
  -d '{
    "login": "9876543210",
    "password": "wrong"
  }'
```

**Response `401`**

```json
{
  "result": "Invalid login or password."
}
```

### Logout — `POST /auth/logout/`

Clears the `access_token` cookie. The token isn't revoked on the server, so it stays valid until it expires.

```bash
curl -X POST "http://localhost:8084/api/v1/auth/logout/"
```

**Response `204`** — empty body

### Any protected endpoint without a token

```bash
curl -X GET "http://localhost:8084/api/v1/me/"
```

**Response `401`**

```json
{
  "detail": "Authentication credentials were not provided."
}
```


---

## 2. My profile

### Get my profile — `GET /me/`

```bash
curl -X GET "http://localhost:8084/api/v1/me/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "id": 1,
  "full_name": "Nishanth Bhukya",
  "mobile_no": "9876543210",
  "email": "nishanth@example.com",
  "is_active": true,
  "last_login_at": "2026-10-03T09:29:11.723917Z",
  "created_at": "2026-10-03T09:29:11.553732Z"
}
```

### Update my profile — `PUT /me/`

Editable: `full_name`, `mobile_no`, `email`. Email and mobile must be unique.

```bash
curl -X PUT "http://localhost:8084/api/v1/me/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Nishanth B"
  }'
```

**Response `200`**

```json
{
  "id": 1,
  "full_name": "Nishanth B",
  "mobile_no": "9876543210",
  "email": "nishanth@example.com",
  "is_active": true,
  "last_login_at": "2026-10-03T09:29:11.723917Z",
  "created_at": "2026-10-03T09:29:11.553732Z"
}
```

### Change my password — `PUT /me/password/`

`current_password` must be correct. `new_password` goes through the same strength checks as signup.

```bash
curl -X PUT "http://localhost:8084/api/v1/me/password/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "current_password": "Str0ng!pass9",
    "new_password": "N3w!password9"
  }'
```

**Response `200`**

```json
{
  "result": "Password updated."
}
```


---

## 3. Master data

### Business types — `GET /business-types/`

Active types only.

```bash
curl -X GET "http://localhost:8084/api/v1/business-types/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "results": [
    {
      "id": 1,
      "name": "Gym",
      "code": "GYM",
      "description": "Gym and fitness center"
    }
  ]
}
```

### Duration types — `GET /duration-types/`

Active types only.

```bash
curl -X GET "http://localhost:8084/api/v1/duration-types/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "results": [
    {
      "id": 1,
      "name": "Day",
      "code": "DAY"
    },
    {
      "id": 2,
      "name": "Month",
      "code": "MONTH"
    },
    {
      "id": 3,
      "name": "Year",
      "code": "YEAR"
    }
  ]
}
```


---

## 4. Business accounts

### List my business accounts — `GET /business-accounts/`

Returns only accounts linked to the logged-in admin. Right after signup, this is empty.

```bash
curl -X GET "http://localhost:8084/api/v1/business-accounts/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "results": []
}
```

### Create business account — `POST /business-accounts/`

Required: `business_type_id` (must be active) and `name`. Everything else is optional. Also creates the `business_account_admin` mapping (role `ADMIN`) for you, in the same transaction.

```bash
curl -X POST "http://localhost:8084/api/v1/business-accounts/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "business_type_id": 1,
    "name": "FitZone Gym",
    "logo_url": "https://example.com/logo.png",
    "address": "123 Main Road",
    "city": "Bengaluru",
    "state": "Karnataka",
    "country": "India",
    "address_lat": 12.9716,
    "address_lng": 77.5946,
    "contact_no": "9876543210",
    "email": "fitzone@example.com",
    "website": "https://fitzone.com",
    "terms_and_conditions": "No refunds."
  }'
```

**Response `201`**

```json
{
  "id": 1,
  "business_type": {
    "id": 1,
    "name": "Gym",
    "code": "GYM",
    "description": "Gym and fitness center"
  },
  "name": "FitZone Gym",
  "logo_url": "https://example.com/logo.png",
  "address": "123 Main Road",
  "city": "Bengaluru",
  "state": "Karnataka",
  "country": "India",
  "address_lat": "12.97160000",
  "address_lng": "77.59460000",
  "contact_no": "9876543210",
  "email": "fitzone@example.com",
  "website": "https://fitzone.com",
  "terms_and_conditions": "No refunds.",
  "is_active": true,
  "created_at": "2026-10-03T09:29:12.268935Z",
  "updated_at": "2026-10-03T09:29:12.268948Z"
}
```

### List my business accounts — with data

```bash
curl -X GET "http://localhost:8084/api/v1/business-accounts/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "results": [
    {
      "id": 1,
      "business_type": {
        "id": 1,
        "name": "Gym",
        "code": "GYM",
        "description": "Gym and fitness center"
      },
      "name": "FitZone Gym",
      "logo_url": "https://example.com/logo.png",
      "address": "123 Main Road",
      "city": "Bengaluru",
      "state": "Karnataka",
      "country": "India",
      "address_lat": "12.97160000",
      "address_lng": "77.59460000",
      "contact_no": "9876543210",
      "email": "fitzone@example.com",
      "website": "https://fitzone.com",
      "terms_and_conditions": "No refunds.",
      "is_active": true,
      "created_at": "2026-10-03T09:29:12.268935Z",
      "updated_at": "2026-10-03T09:29:12.268948Z"
    }
  ]
}
```

### Get business account — `GET /business-accounts/{id}/`

Returns `404` if the account isn't linked to you.

```bash
curl -X GET "http://localhost:8084/api/v1/business-accounts/1/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "id": 1,
  "business_type": {
    "id": 1,
    "name": "Gym",
    "code": "GYM",
    "description": "Gym and fitness center"
  },
  "name": "FitZone Gym",
  "logo_url": "https://example.com/logo.png",
  "address": "123 Main Road",
  "city": "Bengaluru",
  "state": "Karnataka",
  "country": "India",
  "address_lat": "12.97160000",
  "address_lng": "77.59460000",
  "contact_no": "9876543210",
  "email": "fitzone@example.com",
  "website": "https://fitzone.com",
  "terms_and_conditions": "No refunds.",
  "is_active": true,
  "created_at": "2026-10-03T09:29:12.268935Z",
  "updated_at": "2026-10-03T09:29:12.268948Z"
}
```

### Update business account — `PUT /business-accounts/{id}/`

Partial. `business_type_id` and `is_active` can't be changed here and are ignored if sent.

```bash
curl -X PUT "http://localhost:8084/api/v1/business-accounts/1/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Hyderabad"
  }'
```

**Response `200`**

```json
{
  "id": 1,
  "business_type": {
    "id": 1,
    "name": "Gym",
    "code": "GYM",
    "description": "Gym and fitness center"
  },
  "name": "FitZone Gym",
  "logo_url": "https://example.com/logo.png",
  "address": "123 Main Road",
  "city": "Hyderabad",
  "state": "Karnataka",
  "country": "India",
  "address_lat": "12.97160000",
  "address_lng": "77.59460000",
  "contact_no": "9876543210",
  "email": "fitzone@example.com",
  "website": "https://fitzone.com",
  "terms_and_conditions": "No refunds.",
  "is_active": true,
  "created_at": "2026-10-03T09:29:12.268935Z",
  "updated_at": "2026-10-03T09:29:12.275322Z"
}
```

### Delete business account — `DELETE /business-accounts/{id}/`

Soft delete: sets `is_active=false`. After that the account is hidden from every endpoint, and its member, staff and other APIs return `403`.

```bash
curl -X DELETE "http://localhost:8084/api/v1/business-accounts/1/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `204`** — empty body


---

## 5. Membership plans

**Query params:**

| Param | Required | Description |
|---|---|---|
| `business_account_id` | always | Tenant |
| `plan_id` | GET one, PUT | Plan ID |
| `page` | no | Page number for the list |

### Create plan — `POST /membership-plans/?business_account_id=1`

Required: `name`, `duration_type_id` (must be active), `duration_value` (≥ 1), `amount` (≥ 0). New plans are always created with `is_active=true`.

```bash
curl -X POST "http://localhost:8084/api/v1/membership-plans/?business_account_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Monthly",
    "duration_type_id": 2,
    "duration_value": 1,
    "amount": "1500.00",
    "description": "1 month access"
  }'
```

**Response `201`**

```json
{
  "id": 1,
  "name": "Monthly",
  "duration_type": {
    "id": 2,
    "name": "Month",
    "code": "MONTH"
  },
  "duration_value": 1,
  "amount": "1500.00",
  "description": "1 month access",
  "is_active": true,
  "created_at": "2026-10-03T09:29:12.278839Z",
  "updated_at": "2026-10-03T09:29:12.278848Z"
}
```

### List plans — `GET /membership-plans/?business_account_id=1`

```bash
curl -X GET "http://localhost:8084/api/v1/membership-plans/?business_account_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Monthly",
      "duration_type": {
        "id": 2,
        "name": "Month",
        "code": "MONTH"
      },
      "duration_value": 1,
      "amount": "1500.00",
      "description": "1 month access",
      "is_active": true,
      "created_at": "2026-10-03T09:29:12.278839Z",
      "updated_at": "2026-10-03T09:29:12.278848Z"
    }
  ]
}
```

### Get plan — `GET /membership-plans/?business_account_id=1&plan_id=1`

```bash
curl -X GET "http://localhost:8084/api/v1/membership-plans/?business_account_id=1&plan_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "id": 1,
  "name": "Monthly",
  "duration_type": {
    "id": 2,
    "name": "Month",
    "code": "MONTH"
  },
  "duration_value": 1,
  "amount": "1500.00",
  "description": "1 month access",
  "is_active": true,
  "created_at": "2026-10-03T09:29:12.278839Z",
  "updated_at": "2026-10-03T09:29:12.278848Z"
}
```

### Update plan — `PUT /membership-plans/?business_account_id=1&plan_id=1`

Partial. Send `{"is_active": false}` to retire a plan, so it can no longer be assigned to new members.

```bash
curl -X PUT "http://localhost:8084/api/v1/membership-plans/?business_account_id=1&plan_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "1800.00"
  }'
```

**Response `200`**

```json
{
  "id": 1,
  "name": "Monthly",
  "duration_type": {
    "id": 2,
    "name": "Month",
    "code": "MONTH"
  },
  "duration_value": 1,
  "amount": "1800.00",
  "description": "1 month access",
  "is_active": true,
  "created_at": "2026-10-03T09:29:12.278839Z",
  "updated_at": "2026-10-03T09:29:12.284987Z"
}
```


---

## 6. Members

**Query params:**

| Param | Required | Description |
|---|---|---|
| `business_account_id` | always | Tenant |
| `member_id` | GET one, PUT, DELETE | Member ID |
| `search` | no | Case-insensitive match on first/last name, phone, email, member_code |
| `phone` | no | Exact phone |
| `member_code` | no | Exact member code |
| `is_active` | no | `true` / `false` |
| `end_date_from` | no | Active membership `end_date` ≥ this date |
| `end_date_to` | no | Active membership `end_date` ≤ this date |
| `page` | no | Page number |

**Dashboard filters** (taking today as 2026-10-03; read `count` from the response):

| Number | Query |
|---|---|
| Total members | *(no filter)* |
| Active / inactive | `&is_active=true` / `&is_active=false` |
| Membership currently valid | `&end_date_from=2026-10-03` |
| Expired | `&end_date_to=2026-10-02` |
| Expired in last 3 days | `&end_date_from=2026-09-30&end_date_to=2026-10-02` |
| Expiring in next 7 days | `&end_date_from=2026-10-03&end_date_to=2026-10-10` |
| Live today (attended) | Use `/member-attendance/?attendance_date=2026-10-03` |

### Create member — `POST /members/?business_account_id=1`

**Required:** `member_code` (unique within the business), `first_name`, `membership_plan_id` (an active plan of **this** business).
**Optional:** `last_name`, `phone`, `email`, `date_of_birth`, `gender`, `start_date` (defaults to today), and `payment`.

- **`payment`:** `amount` (> 0) and `payment_method` are required. `transaction_reference`, `notes` and `payment_date` (defaults to now) are optional.
- **What gets created:** the member, a `membership`, and the payment if you sent one, all in one transaction.
- **`end_date`** is worked out from the plan, counting `start_date` as day one.
- **`amount`** on the membership is copied from the plan.

```bash
curl -X POST "http://localhost:8084/api/v1/members/?business_account_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "member_code": "MEM001",
    "first_name": "Rahul",
    "last_name": "Kumar",
    "phone": "9876500001",
    "email": "rahul@example.com",
    "date_of_birth": "1998-05-10",
    "gender": "MALE",
    "membership_plan_id": 1,
    "start_date": "2026-10-03",
    "payment": {
      "amount": "1800.00",
      "payment_method": "UPI",
      "transaction_reference": "UPI123456",
      "notes": "First month"
    }
  }'
```

**Response `201`**

```json
{
  "id": 1,
  "member_code": "MEM001",
  "first_name": "Rahul",
  "last_name": "Kumar",
  "phone": "9876500001",
  "email": "rahul@example.com",
  "date_of_birth": "1998-05-10",
  "gender": "MALE",
  "is_active": true,
  "membership": {
    "id": 1,
    "membership_plan": {
      "id": 1,
      "name": "Monthly",
      "duration_type": {
        "id": 2,
        "name": "Month",
        "code": "MONTH"
      },
      "duration_value": 1,
      "amount": "1800.00",
      "description": "1 month access",
      "is_active": true,
      "created_at": "2026-10-03T09:29:12.278839Z",
      "updated_at": "2026-10-03T09:29:12.284987Z"
    },
    "start_date": "2026-10-03",
    "end_date": "2026-11-02",
    "amount": "1800.00",
    "is_active": true,
    "payments": [
      {
        "id": 1,
        "amount": "1800.00",
        "payment_date": "2026-10-03T09:29:12.292024Z",
        "payment_method": "UPI",
        "transaction_reference": "UPI123456",
        "notes": "First month",
        "created_at": "2026-10-03T09:29:12.292125Z"
      }
    ]
  },
  "created_at": "2026-10-03T09:29:12.291095Z",
  "updated_at": "2026-10-03T09:29:12.291103Z"
}
```

### Create member — duplicate `member_code`

```bash
curl -X POST "http://localhost:8084/api/v1/members/?business_account_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "member_code": "MEM001",
    "first_name": "X",
    "membership_plan_id": 1
  }'
```

**Response `400`**

```json
{
  "member_code": [
    "A member with this code already exists in this business."
  ]
}
```

### List members — `GET /members/?business_account_id=1&search=rahul&is_active=true`

Each member includes their **active** membership, with the plan and payments, or `membership: null`.

```bash
curl -X GET "http://localhost:8084/api/v1/members/?business_account_id=1&search=rahul&is_active=true" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "member_code": "MEM001",
      "first_name": "Rahul",
      "last_name": "Kumar",
      "phone": "9876500001",
      "email": "rahul@example.com",
      "date_of_birth": "1998-05-10",
      "gender": "MALE",
      "is_active": true,
      "membership": {
        "id": 1,
        "membership_plan": {
          "id": 1,
          "name": "Monthly",
          "duration_type": {
            "id": 2,
            "name": "Month",
            "code": "MONTH"
          },
          "duration_value": 1,
          "amount": "1800.00",
          "description": "1 month access",
          "is_active": true,
          "created_at": "2026-10-03T09:29:12.278839Z",
          "updated_at": "2026-10-03T09:29:12.284987Z"
        },
        "start_date": "2026-10-03",
        "end_date": "2026-11-02",
        "amount": "1800.00",
        "is_active": true,
        "payments": [
          {
            "id": 1,
            "amount": "1800.00",
            "payment_date": "2026-10-03T09:29:12.292024Z",
            "payment_method": "UPI",
            "transaction_reference": "UPI123456",
            "notes": "First month",
            "created_at": "2026-10-03T09:29:12.292125Z"
          }
        ]
      },
      "created_at": "2026-10-03T09:29:12.291095Z",
      "updated_at": "2026-10-03T09:29:12.291103Z"
    }
  ]
}
```

### List members by membership end date

The example uses a wide range so it returns the sample member. For dashboard ranges, see the table above.

```bash
curl -X GET "http://localhost:8084/api/v1/members/?business_account_id=1&end_date_from=2026-10-03&end_date_to=2026-11-12" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "member_code": "MEM001",
      "first_name": "Rahul",
      "last_name": "Kumar",
      "phone": "9876500001",
      "email": "rahul@example.com",
      "date_of_birth": "1998-05-10",
      "gender": "MALE",
      "is_active": true,
      "membership": {
        "id": 1,
        "membership_plan": {
          "id": 1,
          "name": "Monthly",
          "duration_type": {
            "id": 2,
            "name": "Month",
            "code": "MONTH"
          },
          "duration_value": 1,
          "amount": "1800.00",
          "description": "1 month access",
          "is_active": true,
          "created_at": "2026-10-03T09:29:12.278839Z",
          "updated_at": "2026-10-03T09:29:12.284987Z"
        },
        "start_date": "2026-10-03",
        "end_date": "2026-11-02",
        "amount": "1800.00",
        "is_active": true,
        "payments": [
          {
            "id": 1,
            "amount": "1800.00",
            "payment_date": "2026-10-03T09:29:12.292024Z",
            "payment_method": "UPI",
            "transaction_reference": "UPI123456",
            "notes": "First month",
            "created_at": "2026-10-03T09:29:12.292125Z"
          }
        ]
      },
      "created_at": "2026-10-03T09:29:12.291095Z",
      "updated_at": "2026-10-03T09:29:12.291103Z"
    }
  ]
}
```

### Get member — `GET /members/?business_account_id=1&member_id=1`

```bash
curl -X GET "http://localhost:8084/api/v1/members/?business_account_id=1&member_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "id": 1,
  "member_code": "MEM001",
  "first_name": "Rahul",
  "last_name": "Kumar",
  "phone": "9876500001",
  "email": "rahul@example.com",
  "date_of_birth": "1998-05-10",
  "gender": "MALE",
  "is_active": true,
  "membership": {
    "id": 1,
    "membership_plan": {
      "id": 1,
      "name": "Monthly",
      "duration_type": {
        "id": 2,
        "name": "Month",
        "code": "MONTH"
      },
      "duration_value": 1,
      "amount": "1800.00",
      "description": "1 month access",
      "is_active": true,
      "created_at": "2026-10-03T09:29:12.278839Z",
      "updated_at": "2026-10-03T09:29:12.284987Z"
    },
    "start_date": "2026-10-03",
    "end_date": "2026-11-02",
    "amount": "1800.00",
    "is_active": true,
    "payments": [
      {
        "id": 1,
        "amount": "1800.00",
        "payment_date": "2026-10-03T09:29:12.292024Z",
        "payment_method": "UPI",
        "transaction_reference": "UPI123456",
        "notes": "First month",
        "created_at": "2026-10-03T09:29:12.292125Z"
      }
    ]
  },
  "created_at": "2026-10-03T09:29:12.291095Z",
  "updated_at": "2026-10-03T09:29:12.291103Z"
}
```

### Update member + record a payment — `PUT /members/?business_account_id=1&member_id=1`

Partial. Sending `payment` **adds** a new payment to the current membership. It doesn't edit an earlier one.

```bash
curl -X PUT "http://localhost:8084/api/v1/members/?business_account_id=1&member_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "9999999999",
    "payment": {
      "amount": "500.00",
      "payment_method": "CASH"
    }
  }'
```

**Response `200`**

```json
{
  "id": 1,
  "member_code": "MEM001",
  "first_name": "Rahul",
  "last_name": "Kumar",
  "phone": "9999999999",
  "email": "rahul@example.com",
  "date_of_birth": "1998-05-10",
  "gender": "MALE",
  "is_active": true,
  "membership": {
    "id": 1,
    "membership_plan": {
      "id": 1,
      "name": "Monthly",
      "duration_type": {
        "id": 2,
        "name": "Month",
        "code": "MONTH"
      },
      "duration_value": 1,
      "amount": "1800.00",
      "description": "1 month access",
      "is_active": true,
      "created_at": "2026-10-03T09:29:12.278839Z",
      "updated_at": "2026-10-03T09:29:12.284987Z"
    },
    "start_date": "2026-10-03",
    "end_date": "2026-11-02",
    "amount": "1800.00",
    "is_active": true,
    "payments": [
      {
        "id": 2,
        "amount": "500.00",
        "payment_date": "2026-10-03T09:29:12.311621Z",
        "payment_method": "CASH",
        "transaction_reference": null,
        "notes": null,
        "created_at": "2026-10-03T09:29:12.311722Z"
      },
      {
        "id": 1,
        "amount": "1800.00",
        "payment_date": "2026-10-03T09:29:12.292024Z",
        "payment_method": "UPI",
        "transaction_reference": "UPI123456",
        "notes": "First month",
        "created_at": "2026-10-03T09:29:12.292125Z"
      }
    ]
  },
  "created_at": "2026-10-03T09:29:12.291095Z",
  "updated_at": "2026-10-03T09:29:12.311191Z"
}
```

### Change a member's plan — `PUT /members/?business_account_id=1&member_id=1`

A different `membership_plan_id` ends the current membership and creates a new one, starting on `start_date` or today. Sending the same plan changes nothing. A payment sent in the same request goes to the new membership.

```bash
curl -X PUT "http://localhost:8084/api/v1/members/?business_account_id=1&member_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "membership_plan_id": 2,
    "payment": {
      "amount": "15000.00",
      "payment_method": "CARD"
    }
  }'
```

**Response `200`**

```json
{
  "id": 1,
  "member_code": "MEM001",
  "first_name": "Rahul",
  "last_name": "Kumar",
  "phone": "9999999999",
  "email": "rahul@example.com",
  "date_of_birth": "1998-05-10",
  "gender": "MALE",
  "is_active": true,
  "membership": {
    "id": 2,
    "membership_plan": {
      "id": 2,
      "name": "Yearly",
      "duration_type": {
        "id": 3,
        "name": "Year",
        "code": "YEAR"
      },
      "duration_value": 1,
      "amount": "15000.00",
      "description": null,
      "is_active": true,
      "created_at": "2026-10-03T09:29:12.287455Z",
      "updated_at": "2026-10-03T09:29:12.287464Z"
    },
    "start_date": "2026-10-03",
    "end_date": "2027-10-02",
    "amount": "15000.00",
    "is_active": true,
    "payments": [
      {
        "id": 3,
        "amount": "15000.00",
        "payment_date": "2026-10-03T09:29:12.318013Z",
        "payment_method": "CARD",
        "transaction_reference": null,
        "notes": null,
        "created_at": "2026-10-03T09:29:12.318079Z"
      }
    ]
  },
  "created_at": "2026-10-03T09:29:12.291095Z",
  "updated_at": "2026-10-03T09:29:12.317309Z"
}
```

### Delete member — `DELETE /members/?business_account_id=1&member_id=2`

Soft delete: sets the member's `is_active=false` and ends their active membership. Payments are kept.

```bash
curl -X DELETE "http://localhost:8084/api/v1/members/?business_account_id=1&member_id=2" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `204`** — empty body


---

## 7. Staff

**Query params:**

| Param | Required | Description |
|---|---|---|
| `business_account_id` | always | Tenant |
| `staff_id` | GET one, PUT | Staff ID |
| `search` | no | Case-insensitive match on first/last name, phone, email, employee_code |
| `phone` | no | Exact phone |
| `employee_code` | no | Exact employee code |
| `is_active` | no | `true` / `false` |
| `page` | no | Page number |

### Create staff — `POST /staff/?business_account_id=1`

Required: `employee_code` (unique within the business) and `first_name`. Optional: `last_name`, `phone`, `email`, `role`. New staff are always created with `is_active=true`.

```bash
curl -X POST "http://localhost:8084/api/v1/staff/?business_account_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "employee_code": "EMP001",
    "first_name": "Suresh",
    "last_name": "Rao",
    "phone": "9876500010",
    "email": "suresh@example.com",
    "role": "Trainer"
  }'
```

**Response `201`**

```json
{
  "id": 1,
  "employee_code": "EMP001",
  "first_name": "Suresh",
  "last_name": "Rao",
  "phone": "9876500010",
  "email": "suresh@example.com",
  "role": "Trainer",
  "is_active": true,
  "created_at": "2026-10-03T09:29:12.329257Z",
  "updated_at": "2026-10-03T09:29:12.329266Z"
}
```

### List staff — `GET /staff/?business_account_id=1&is_active=true`

```bash
curl -X GET "http://localhost:8084/api/v1/staff/?business_account_id=1&is_active=true" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "employee_code": "EMP001",
      "first_name": "Suresh",
      "last_name": "Rao",
      "phone": "9876500010",
      "email": "suresh@example.com",
      "role": "Trainer",
      "is_active": true,
      "created_at": "2026-10-03T09:29:12.329257Z",
      "updated_at": "2026-10-03T09:29:12.329266Z"
    }
  ]
}
```

### Get staff — `GET /staff/?business_account_id=1&staff_id=1`

```bash
curl -X GET "http://localhost:8084/api/v1/staff/?business_account_id=1&staff_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "id": 1,
  "employee_code": "EMP001",
  "first_name": "Suresh",
  "last_name": "Rao",
  "phone": "9876500010",
  "email": "suresh@example.com",
  "role": "Trainer",
  "is_active": true,
  "created_at": "2026-10-03T09:29:12.329257Z",
  "updated_at": "2026-10-03T09:29:12.329266Z"
}
```

### Update / deactivate staff — `PUT /staff/?business_account_id=1&staff_id=1`

Partial. Send `is_active: false` to deactivate.

```bash
curl -X PUT "http://localhost:8084/api/v1/staff/?business_account_id=1&staff_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "Head Trainer",
    "is_active": false
  }'
```

**Response `200`**

```json
{
  "id": 1,
  "employee_code": "EMP001",
  "first_name": "Suresh",
  "last_name": "Rao",
  "phone": "9876500010",
  "email": "suresh@example.com",
  "role": "Head Trainer",
  "is_active": false,
  "created_at": "2026-10-03T09:29:12.329257Z",
  "updated_at": "2026-10-03T09:29:12.335130Z"
}
```


---

## 8. Member attendance

**Query params:**

| Param | Required | Description |
|---|---|---|
| `business_account_id` | always | Tenant |
| `attendance_id` | GET one, PUT | Attendance ID |
| `attendance_date` | no | Members present on that date |
| `member_id` | no | One member's attendance history |
| `page` | no | Page number |

### Mark attendance — `POST /member-attendance/?business_account_id=1`

Required: `member_id` (an active member of this business). Optional: `attendance_date` (defaults to today), `check_in_time` (defaults to now), and `check_out_time`.

```bash
curl -X POST "http://localhost:8084/api/v1/member-attendance/?business_account_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "member_id": 1
  }'
```

**Response `201`**

```json
{
  "id": 1,
  "member": {
    "id": 1,
    "member_code": "MEM001",
    "first_name": "Rahul",
    "last_name": "Kumar"
  },
  "attendance_date": "2026-10-03",
  "check_in_time": "2026-10-03T09:29:12.337178Z",
  "check_out_time": null,
  "created_at": "2026-10-03T09:29:12.337486Z",
  "updated_at": "2026-10-03T09:29:12.337493Z"
}
```

### Mark attendance — already marked that day

```bash
curl -X POST "http://localhost:8084/api/v1/member-attendance/?business_account_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "member_id": 1
  }'
```

**Response `400`**

```json
{
  "non_field_errors": [
    "Attendance is already marked for this member on this date."
  ]
}
```

### List attendance — `GET /member-attendance/?business_account_id=1&attendance_date=2026-10-03`

```bash
curl -X GET "http://localhost:8084/api/v1/member-attendance/?business_account_id=1&attendance_date=2026-10-03" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "member": {
        "id": 1,
        "member_code": "MEM001",
        "first_name": "Rahul",
        "last_name": "Kumar"
      },
      "attendance_date": "2026-10-03",
      "check_in_time": "2026-10-03T09:29:12.337178Z",
      "check_out_time": null,
      "created_at": "2026-10-03T09:29:12.337486Z",
      "updated_at": "2026-10-03T09:29:12.337493Z"
    }
  ]
}
```

### Get attendance — `GET /member-attendance/?business_account_id=1&attendance_id=1`

```bash
curl -X GET "http://localhost:8084/api/v1/member-attendance/?business_account_id=1&attendance_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "id": 1,
  "member": {
    "id": 1,
    "member_code": "MEM001",
    "first_name": "Rahul",
    "last_name": "Kumar"
  },
  "attendance_date": "2026-10-03",
  "check_in_time": "2026-10-03T09:29:12.337178Z",
  "check_out_time": null,
  "created_at": "2026-10-03T09:29:12.337486Z",
  "updated_at": "2026-10-03T09:29:12.337493Z"
}
```

### Check out / correct times — `PUT /member-attendance/?business_account_id=1&attendance_id=1`

Only `check_in_time` and `check_out_time` can be changed. Check-out can't be before check-in.

```bash
curl -X PUT "http://localhost:8084/api/v1/member-attendance/?business_account_id=1&attendance_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "check_out_time": "2026-10-04T08:30:00Z"
  }'
```

**Response `200`**

```json
{
  "id": 1,
  "member": {
    "id": 1,
    "member_code": "MEM001",
    "first_name": "Rahul",
    "last_name": "Kumar"
  },
  "attendance_date": "2026-10-03",
  "check_in_time": "2026-10-03T09:29:12.337178Z",
  "check_out_time": "2026-10-04T08:30:00Z",
  "created_at": "2026-10-03T09:29:12.337486Z",
  "updated_at": "2026-10-03T09:29:12.344245Z"
}
```


---

## 9. Business admins

**Query params:**

| Param | Required | Description |
|---|---|---|
| `business_account_id` | always | Tenant |
| `admin_id` | GET one, PUT | The admin's `business_admin` ID |

### Create admin — `POST /admins/?business_account_id=1`

Same body as signup. Creates the admin with their password and links them to this business, in one transaction. They can log in straight away.

```bash
curl -X POST "http://localhost:8084/api/v1/admins/?business_account_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Anita Sharma",
    "mobile_no": "9000000001",
    "email": "anita@example.com",
    "password": "Str0ng!pass9"
  }'
```

**Response `201`**

```json
{
  "admin": {
    "id": 2,
    "full_name": "Anita Sharma",
    "mobile_no": "9000000001",
    "email": "anita@example.com",
    "is_active": true,
    "last_login_at": null,
    "created_at": "2026-10-03T09:29:12.517897Z"
  },
  "role": "ADMIN",
  "is_active": true,
  "created_at": "2026-10-03T09:29:12.518435Z"
}
```

### List admins — `GET /admins/?business_account_id=1`

```bash
curl -X GET "http://localhost:8084/api/v1/admins/?business_account_id=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "results": [
    {
      "admin": {
        "id": 1,
        "full_name": "Nishanth B",
        "mobile_no": "9876543210",
        "email": "nishanth@example.com",
        "is_active": true,
        "last_login_at": "2026-10-03T09:29:11.723917Z",
        "created_at": "2026-10-03T09:29:11.553732Z"
      },
      "role": "ADMIN",
      "is_active": true,
      "created_at": "2026-10-03T09:29:12.269556Z"
    },
    {
      "admin": {
        "id": 2,
        "full_name": "Anita Sharma",
        "mobile_no": "9000000001",
        "email": "anita@example.com",
        "is_active": true,
        "last_login_at": null,
        "created_at": "2026-10-03T09:29:12.517897Z"
      },
      "role": "ADMIN",
      "is_active": true,
      "created_at": "2026-10-03T09:29:12.518435Z"
    }
  ]
}
```

### Get admin — `GET /admins/?business_account_id=1&admin_id=2`

```bash
curl -X GET "http://localhost:8084/api/v1/admins/?business_account_id=1&admin_id=2" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4"
```

**Response `200`**

```json
{
  "admin": {
    "id": 2,
    "full_name": "Anita Sharma",
    "mobile_no": "9000000001",
    "email": "anita@example.com",
    "is_active": true,
    "last_login_at": null,
    "created_at": "2026-10-03T09:29:12.517897Z"
  },
  "role": "ADMIN",
  "is_active": true,
  "created_at": "2026-10-03T09:29:12.518435Z"
}
```

### Update / deactivate admin — `PUT /admins/?business_account_id=1&admin_id=2`

Partial: `full_name`, `mobile_no`, `email` and `is_active`. `is_active` only removes or restores their access to **this** business. You can't deactivate yourself.

```bash
curl -X PUT "http://localhost:8084/api/v1/admins/?business_account_id=1&admin_id=2" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZG1pbl9pZCI6MSwidGltZSI6MTc5MTAyMDg1MC4yNzM5NTQyLCJleHAiOjE4MDY1NzI4NTB9.mbdZaqMr8rRil0xV33S_jIvts95a03PzwcOWdK7Set4" \
  -H "Content-Type: application/json" \
  -d '{
    "mobile_no": "9000000002",
    "is_active": false
  }'
```

**Response `200`**

```json
{
  "admin": {
    "id": 2,
    "full_name": "Anita Sharma",
    "mobile_no": "9000000002",
    "email": "anita@example.com",
    "is_active": true,
    "last_login_at": null,
    "created_at": "2026-10-03T09:29:12.517897Z"
  },
  "role": "ADMIN",
  "is_active": false,
  "created_at": "2026-10-03T09:29:12.518435Z"
}
```
