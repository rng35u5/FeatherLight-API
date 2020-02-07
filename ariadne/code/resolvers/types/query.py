"""resolvers for query types"""
from math import floor
from typing import Optional
import pytest
from datetime import (
    datetime,
    timedelta
)
from secrets import token_hex
from ariadne import QueryType
from jwt.exceptions import ExpiredSignatureError
from protobuf_to_dict import protobuf_to_dict
import rpc_pb2 as ln
import rpc_pb2_grpc as lnrpc
from code.classes import User
from code.helpers import make_async, authenticate


query = QueryType()


@query.field('walletBalance')
async def r_walllet_balance(_: None, info) -> dict:
    response = await make_async(info.context.lnd.WalletBalance.future(ln.WalletBalanceRequest()))
    return {
        'totalBalance': response.total_balance,
        'confirmedBalance': response.confirmed_balance
    }

@pytest.fixture
@query.field('login')
async def r_auth(_: None, info, user: str, password: str) -> dict:
    try:
        if not (u := await User.from_credentials(ctx=info.context, login=user, pw=pw)):
            return 'Invalid Credentials'
        return u
    except ExpiredSignatureError:
        return 'Token has expired'


@query.field('token')
async def r_get_token(_: None, info) -> dict:
    if (cookie := info.context.req.cookies.get(info.context.cookie_name)):
        send = cookie.encode('utf-8')
        try:
            jsn = info.context.jwt.decode(send, kind='refresh')
        except ExpiredSignatureError:
            return 'Token has expired'
        return await User.from_auth(ctx=info.context, auth=jsn['token'])
    return 'No refresh token'


@query.field('BTCAddress')
@authenticate
async def r_get_address(_: None, info, *, user: User) -> dict:
    addr = await user.get_address()
    if not addr:
        await user.generate_address()
        addr = await user.get_address()
    return {
        'ok': True,
        'address': addr.decode('utf-8')
    }

@query.field('balance')
@authenticate
async def r_balance(_: None, info, *, user: User) -> dict:
    addr = await user.get_address()
    if not addr:
        await user.generate_address()
    await user.account_for_possible_txids()
    balance = await user.get_balance()
    if (balance < 0):
        balance = 0
    return {
        'ok': True,
        'availableBalance': balance
    }

@query.field('info')
@authenticate
async def r_info(_: None, info) -> dict:
    request = ln.GetInfoRequest()
    response = await make_async(info.context.lnd.GetInfo.future(request, timeout=5000))
    d = protobuf_to_dict(response)
    if 'chains' in d:
        del d['chains']
    if 'uris' in d:
        del d['uris']
    if 'features' in d:
        del d['features'] #TODO remove these and add the types in gql schema
    return {
        'ok': True,
        **d
    }

@query.field('txs')
@authenticate
async def r_txs(_: None, info, *, user: User) -> dict:
    if not await user.get_address():
        user.generate_address()
    await user.account_for_possible_txids()
    txs = await user.get_txs()
    locked_payments = await user.get_locked_payments()
    for locked in locked_payments:
        txs.append({
            'type': 'paid_invoice',
            'fee': floor(locked['amount'] * 0.01),
            'value': locked['amount'] + floor(locked['amount'] * 0.01),
            'timestamp': locked['timestamp'],
            'memo': 'Payment in transition'
        })
    return txs


@query.field('invoices')
@authenticate
async def r_invoices(_: None, info, *, last: Optional[int], user: User):
    invoices = await user.get_user_invoices()
    return invoices[-1 * last]

@query.field('pending')
@authenticate
async def r_pending(obj, info, **kwargs):
    if not await user.get_address():
        await user.generate_address()
    await user.account_for_possible_txids()
    return await user.get_pending_txs()


@query.field('decodeInvoice')
@authenticate
async def r_decode_invoice(_: None, info, *, invoice: str, user: User) -> dict:
    request = ln.PayReqString(pay_req=invoice)
    res = await make_async(info.context.lnd.DecodePayReq.future(request, timeout=5000))
    return {
        'ok': True,
        **protobuf_to_dict(res)
    }


# @query.field('checkRouteInvoice')
# @authenticate
# async def r_check_route(obj, info, invoice):
# TODO


