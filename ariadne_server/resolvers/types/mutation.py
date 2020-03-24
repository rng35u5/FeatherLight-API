from math import floor
import json
from secrets import token_hex
from typing import Union, Optional
from datetime import (
    datetime,
    timedelta
)
from protobuf_to_dict import protobuf_to_dict
from ariadne import MutationType
from classes.user import User
from classes.lock import Lock
from classes.error import Error
from helpers.async_future import make_async
from helpers.mixins import LoggerMixin
from helpers.crypto import decode, hash_string
from helpers.hexify import HexEncoder
from helpers.attach_fees import attach_fees
from context import LND, REDIS, ARGON
from argon2.exceptions import VerificationError
from models import User as DB_User
import rpc_pb2 as ln

MUTATION = MutationType()

_mutation_logger = LoggerMixin()

@MUTATION.field('createUser')
# TODO add post limiter?
async def r_create_user(_: None, info, role: str = 'USER') -> User:
    """create a new user and save to db"""
    #create userid hex
    userid = token_hex(10)
    # create api object
    user = User(userid=userid, role=role)

    user.username = token_hex(10)

    user.password = token_hex(10)
    # save to db
    await DB_User.create(
        id=userid,
        username=user.username,
        password=ARGON.hash(user.password),
        role=role
    )
    # return api object to resolver
    return user


@MUTATION.field('login')
async def r_auth(_: None, info, username: str, password: str) -> Union[User, Error]:
    if not (user_obj := await DB_User.query.where(DB_User.username == username).gino.first()):
        return Error('Authentication Error', 'User not found')
    #verify pw hash
    try:
        ARGON.verify(user_obj.password,  password)
    except VerificationError:
        return Error('AuthenticationError', 'Incorrect password')

    if ARGON.check_needs_rehash(user_obj.password):
        await user_obj.update(password=ARGON.hash(password).apply())
    
    return User(
        userid = user_obj.id,
        role = user_obj.role
    )

    


#TODO GET RID OF THIS ITS FOR DEBUG
@MUTATION.field('forceUser')
async def r_force_user(_, info, user: str) -> str:
    if not (user_obj := await DB_User.get(user)):
        return Error('AuthenticationError', 'User not found in DB')
    return User(user_obj.id, user_obj.role)


@MUTATION.field('refreshAccessToken')
async def r_get_token(_: None, info) -> Union[User, Error]:
    # catch scenario of no refresh cookie
    if not (cookie := info.context['request'].cookies.get('refresh')):
        return Error(error_type='AuthenticationError', message='No refresh token sent')
    decode_response: Union[dict, Error] = decode(token=cookie, kind='refresh')
    # pass either error or user instance to union resolver
    _mutation_logger.logger.critical(decode_response)
    if isinstance(decode_response, Error):
        return decode_response
    if isinstance(decode_response, dict):
        return User(decode_response['id'], decode_response['role'])


@MUTATION.field('addInvoice')
# TODO add more flexiblilty in invoice creation
# TODO invoiceFor allows creating invoices for other users on their behalf
# FIXME doesnt work
async def r_add_invoice(user: User, info, *, memo: str, amt: int, invoiceFor: Optional[str] = None) -> dict:
    """Authenticated route"""
    expiry_time = 3600*24
    request = ln.Invoice(
        memo=memo,
        value=amt,
        expiry=expiry_time
    )
    response = await make_async(LND.stub.AddInvoice.future(request, timeout=5000))
    output = protobuf_to_dict(response)
    #change the bytes object to hex string for json serialization
    await REDIS.conn.rpush(f"userinvoices_for_{user.userid}", json.dumps(output, cls=HexEncoder))
    # add hex encoded bytes hash to redis
    _mutation_logger.logger.critical(f"setting key: payment_hash_{output['r_hash']} to {user.userid}")
    await REDIS.conn.set(f"payment_hash_{output['r_hash'].hex()}", user.userid)
    # decode response and return GraphQL invoice type
    pay_req_string = ln.PayReqString(pay_req=response.payment_request)
    decoded_invoice = await make_async(LND.stub.DecodePayReq.future(pay_req_string, timeout=5000))
    return {
        #payment_preimage is resolved in invoice_resolver
        'amount': decoded_invoice.num_satoshis,
        'memo': decoded_invoice.description,
        'payment_hash': decoded_invoice.payment_hash,
        'paid': False,
        'expiry': decoded_invoice.expiry,
        'timestamp': decoded_invoice.timestamp,
        'payment_request': response.payment_request,
    }


