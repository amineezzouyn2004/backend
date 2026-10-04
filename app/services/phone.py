import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType


class InvalidMoroccanPhone(ValueError):
    pass


def normalize_moroccan_mobile(value: str) -> str:
    try:
        parsed = phonenumbers.parse(value, "MA", keep_raw_input=False)
    except phonenumbers.NumberParseException as exc:
        raise InvalidMoroccanPhone from exc

    if (
        parsed.country_code != 212
        or not phonenumbers.is_valid_number(parsed)
        or phonenumbers.number_type(parsed) != PhoneNumberType.MOBILE
    ):
        raise InvalidMoroccanPhone
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def format_moroccan_local_sheet(phone_e164: str) -> str:
    """Sheet-only national form: 0 + 9 digits. Storage stays E.164."""
    if phone_e164.startswith("+212"):
        return "0" + phone_e164[4:]
    parsed = phonenumbers.parse(phone_e164, "MA")
    national = phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL)
    return "".join(char for char in national if char.isdigit())
