from fastapi import Request, HTTPException, status, Depends
from guguwebui.constant import user_db

async def get_current_user(request: Request):
    """获取当前登录用户，如果未登录则抛出 401 异常"""
    token = request.cookies.get("token")
    
    if not token or token not in user_db.get("token", {}):
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not logged in"
        )

    if not request.session.get("logged_in"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not logged in"
        )

    return {
        "username": request.session.get("username"),
        "token": token
    }

async def get_current_admin(request: Request, current_user: dict = Depends(get_current_user)):
    """获取当前管理员用户，如果不是管理员则抛出 403 异常"""
    config_service = request.app.state.config_service
    server_config = config_service.get_config()
    
    super_admin_account = str(server_config.get("super_admin_account"))
    disable_other_admin = server_config.get("disable_other_admin", False)
    
    username = current_user.get("username")
    
    is_admin = True
    if disable_other_admin and str(username) != super_admin_account:
        is_admin = False
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
            
    return current_user
