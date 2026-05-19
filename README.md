# 🛒 Victor's Supermarket Management System

A full‑featured, web‑based Point of Sale (POS) and inventory management system for supermarkets.  
Built with **Flask** (Python), **SQLite**, and **Bootstrap 5** – green theme, role‑based access, 500+ products, sales reports, barcode printing, coupons, purchase orders, and much more.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.3-red)
![SQLite](https://img.shields.io/badge/Database-SQLite-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 📸 Screenshots

| Login | Dashboard | Point of Sale |
|-------|-----------|---------------|
| <img width="1357" height="640" alt="Screenshot 2026-05-19 205659" src="https://github.com/user-attachments/assets/0d2b8db8-00c9-4589-a912-d1e11aee04b7" /> | <img width="1346" height="642" alt="Screenshot 2026-05-19 205637" src="https://github.com/user-attachments/assets/3755c34a-716d-4e68-a268-616bf38bdb38" /> | <img width="1348" height="633" alt="Screenshot 2026-05-19 205520" src="https://github.com/user-attachments/assets/3f549a12-c434-4993-a516-7ad505c3b879" /> |

---

## ✨ Features

- **Secure login** with two roles:
  - **Admin** (full control) – username: `victor`, password: `victor@123`
  - **Cashier** (POS only) – username: `cashier`, password: *(blank)*
- **Point of Sale** – product search, barcode scan, category filter, quantity prompt, discount, payment method, optional receipt printing
- **Inventory Management** – add, edit, delete products; low‑stock alerts; inline stock update; export to Excel
- **500+ pre‑loaded products** with realistic categories (grains, dairy, beverages, snacks, fruits, vegetables, meat, frozen, household, personal care, baby)
- **20+ suppliers** and **50+ loyalty customers** pre‑loaded
- **Sales Reports** – daily sales, top products, payment method breakdown, date range filter
- **Customer & Supplier Management** – track customer spending, manage supplier contacts
- **User Management** (admin only) – create/modify users, assign roles, set passwords
- **Loyalty Program** – register customers, collect points, automatic tier levels (Bronze/Silver/Gold)
- **Expense Tracking & Budgets** – record expenses, set monthly budgets per category, alert when exceeded
- **Returns Processing** – refund items with configurable restocking fee
- **Discount Coupons** – create percentage/fixed coupons with expiry and minimum purchase
- **Purchase Order Management** – create POs, receive stock, auto‑update inventory
- **Supplier Performance** – track delivery times, quality, competitiveness
- **Customer Feedback** – collect ratings and comments after each sale
- **Profit Margin Report** – view profit per product and total potential margin
- **Slow‑Moving Products Report** – list products with zero sales in the last 30 days
- **Stock Value Trends** – chart of total inventory value
- **Export Reports** – Excel export for sales and inventory
- **Dark Mode** – toggle between light and dark themes (persists via localStorage)
- **Keyboard Shortcuts** – in POS: `F1` focus search, `F2` add to cart, `F9` checkout
- **Audit Log** – view all user actions with filtering by user, action, date
- **REST API** – JSON endpoints for products and sales (future mobile app integration)
- **Multi‑Branch Support** (optional) – admin can switch between branches
- **Automatic Database Backup** – scheduled daily backup (configurable)
- **Barcode Printing** – generate printable barcode labels for any product
- **Cloud Backup Stub** – ready for Google Drive integration

---

## 🖥️ Technology Stack

| Component       | Technology                               |
|----------------|------------------------------------------|
| Backend        | Python 3.8+ / Flask                      |
| Frontend       | HTML5, Bootstrap 5, JavaScript, Chart.js |
| Database       | SQLite (no separate server)              |
| Charts         | Chart.js (interactive)                   |
| Barcode        | `qrcode` + Pillow                        |
| Reports        | `pandas`, `openpyxl` (Excel export)      |
| Authentication | SHA‑256 hashing                          |
| Deployment     | Docker, Gunicorn (optional)              |

---

## 📦 Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/supermarket-system.git
cd supermarket-system