@MUTATION.field('payInvoice')
async def r_pay_invoice(user: User, info, invoice: str, amt: Optional[int] = None) -> dict:
    """Authenticated Route"""
    assert not amt or amt >= 0
    # obtain a db lock
    lock = Lock(
        REDIS.conn,
        'invoice_paying_for_' + user.userid
    )
    if not await lock.obtain_lock():
        _mutation_logger.logger.warning('Failed to acquire lock for user {}'.format(user.userid))
        return Error('PaymentError', 'DB is locked try again later')
    user_balance = await user.balance(info)
    request = ln.PayReqString(pay_req=invoice)
    decoded_invoice = await make_async(LND.stub.DecodePayReq.future(request, timeout=5000))
    real_amount = decoded_invoice.num_satoshis if decoded_invoice.num_satoshis > 0 else amt
    decoded_invoice.num_satoshis = real_amount
    _mutation_logger.logger.info(f"paying invoice user:{user.userid} with balance {user_balance}, for {real_amount}")
    
    if not real_amount:
        _mutation_logger.logger.warning(f"Invalid amount when paying invoice for user {user.userid}")
        await lock.release_lock()
        return Error(error_type='PaymentError', message='Invalid invoice amount')
    # check if user has enough balance including possible fees
    if not user_balance >= real_amount + floor(real_amount * 0.01):
        await lock.release_lock()
        return Error('PaymentError', 'Not enough balance to pay invoice')

    # determine destination of funds
    if LND.id_pubkey == decoded_invoice.destination:
        # this is internal invoice now, receiver add balance
        _mutation_logger.logger.info(decoded_invoice.payment_hash)
        
        if not (userid_payee := await REDIS.conn.get(f"payment_hash_{decoded_invoice.payment_hash}")):
            await lock.release_lock()
            return Error('PaymentError', 'Could not get user by payment hash')
        if await REDIS.conn.get(f"is_paid_{decoded_invoice.payment_hash}"):
            # invoice has already been paid
            await lock.release_lock()
            _mutation_logger.logger.warning('Attempted to pay invoice that was already paid')
            return Error('PaymentError', 'Invoice has already been paid')


        # initialize internal user payee
        # TODO FIXME change to sql db
        payee = User(userid_payee)

        doc_to_save = {
            #paid is implied by storage key
            #payment_preimage is resolved in invoice_resolver
            'amount': real_amount,
            'value': real_amount + floor(real_amount * 0.003),
            'fee': floor(real_amount * 0.003),
            'pay_req': invoice,
            'timestamp': decoded_invoice.timestamp,
            'memo': decoded_invoice.description,
            'type': 'local_invoice',
            'payment_hash': decoded_invoice.payment_hash
        }

        # sender spent his balance
        await REDIS.conn.rpush(
            f"paid_invoices_for_{user.userid}",
            json.dumps(doc_to_save, cls=HexEncoder)
        )
        await REDIS.conn.set(f"is_paid_{decoded_invoice.payment_hash}", 1)
        await lock.release_lock()
        return doc_to_save

    else:
        # this is a standard lightning network payment
        fee_limit = floor(real_amount * 0.005) + 1

        def req_gen():
            # define a request generator that yields a single payment request
            yield ln.SendRequest(
                payment_request=invoice,
                amt=real_amount, # amount is only used for tip invoices,
                fee_limit=ln.FeeLimit(fixed=fee_limit)
            )

        await user.lock_funds(invoice, decoded_invoice)
        for pay_res in LND.stub.SendPayment(req_gen()):
            # stream response synchronously FIXME
            _mutation_logger.logger.critical(f"pay res {pay_res}")
            await user.unlock_funds(invoice)
            if not pay_res.payment_error and pay_res.payment_preimage:
                # payment success
                pay_dict = protobuf_to_dict(pay_res)
                pay_dict['pay_req'] = invoice
                pay_dict['timestamp'] = decoded_invoice.timestamp
                pay_dict['memo'] = decoded_invoice.description
                pay_dict['amount'] = decoded_invoice.num_satoshis
                pay_dict['fee'] = max(fee_limit, pay_res.payment_route.total_fees)
                pay_dict['value'] = pay_dict['amount'] + pay_dict['fee']
                pay_dict['type'] = 'remote_invoice'
                pay_dict.pop('payment_error', None)
                pay_json = json.dumps(pay_dict, cls=HexEncoder)
                _mutation_logger.logger.info(pay_json)

                await REDIS.conn.rpush(f"paid_invoices_for_{user.userid}", pay_json)
                await lock.release_lock()
                return pay_dict
            else:
                # payment failed
                await lock.release_lock()
                return Error('PaymentError', pay_res.payment_error)