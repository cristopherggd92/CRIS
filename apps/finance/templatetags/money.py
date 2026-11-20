from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def money(value, sign=False):
    """1234.5 -> $1,234.50 ; con sign=True agrega + o −."""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    text = f"${abs(amount):,.2f}"
    if amount < 0:
        return f"−{text}"
    if sign and amount > 0:
        return f"+{text}"
    return text
