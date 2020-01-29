import functools
from inspect import iscoroutinefunction
from code.classes import User
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

def authenticate(func):
    @functools.wraps(func)
    async def authwrapper(obj, info, **kwargs):
        try:
            if not (u := await info.context.user_from_header()):
                return {
                    'ok': False,
                    'error': 'Invalid auth token'
                }
            elif iscoroutinefunction(func):
                return await func(obj, info, **kwargs, user=u)
            else:
                return func(obj, info, **kwargs, user=u)
        except ExpiredSignatureError:
            return {
                'ok': False,
                'error': 'Token has expired'
            }
        except InvalidTokenError:
            return {
                'ok': False,
                'error': 'Invalid auth token'
            }
    return authwrapper