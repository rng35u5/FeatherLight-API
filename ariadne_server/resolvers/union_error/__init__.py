from .macaroon_response import MACAROON_RESPONSES as _MACAROON_RESPONSES
from .invoice_response import USER_INVOICE_RESPONSE as _USER_INVOICE_RESPONSE
from .invoice_response import PAY_INVOICE_RESPONSE as _PAY_INVOICE_RESPONSE
from .wallet_response import WALLET_RESPONSE as _WALLET_RESPONSE
from .user_response import USER_RESPONSE as _USER_RESPONSE
from .user_response import NEW_USER_RESPONSE as _NEW_USER_RESPONSE
from .channel_response import CHANNEL_RESPONSE as _CHANNEL_RESPONSE
from .lsat_response import LSAT_REPONSE as _LSAT_RESPONSE

UNION_ERROR = [
    *_MACAROON_RESPONSES,
    _USER_INVOICE_RESPONSE,
    _PAY_INVOICE_RESPONSE,
    _WALLET_RESPONSE,
    _USER_RESPONSE,
    _NEW_USER_RESPONSE,
    _CHANNEL_RESPONSE,
    _LSAT_RESPONSE
]
