
import logging
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from dodopayments import DodoPayments

from subscriptions.models import PackagePlan, PackagePlanPrice

logger = logging.getLogger(__name__)


class DodoProductService:
    """
    Synchronizes a local PackagePlan with a Dodo Payments product.

    Local source of truth:
        PackagePlan

    Dodo representation:
        Dodo Product

    Behavior:
        - No dodo_product_id -> CREATE Dodo product
        - Existing dodo_product_id -> UPDATE Dodo product
    """

    TAX_CATEGORY = getattr(
        settings,
        "DODO_PRODUCT_TAX_CATEGORY",
        "saas",
    )

    ENVIRONMENT = (
        "test_mode"
        if settings.DEBUG
        else "live_mode"
    )

    def __init__(self, client=None):
        self.client = client or DodoPayments(
            bearer_token=settings.DODO_PAYMENTS_API_KEY,
            environment=self.ENVIRONMENT,
        )

    # ============================================================
    # PUBLIC METHODS
    # ============================================================

    def sync_plan(self, plan):
        """
        Create or update the Dodo product for a PackagePlan.

        Returns:
            Dodo product response.

        Raises:
            ValueError:
                Invalid PackagePlan configuration.

            Exception:
                Any Dodo API error.
        """

        if not isinstance(plan, PackagePlan):
            raise TypeError(
                "DodoProductService.sync_plan() expects a PackagePlan instance."
            )

        responses = []
        for price in plan.prices.select_related("currency"):
            responses.append(self.sync_price(price))
        return responses

    def sync_price(self, price):
        """Create or update the Dodo product for one plan/currency price."""
        if not isinstance(price, PackagePlanPrice):
            raise TypeError("DodoProductService.sync_price() expects a PackagePlanPrice instance.")
        self._validate_price(price)
        if price.dodo_product_id:
            return self.update_price(price)
        return self.create_price(price)

    def create_price(self, price):
        self._validate_price(price)
        response = self.client.products.create(**self._build_product_payload(price))
        product_id = self._extract_product_id(response)
        if not product_id:
            raise RuntimeError("Dodo product was created but no product_id was returned.")
        PackagePlanPrice.objects.filter(pk=price.pk).update(dodo_product_id=product_id)
        price.dodo_product_id = product_id
        logger.info("Dodo product created. PackagePlanPrice=%s DodoProduct=%s", price.pk, product_id)
        return response

    def update_price(self, price):
        self._validate_price(price)
        response = self.client.products.update(
            price.dodo_product_id,
            **self._build_update_payload(price),
        )
        # Dodo normally updates a product in place and returns no new ID.
        # If an API version does return one, persist it so the local record
        # always follows Dodo's authoritative product ID.
        product_id = self._extract_product_id(response)
        if product_id and product_id != price.dodo_product_id:
            PackagePlanPrice.objects.filter(pk=price.pk).update(
                dodo_product_id=product_id
            )
            price.dodo_product_id = product_id
        logger.info("Dodo product updated. PackagePlanPrice=%s DodoProduct=%s", price.pk, price.dodo_product_id)
        return response

    def create_product(self, plan):
        """
        Create a new Dodo product for the PackagePlan.

        The returned Dodo product_id is saved into:
            PackagePlan.dodo_product_id
        """

        return self.sync_plan(plan)

        if plan.dodo_product_id:
            raise ValueError(
                f"PackagePlan {plan.pk} already has a Dodo product "
                f"({plan.dodo_product_id}). Use update_product()."
            )

        payload = self._build_product_payload(plan)

        logger.info(
            "Creating Dodo product for PackagePlan %s",
            plan.pk,
        )

        response = self.client.products.create(**payload)

        product_id = self._extract_product_id(response)

        if not product_id:
            raise RuntimeError(
                "Dodo product was created but no product_id "
                "was returned by Dodo Payments."
            )

        # Only update the local Dodo ID.
        #
        # We intentionally do not call plan.save() here because that
        # could trigger another synchronization.
        PackagePlan.objects.filter(pk=plan.pk).update(
            dodo_product_id=product_id
        )

        # Keep the in-memory object consistent.
        plan.dodo_product_id = product_id

        logger.info(
            "Dodo product created successfully. "
            "PackagePlan=%s DodoProduct=%s",
            plan.pk,
            product_id,
        )

        return response

    def update_product(self, plan):
        """
        Update the existing Dodo product belonging to PackagePlan.

        The product ID comes directly from:
            plan.dodo_product_id
        """

        return self.sync_plan(plan)

        if not plan.dodo_product_id:
            raise ValueError(
                f"PackagePlan {plan.pk} does not have a Dodo product ID. "
                f"Use create_product() instead."
            )

        payload = self._build_update_payload(plan)

        logger.info(
            "Updating Dodo product. "
            "PackagePlan=%s DodoProduct=%s",
            plan.pk,
            plan.dodo_product_id,
        )

        # The Dodo SDK expects the product identifier as the first
        # positional argument.  Passing it as ``id=`` does not match the
        # SDK method signature, so the local plan was saved while the Dodo
        # product was never updated.
        response = self.client.products.update(
            plan.dodo_product_id,
            **payload,
        )

        logger.info(
            "Dodo product updated successfully. "
            "PackagePlan=%s DodoProduct=%s",
            plan.pk,
            plan.dodo_product_id,
        )

        return response

    # ============================================================
    # PAYLOAD BUILDERS
    # ============================================================

    def _build_product_payload(self, price):
        """
        Build payload for Dodo product creation.
        """

        payload = {
            "name": self._build_product_name(price.package_plan, price),
            "description": self._build_product_description(price.package_plan),
            "price": self._build_price(price),
            "tax_category": self.TAX_CATEGORY,
            "metadata": self._build_metadata(price.package_plan, price),
        }

        return payload

    def _build_update_payload(self, price):
        """
        Build payload for Dodo product update.

        Dodo supports updating name, description, price,
        metadata and tax category.
        """

        return {
            "name": self._build_product_name(price.package_plan, price),
            "description": self._build_product_description(price.package_plan),
            "price": self._build_price(price),
            "tax_category": self.TAX_CATEGORY,
            "metadata": self._build_metadata(price.package_plan, price),
        }

    def _build_product_name(self, plan, price=None):
        """
        Example:

            Basic - Monthly
            Basic - Yearly
        """

        package_name = (
            plan.package.title
            if plan.package
            else "Package"
        )

        duration_name = (
            plan.duration.name
            if plan.duration
            else "One-time"
        )

        currency = f" - {price.currency.code.upper()}" if price else ""
        return f"{package_name} - {duration_name}{currency}"[:100]

    def _build_product_description(self, plan):
        """
        Build product description from Package.description.
        """

        if plan.package and plan.package.description:
            return plan.package.description[:1000]

        return self._build_product_name(plan)

    def _build_metadata(self, plan, price=None):
        """
        Metadata allows us to identify the Dodo product
        as belonging to this PackagePlan.
        """

        metadata = {
            "package_plan_id": str(plan.id),
            "package_id": str(plan.package_id)
            if plan.package_id
            else "",
            "duration_id": str(plan.duration_id)
            if plan.duration_id
            else "",
            "package_title": (
                plan.package.title
                if plan.package
                else ""
            ),
        }
        if price:
            metadata["package_plan_price_id"] = str(price.id)
            metadata["currency"] = price.currency.code.upper()

        if plan.duration:
            metadata["duration_name"] = plan.duration.name
            metadata["duration_days"] = str(
                plan.duration.days or ""
            )

        return metadata

    # ============================================================
    # PRICE
    # ============================================================

    def _build_price(self, price):
        plan = price.package_plan
        currency = price.currency.code.upper()

        amount = self._to_minor_units(
            price.price,
            currency,
        )

        if plan.duration:
            (
                interval,
                count,
            ) = self._get_recurring_interval(
                plan.duration.days
            )

            return {
                "type": "recurring_price",
                "price": amount,
                "currency": currency,
                "discount": 0,

                # How often payment is collected
                "payment_frequency_interval": interval,
                "payment_frequency_count": count,

                # Length of the subscription period
                "subscription_period_interval": interval,
                "subscription_period_count": count,
            }

        return {
            "type": "one_time_price",
            "price": amount,
            "currency": currency,
            "discount": 0,
        }

    def _get_recurring_interval(self, days):
        if not days:
            raise ValueError(
                "Recurring PackagePlan requires Duration.days."
            )

        days = int(days)

        if days == 1:
            return "Day", 1

        if days == 7:
            return "Week", 1

        if days == 14:
            return "Week", 2

        if days == 30:
            return "Month", 1

        if days == 60:
            return "Month", 2

        if days == 90:
            return "Month", 3

        if days == 180:
            return "Month", 6

        if days == 365:
            return "Year", 1

        raise ValueError(
            f"Unsupported recurring duration: {days} days. "
            "Supported durations are: "
            "1, 7, 14, 30, 60, 90, 180 and 365 days."
        )
    # ============================================================
    # VALIDATION
    # ============================================================

    def _validate_price(self, price):
        plan = price.package_plan
        if not plan.package:
            raise ValueError(
                f"PackagePlan {plan.pk} must have a package."
            )

        if not price.currency:
            raise ValueError(f"PackagePlanPrice {price.pk} must have a currency.")

        if price.price is None:
            raise ValueError(
                f"PackagePlan {plan.pk} must have a price."
            )

        if Decimal(str(price.price)) < Decimal("0"):
            raise ValueError(
                f"PackagePlan {plan.pk} cannot have a negative price."
            )

        # ``currency`` is a Currency model relation, not a string.
        # Calling ``upper()`` on the relation made every post-save Dodo
        # synchronization fail before the product was created/updated.
        currency = (price.currency.code or "").upper()

        if len(currency) != 3:
            raise ValueError(
                f"Invalid currency '{currency}' for PackagePlan {plan.pk}."
            )

        if not self.TAX_CATEGORY:
            raise ValueError(
                "DODO_PRODUCT_TAX_CATEGORY is not configured."
            )

    # ============================================================
    # RESPONSE HELPERS
    # ============================================================

    @staticmethod
    def _extract_product_id(response):
        """
        Extract product_id from Dodo SDK response.

        Supports:
            SDK model
            dictionary
            object with __dict__
        """

        if response is None:
            return None

        # SDK object
        product_id = getattr(
            response,
            "product_id",
            None,
        )

        if product_id:
            return product_id

        # Dictionary response
        if isinstance(response, dict):
            return response.get("product_id")

        # Generic object
        if hasattr(response, "__dict__"):
            return response.__dict__.get("product_id")

        return None

    # ============================================================
    # CURRENCY
    # ============================================================

    ZERO_DECIMAL_CURRENCIES = {
        "BIF",
        "CLP",
        "DJF",
        "GNF",
        "JPY",
        "KMF",
        "KRW",
        "MGA",
        "PYG",
        "RWF",
        "UGX",
        "VND",
        "VUV",
        "XAF",
        "XOF",
        "XPF",
    }

    THREE_DECIMAL_CURRENCIES = {
        "BHD",
        "IQD",
        "JOD",
        "KWD",
        "LYD",
        "OMR",
        "TND",
    }

    @classmethod
    def _currency_minor_units(cls, currency):
        currency = (currency or "USD").upper()

        if currency in cls.ZERO_DECIMAL_CURRENCIES:
            return 0

        if currency in cls.THREE_DECIMAL_CURRENCIES:
            return 3

        return 2

    @classmethod
    def _to_minor_units(cls, amount, currency):
        """
        Convert:

            USD 10.50 -> 1050
            JPY 1000   -> 1000
            BHD 10.500 -> 10500
        """

        decimals = cls._currency_minor_units(currency)

        factor = Decimal(10) ** decimals

        value = (
            Decimal(str(amount)) * factor
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )

        return int(value)
