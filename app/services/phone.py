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
