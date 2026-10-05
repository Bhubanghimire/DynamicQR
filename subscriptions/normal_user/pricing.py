"""Select the normal-user plan price for the request's country."""

import ipaddress
import logging

from babel.numbers import get_territory_currencies

from analytics.services.geo_parser import GeoParser


logger = logging.getLogger(__name__)


def request_currency_codes(request):
    """Return current tender currencies for the client's GeoIP country."""
    if request is None:
        return ()
    cached = getattr(request, "_subscription_currency_codes", None)
    if cached is not None:
        return cached

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = (forwarded_for.split(",", 1)[0].strip() if forwarded_for else
          request.META.get("REMOTE_ADDR", ""))
    codes = ()
    try:
        if ip and ipaddress.ip_address(ip).is_global:
            country_code = GeoParser.get_reader().city(ip).country.iso_code
            if country_code:
                codes = tuple(
                    code.upper() for code in get_territory_currencies(country_code)
                )
    except Exception:
        # GeoIP and currency lookup are best effort; USD remains the fallback.
        logger.warning("Could not determine subscription currency from client IP", exc_info=True)

    request._subscription_currency_codes = codes
    return codes


def select_plan_price(plan, request):
    """Prefer an active local-currency price, otherwise use active USD."""
    prices_by_currency = {
        price.currency.code.upper(): price
        for price in plan.prices.all()
        if price.is_active and price.currency.is_active
    }
    for code in request_currency_codes(request):
        if code in prices_by_currency:
            return prices_by_currency[code]
    return prices_by_currency.get("USD")
