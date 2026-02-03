import datetime
import secrets
from fastapi import Request, status
from fastapi.responses import JSONResponse
from ..utils.constant import DEFALUT_CONFIG, user_db
from ..utils.auth_util import verify_password

class AuthService:
    def __init__(self, server):
        self.server = server

    def login_admin_check(self, account, disable_other_admin, super_admin_account):
        if disable_other_admin and str(account) != str(super_admin_account):
            return False
        return True

    async def login(self, request: Request, account: str, password: str, temp_code: str, remember: bool):
        now = datetime.datetime.now(datetime.timezone.utc)
        server_config = self.server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
        root_path = request.scope.get("root_path", "")
        cookie_path = root_path if root_path else "/"

        if account and password:
            account = account.replace('<', '').replace('>', '')
            password = password.replace('<', '').replace('>', '')
            disable_other_admin = server_config.get("disable_other_admin", False)
            super_admin_account = str(server_config.get("super_admin_account"))
            
            if not self.login_admin_check(account, disable_other_admin, super_admin_account):
                return JSONResponse({"status": "error", "message": "只有超级管理才能登录。"}, status_code=403)

            if account in user_db["user"] and verify_password(password, user_db["user"][account]):
                token = secrets.token_hex(16)
                expiry = now + (datetime.timedelta(days=365) if remember else datetime.timedelta(days=1))
                max_age = (datetime.timedelta(days=365) if remember else datetime.timedelta(days=1)).total_seconds()

                request.session["logged_in"] = True
                request.session["token"] = token
                request.session["username"] = account

                user_db["token"][token] = {"user_name": account, "expire_time": str(expiry)}
                user_db.save()

                response = JSONResponse({"status": "success", "message": "登录成功"})
                response.set_cookie("token", token, expires=expiry, path=cookie_path, httponly=True, max_age=max_age)
                return response
            else:
                return JSONResponse({"status": "error", "message": "账号或密码错误。"}, status_code=401)

        elif temp_code:
            allow_temp_password = server_config.get('allow_temp_password', True)
            if not allow_temp_password:
                return JSONResponse({"status": "error", "message": "已禁止临时登录码登录。"}, status_code=403)

            if temp_code in user_db["temp"] and user_db["temp"][temp_code] > str(now):
                token = secrets.token_hex(16)
                expiry = now + datetime.timedelta(hours=2)
                max_age = datetime.timedelta(hours=2).total_seconds()

                request.session["logged_in"] = True
                request.session["token"] = token
                request.session["username"] = "tempuser"

                user_db["token"][token] = {"user_name": "tempuser", "expire_time": str(expiry)}
                user_db.save()

                response = JSONResponse({"status": "success", "message": "临时登录成功"})
                response.set_cookie("token", token, expires=expiry, path=cookie_path, httponly=True, max_age=max_age)
                self.server.logger.info(f"临时用户登录成功")
                return response
            else:
                if temp_code in user_db["temp"]:
                    del user_db["temp"][temp_code]
                    user_db.save()
                return JSONResponse({"status": "error", "message": "临时登录码无效。"}, status_code=401)
        else:
            return JSONResponse({"status": "error", "message": "请填写完整的登录信息。"}, status_code=400)
