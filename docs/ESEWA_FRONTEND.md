# eSewa frontend integration

The Dodo API remains `POST /api/v1.1/user/subscriptions/payments/`. Use the eSewa path only when the customer chooses eSewa. eSewa purchases are one-time package periods; do not offer auto-renew for this provider.

## Configure backend

Set these server-side environment variables (never expose the secret key to the frontend):

- `ESEWA_PRODUCT_CODE`: merchant product/service code; use `EPAYTEST` only in eSewa UAT.
- `ESEWA_SECRET_KEY`: merchant HMAC key issued by eSewa.
- `ESEWA_TEST_MODE=true` for UAT, `false` for production. It defaults to Django `DEBUG`.
- `ESEWA_CALLBACK_BASE_URL`: public backend origin, for example `https://api.example.com`. eSewa must be able to return the browser to this origin.
- `FRONTEND_URL`: existing frontend origin, for example `https://app.example.com`.

The selected package plan price must have `currency: "NPR"` and a positive price. The backend takes the amount from the stored package plan price, not from a frontend request. For Dodo, ensure the plan's synced product is priced in NPR before offering both providers for that plan.

## 1. Start checkout

Authenticated request:

```http
POST /api/v1.1/user/subscriptions/payments/esewa/initiate/
Content-Type: application/json
Authorization: Bearer <access-token>

{"package_plan_id":"<plan-uuid>","package_plan_price_id":"<package-plan-price-uuid>"}
```

A successful response (`201`) looks like:

```json
{
  "payment_url": "https://rc-epay.esewa.com.np/api/epay/main/v2/form",
  "form_fields": {
    "amount": "100.00",
    "tax_amount": "0",
    "total_amount": "100.00",
    "transaction_uuid": "<unique-uuid>",
    "product_code": "EPAYTEST",
    "product_service_charge": "0",
    "product_delivery_charge": "0",
    "success_url": "https://api.example.com/api/payment/esewa/success/<invoice-uuid>/",
    "failure_url": "https://api.example.com/api/payment/esewa/failure/<invoice-uuid>/",
    "signed_field_names": "total_amount,transaction_uuid,product_code",
    "signature": "<base64-hmac>"
  },
  "invoice_number": "INV-...",
  "invoice_id": "<invoice-uuid>",
  "transaction_uuid": "<unique-uuid>",
  "amount": "100.00",
  "currency": "NPR",
  "auto_renew": false
}
```

Submit `form_fields` as an HTML form POST to `payment_url` in the same browser window. Do not `fetch()` eSewa's form endpoint. Do not modify any returned field or compute the signature in the browser.

```js
const form = document.createElement("form");
form.method = "POST";
form.action = result.payment_url;
for (const [name, value] of Object.entries(result.form_fields)) {
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = name;
  input.value = value;
  form.appendChild(input);
}
document.body.appendChild(form);
form.submit();
```

Store the `invoice_number` in local UI state before navigation if useful. Checkout initiation creates a pending invoice in the existing `Invoice` table. It does not grant access or create a `Payment` row.

## 2. Handle the return

eSewa returns the browser to the backend success or failure URL. The backend validates the signed return and asks eSewa's status API for the final transaction state. It then redirects to:

```text
{FRONTEND_URL}/billings/{invoice_id}/?invoice={invoice_number}&provider=esewa&payment={success|pending|failed}
```

Treat `payment` in this URL as a display hint only. Fetch the authenticated status endpoint before showing paid access:

```http
GET /api/v1.1/user/subscriptions/payments/esewa/status/?invoice_number=INV-...
Authorization: Bearer <access-token>
```

Example:

```json
{
  "invoice_number": "INV-...",
  "invoice_id": "<invoice-uuid>",
  "status": "paid",
  "payment_status": "success",
  "amount": "100.00",
  "currency": "NPR",
  "transaction_code": "<esewa-reference>",
  "subscription_id": "<subscription-uuid>"
}
```

`status` may be `pending`, `paid`, or `cancelled`. The endpoint rechecks eSewa if the invoice is not yet paid, so use it after return and allow the user to retry a pending status. Do not grant access based solely on eSewa's redirect or query parameters. A failed checkout can be started again with a new initiation request, invoice, and transaction UUID.

## Existing invoice and paid-list APIs

Confirmed eSewa transactions are stored in the existing `Payment` table with `provider: "esewa"` and linked to the paid invoice and subscription. The existing user invoice API serves both providers:

- `GET /api/v1.1/user/subscriptions/invoices/?status=paid` for the paid list.
- `GET /api/v1.1/user/subscriptions/invoices/{invoice_id}/` for the invoice detail.

Invoice responses now include `payment_provider` (`"dodo"` or `"esewa"`) and `payment_reference` (the Dodo payment ID or eSewa transaction code). No separate eSewa invoice or paid-list API is required.

## Errors

- `400`: invalid plan ID, free/zero-price plan, non-NPR plan, or `auto_renew: true`.
- `404`: inactive/missing plan or invoice not owned by the signed-in user.
- `409`: an active Dodo subscription is set to auto-renew; disable its auto-renew before using eSewa.
- `503`: eSewa server configuration is missing.

## eSewa references

[ePay V2 integration, signature, and status check](https://developer.esewa.com.np/pages/Epay-V2).
