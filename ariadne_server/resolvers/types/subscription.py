from ariadne import SubscriptionType
from classes.user import User

subs = SubscriptionType()


@subs.field('paymentChannel')
# @authenticate
async def r_sub_channel(_: None, info, user: User) -> dict:
    # pseudocode
    # access lnd stub via context
    # request the generator for payment results (see grpc docs)
    # yield response
    pass
