"""统一业务异常与全局异常处理器。

为什么需要它：
- 之前后端直接 raise HTTPException，前端只能靠 HTTP 状态码（如 401）猜错误原因，
  导致「账号或密码错误」和「登录已过期」都被前端当成同一种 401 处理。
- 这里给每个错误一个稳定、与 HTTP 状态码解耦的「业务码 code」，
  前端按 code 分流，文案以后端返回的 message 为准。

约定：业务码 = HTTP 状态码 * 100 + 子序号
  - 40100 表示通用认证失败；40101 / 40102 / 40103 是具体原因
  - 40400 通用不存在；40401 / 40402 是具体资源
前端只要判断 code 落在哪个区间 / 是否在某组，就能决定跳不跳登录页、提示什么。
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# ---- 业务码常量（集中定义，避免散落魔法数字）----
ERR_ACCOUNT_EXISTS = 40001        # 注册时账号已存在
ERR_BAD_CREDENTIALS = 40101       # 登录：账号或密码错误
ERR_TOKEN_INVALID = 40102         # 令牌无效或已过期
ERR_TOKEN_USER_GONE = 40103       # 令牌里的用户已被删除
ERR_ACCOUNT_DISABLED = 40104      # 账号已被停用（登录 / 携带令牌访问时拦截）
ERR_USER_NOT_FOUND = 40402        # 查询用户：不存在
ERR_COMPETITOR_NOT_FOUND = 40401  # 查询竞品：不存在
ERR_EVENT_NOT_FOUND = 40403       # 查询情报事件：不存在
ERR_REPORT_NOT_FOUND = 40404      # 查询周报：不存在
ERR_SHARE_NOT_FOUND = 40405       # 免登录分享链接：不存在或已撤销
ERR_SHARE_EXPIRED = 41001         # 免登录分享链接：已过期
ERR_INVALID_SOURCE = 40002        # 新建监控源：缺少可用网址
ERR_NO_ENABLED_SOURCE = 40003     # 手动抓取：该竞品没有启用的监控页面
ERR_LLM_CONFIG_INVALID = 40004    # 保存模型设置：启用时配置不完整
ERR_OLD_PASSWORD_WRONG = 40005    # 修改密码：原密码不正确（注意别用 401xx，前端会当成登录失效）
ERR_EMAIL_INVALID = 40006         # 用户中心：邮箱格式不正确
ERR_PASSWORD_TOO_SHORT = 40007    # 管理员重置密码：长度不足
ERR_EMAIL_CODE_INVALID = 40008    # 邮箱验证码：错误或已过期
ERR_EMAIL_CODE_TOO_FREQUENT = 40009  # 邮箱验证码：获取过于频繁（重发间隔 / 每小时上限）
ERR_PASSWORD_NOT_SET = 40010      # 该账号未设置密码（验证码登录建的号），请改用验证码登录
ERR_EMAIL_EXISTS = 40011          # 邮箱已被其它账号占用
ERR_EMAIL_SEND_FAILED = 40012     # 验证码邮件发送失败（SMTP 未配置或发信被拒）
ERR_ACCOUNT_INVALID = 40013       # 注册/改账号：账号名格式不合规（长度或字符集）
ERR_IDENTIFIER_CONFLICT = 40014   # 该账号名或邮箱已被占用（两者共享同一命名空间）
ERR_LOGIN_AMBIGUOUS = 40901       # 登录标识在库中命中多条（账号名与邮箱撞车，属数据异常）
ERR_EMAIL_NOT_BOUND = 40015       # 该账号还没绑定邮箱（无法走邮件重置密码这条自助通道）
ERR_FORBIDDEN = 40300           # 需要管理员权限
ERR_INVALID_ICON = 40016        # 竞品图标上传：格式不合法 / 超限 / 为空
ERR_ANNOUNCEMENT_INVALID = 40017  # 平台公告：内容为空

# 前端据此判断是否清除 token 并跳登录页
AUTH_ERROR_CODES = {
    ERR_BAD_CREDENTIALS,
    ERR_TOKEN_INVALID,
    ERR_TOKEN_USER_GONE,
    ERR_ACCOUNT_DISABLED,
}

# 通用 HTTP 状态码 → 中文提示（仅当后端没给自定义文案时兜底，覆盖 "Not Found" 这类英文默认）
# 标准：每条都同时说明「为什么」和「该怎么做」，避免用户看到后仍不知下一步。
HTTP_STATUS_MESSAGES: dict[int, str] = {
    400: "请求参数有误，请检查填写内容后重试",
    401: "未登录或登录已过期，请重新登录",
    403: "没有权限执行此操作，请检查账号权限",
    404: "请求的资源不存在或已被删除，请刷新页面后重试",
    405: "请求方式不被允许，请刷新页面后重试",
    409: "资源冲突，请检查后重试",
    422: "请求参数校验失败，请检查填写内容",
    429: "请求过于频繁，请稍后再试",
    500: "服务器内部错误，请稍后再试",
    502: "网关错误，请稍后再试",
    503: "服务暂时不可用，请稍后再试",
}

# Pydantic 常见英文校验信息 → 中文（让 422 提示不再是一串英文）
_PYDANTIC_MSG_ZH: dict[str, str] = {
    "Input should be a valid integer": "应为整数",
    "Input should be a valid number": "应为数字",
    "Input should be a valid string": "应为文本",
    "Input should be a valid boolean": "应为布尔值",
    "Input should be a valid email": "邮箱格式不正确",
    "Input should be a valid date": "应为日期",
    "Input should be a valid datetime": "应为日期时间",
    "Field required": "为必填项",
    "String should match pattern": "格式不正确",
    "String too short": "内容过短",
    "String too long": "内容过长",
}


class BusinessError(Exception):
    """业务异常：携带业务码、提示文案、以及对应的 HTTP 状态码。"""

    def __init__(self, code: int, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _envelope(code: int, message: str) -> dict:
    """统一的错误响应壳，与前端 request.ts 约定对齐：{code, message, data}。"""
    return {"code": code, "message": message, "data": None}


def register_exception_handlers(app: FastAPI) -> None:
    """把三类异常都收敛成 {code, message, data} 响应壳。"""

    # 1) 我们自定义的 BusinessError：直接用它的 code / message
    @app.exception_handler(BusinessError)
    async def handle_business_error(_: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.http_status,
            content=_envelope(exc.code, exc.message),
        )

    # 2) FastAPI 原生的 HTTPException：把状态码映射成业务码（状态码 * 100），文案用中文映射兜底
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException):
        code = exc.status_code * 100  # 400 -> 40000, 404 -> 40400 ...
        # 优先用我们自定义的 BusinessError（但它走上面第 1 个处理器）；
        # 这里只剩原生 HTTPException，其 detail 多为英文默认，用中文映射覆盖
        message = HTTP_STATUS_MESSAGES.get(exc.status_code, str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, message),
        )

    # 3) 参数校验失败（Pydantic 抛出 422）：收敛成 42200，并翻成中文
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else None
        msg = "请求参数校验失败"
        if first:
            # 去掉 path/query/body 这类位置词，只留字段名，提示更干净
            loc_parts = [
                str(p)
                for p in first.get("loc", [])
                if p not in ("path", "query", "body")
            ]
            loc = ".".join(loc_parts)
            reason = _PYDANTIC_MSG_ZH.get(first.get("msg", ""), first.get("msg", "参数错误"))
            msg = f"{loc}：{reason}" if loc else reason
        return JSONResponse(
            status_code=422,
            content=_envelope(42200, msg),
        )
