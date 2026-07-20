import hashlib


class FingerprintGenerator:

    @staticmethod
    def generate(
        ip,
        user_agent,
        language,
    ):

        raw = "|".join([
            ip or "",
            user_agent or "",
            language or "",
        ])

        return hashlib.sha256(
            raw.encode()
        ).hexdigest()