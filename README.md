# DynamicOCR

DynamicOCR is a comprehensive QR code management and analytics platform. It allows users to create, customize, and track QR codes with advanced features like bulk importing, custom domains, and detailed scan analytics.

## 🚀 Features

### 📱 QR Code Management
- **Project Organization**: Group your QR codes into projects for better management.
- **Dynamic QR Codes**: Create QR codes with short codes and custom link names.
- **Bulk Importing**: Import large numbers of QR codes from CSV/Excel files.
- **Visual Customization**: Customize the look and feel of your QR codes using templates and design settings.
- **Advanced Controls**: Set passwords, scan limits, and time limits for your QR codes.
- **Media Support**: Attach videos and thumbnails to your QR content.

### 📈 Advanced Analytics
- **Real-time Tracking**: Capture every scan event with detailed metadata.
- **Visitor Insights**: Track unique visitors using a privacy-conscious hashing mechanism.
- **Geo-Analytics**: Get insights into scan locations (Country, City, Region) using GeoIP.
- **Device Analytics**: Track browser, OS, and device types.
- **Time-series Data**: Analyze scan patterns by hour and day.

### 🌐 Domain & Infrastructure
- **Custom Domains**: Connect your own domains to your QR codes.
- **Automated SSL**: Provision and manage SSL certificates for custom domains.
- **Nginx Integration**: Automated Nginx configuration for custom domain routing.

### 💳 Subscription & Billing
- **Tiered Plans**: Multiple package options (Free, Paid) with varying limits.
- **Limit Enforcement**: Control the number of QR codes, total scans, and team members based on the subscription plan.
- **Billing Integration**: Integrated with Dodo Payments for seamless checkout and subscription renewals.
- **Invoice Management**: Automated invoice generation and payment tracking.

### 🤝 Collaboration
- **Team Invites**: Invite collaborators to projects via email.
- **Role-based Access**: Manage permissions for shared resources.

## 🛠 Tech Stack

- **Backend**: Django (Python)
- **API**: Django REST Framework (DRF)
- **Database**: SQLite (Default) / PostgreSQL (Recommended for Production)
- **Task Queue**: Celery (for bulk imports and background tasks)
- **Geolocation**: GeoLite2 (MaxMind)
- **Payments**: Dodo Payments
- **Web Server**: Nginx (for custom domain handling)

## 📐 Architecture Flow

1. **User Flow**:
   `Sign Up` $\rightarrow$ `Default Free Plan` $\rightarrow$ `Create Project` $\rightarrow$ `Generate/Import QR Codes` $\rightarrow$ `Customize Design` $\rightarrow$ `Deploy`.

2. **Scan Flow**:
   `Scan QR` $\rightarrow$ `Request captured by Backend` $\rightarrow$ `Analytics processed (GeoIP, Device)` $\rightarrow$ `ScanEvent stored` $\rightarrow$ `Summary tables updated` $\rightarrow$ `Redirect to target content`.

3. **Billing Flow**:
   `Choose Plan` $\rightarrow$ `Dodo Checkout` $\rightarrow$ `Payment Webhook` $\rightarrow$ `Subscription activated` $\rightarrow$ `Limits updated`.

## 📂 Project Structure

- `DynamicOCR/`: Main project configuration and API routing.
- `accounts/`: User authentication, profiles, and workspace management.
- `Qr/`: Core QR logic, importers, domain services, and design.
- `analytics/`: Scan tracking, visitor hashing, and reporting.
- `subscriptions/`: Package plans, billing, and payment integration.
- `system/`: Global configurations and shared utilities.
- `geoip/`: GeoIP database files.

## ⚙️ Installation

*(Note: This section should be tailored to your specific setup process)*

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run migrations:
   ```bash
   python manage.py migrate
   ```
4. Start the development server:
   ```bash
   python manage.py runserver
   ```

## 📄 API Documentation

The project uses OpenAPI/Swagger for documentation. Once the server is running, you can access the documentation at:
- `/swagger/`
- `/api/schema/`
