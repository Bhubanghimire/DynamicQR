"""Billing details copied onto invoices at checkout."""


def billing_address_snapshot(user):
    billing_address = getattr(user, "billing_address", None)
    if not billing_address:
        return {}
    return {
        "full_name": billing_address.full_name,
        "company_name": billing_address.company_name,
        "address_line_1": billing_address.address_line_1,
        "address_line_2": billing_address.address_line_2,
        "city": billing_address.city,
        "state_province": billing_address.state_province,
        "postal_code": billing_address.postal_code,
        "country": billing_address.country,
        "phone": billing_address.phone,
    }
