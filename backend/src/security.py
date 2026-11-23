import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.contracts import Role
from src.storage import register

bearer = HTTPBearer(auto_error=False)


def password_hash(password, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f'{salt}${digest}'


def login(form):
    with register() as ledger:
        staff = ledger.one('SELECT * FROM staff WHERE username=%s', (form.username,))
    if not staff:
        password_hash(form.password)
        raise HTTPException(401, '账号或密码有误')
    stored = staff.pop('password_hash')
    if not hmac.compare_digest(stored, password_hash(form.password, stored.split('$', 1)[0])):
        raise HTTPException(401, '账号或密码有误')
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode({'sub': staff['username'], 'exp': expires}, os.environ['JWT_SECRET'], algorithm='HS256')
    return {'access_token': token, 'staff': staff}


def signed_in(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    try:
        if credentials is None:
            raise jwt.InvalidTokenError()
        claims = jwt.decode(credentials.credentials, os.environ['JWT_SECRET'], algorithms=['HS256'],
                            options={'require': ['exp', 'sub']})
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, '请重新登录', headers={'WWW-Authenticate': 'Bearer'}) from exc
    with register() as ledger:
        staff = ledger.one('SELECT username,display_name,role FROM staff WHERE username=%s', (claims['sub'],))
    if staff is None:
        raise HTTPException(401, '账号不可用')
    return staff


def allow(*roles: Role):
    def authorized(staff=Depends(signed_in)):
        if staff['role'] not in roles:
            raise HTTPException(403, '当前岗位无权执行此操作')
        return staff
    return authorized
