# JOE Cafeteria System - Information Manual

Welcome to the JOE (Just Order Eat) Cafeteria Operational Platform. This document contains all the essential information required to operate, test, and manage the system.

## 🚀 Getting Started

To run the application locally:
1.  Navigate to the project directory: `JOE_Cafeteria`
2.  Activate the virtual environment: `source env/bin/activate`
3.  Start the development server: `python3 manage.py runserver`
4.  Access the app at: `http://127.0.0.1:8000/`

---

## 🔐 Login Credentials

The system uses role-based access control. Use the following credentials to access different dashboards:

| Role | Username / Email | Password | Primary Dashboard |
| :--- | :--- | :--- | :--- |
| **Super Admin** | `admin` | `admin` | Django Admin (`/admin`) |
| **Cashier** | `cashier@joe.com` | `Cafeteria@123` | Pos Terminal & Dispute Management |
| **Kitchen Manager** | `kitchen@joe.com` | `Cafeteria@123` | Batch Production Board |
| **Serving Desk** | `serving@joe.com` | `Cafeteria@123` | QR Pickup & Item Handoff |
| **Cafeteria Manager** | `manager@joe.com` | `Cafeteria@123` | Analytics & Operational Overview |
| **Cafeteria Owner** | `owner@joe.com` | `Cafeteria@123` | Master Analytics & Sales Reports |
| **Guest / Student** | *Self-Signup* | *Dynamic* | Menu & Live Order Tracking |

---

## 🛠 Core Operational Features

### 1. Item-Level Tracking
Unlike traditional systems that track entire orders, JOE tracks **individual items**. This allows:
-   **Partial Serving:** Hand over a coffee while the sandwich is still grilling.
-   **Granular States:** Each item moves from `Pending` -> `Ready` -> `Served`.

### 2. QR-Based Pickup Validation
Every order generates a unique, immutable **UUID-based QR Code**.
-   **Security:** Prevents fraud or accidental double-serving.
-   **Validation:** Serving desk scans OR manually verifies the QR to unlock the handoff screen.
-   **Intelligence:** The QR stays "Active" until the very last item in the order is marked as `Served`.

### 3. Batch Production Intelligence (Kitchen)
The Kitchen Dashboard doesn't show individual receipts; it shows **Total Demand**.
-   Example: Instead of 5 different screens for "1 Dosa", the chef sees "Dosa: 5 Total".
-   **Mark Batch Ready:** One click notifies all 5 customers simultaneously that their specific item is ready.

### 4. Cashier Command Center
Cashiers have specialized power to:
-   **Punch Counter Orders:** Rapidly place orders for walk-up customers without phone-number friction.
-   **Dispute Management:** Instantly "Disable" an order to stop the kitchen from wasting food during a dispute or refund.
-   **Thermal Print:** Automatic formatting for standard 80mm thermal receipt printers.

---

## 📊 Database Schema Summary

-   **MenuItem:** Tracks `current_stock`, `prep_time_minutes`, and `inventory_type` (Batch/Continuous).
-   **Order:** Tracks `qr_code_id`, `payment_method`, and `is_disabled` status.
-   **OrderItem:** Tracks the specific status of every single plate being prepared.

---

> [!TIP]
> For testing the **Guest Flow**, simply click "Continue as Guest" on the login page and use any mock phone number. The system will remember your cart and orders tied to that number!
