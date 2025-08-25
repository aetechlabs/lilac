import re
import json
from typing import Awaitable, Callable, Dict, Any, List, Optional, Tuple

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable [[Dict[str, Any]], Awaitable[None]]
Handler = Callable[..., Awaitable['Response']]
Middleware = Callable[[Callable[[Scope, Receive, Send], Awaitable[None]]],
                    Callable[[Scope, Receive, Send], Awaitable[None]]]


class Request:
    def __init__(self, scope:Scope, receive:Receive):
        assert scope['type'] == 'http'
        self.scope = scope
        self._receive = receive
        self._body: Optional[bytes] = None

    @property
    def method(self) -> str:
        return self.scope['method'].upper()

    @property
    def path(self) -> str:
        return self.scope['path']
    
    @property
    def headers(self) -> str:
        return {k.decode().lower(): v.decode() for k, v in self.scope['Headers']}
    
    @property
    def query_params(self) -> Dict[str, str]:
        raw = self.scope.get('query_string', b"") or b""
        qs = raw.decode()
        params = {}
        if qs:
            for pair in qs.split("&"):
                if not pair:
                    continue
                if "=" in pair:
                    k, v = pair.split("=", 1)
                else:
                    k, v = pair, ""
                params[k] = v
        return params
    
    async def body(self) -> bytes:
        if self._body is None:
            chunks = []
            more = True

            while more:
                msg = await self._receive()
                if msg['type'] == "http.request":
                    chunks.append(msg.get("body", b""))
                    more = msg.get("more_body", False)

                else:
                    more = False
            self._body = b"".join(chunks)
        return self._body

    async def json(self) -> Any:
        b = await self.body()
        if not b:
            return None
        return json.loads(b.decode())
    
class Response:
    def __init__(self,
                 content: bytes | str | dict | list | None = b"",
                 status: int = 200,
                 headers: Optional[List[Tuple[str, str]]] = None,
                 media_type: Optional[str] = None
                 ):
        self.status = status
        self.headers = headers or []
        self.body_bytes: bytes

        if isinstance(content, (dict, list)):
            self.body_bytes = json.dumps(content).encode()
            self.headers.append(("content-type", "application/json; charset=utf-8"))
        elif isinstance(content, str):
            self.body_bytes = content.encode()
            self.headers.append(("content-type", media_type or "text/plain; charset=utf-8"))
        elif isinstance(content, (bytes, bytearray)):
            self.body_bytes = bytes(content)
            if media_type:
                self.headers.append(("content-type", media_type))
        elif content is None:
            self.body_bytes = b""
            if media_type:
                self.headers.append(("content-type", media_type))
        else:
            raise TypeError("Unsupported content type for Response")
        
    @classmethod
    def json(cls, data: Any, status: int = 200, headers: Optional[List[Tuple[str, str]]] = None):
        return cls(data, status=status, headers=headers or [])
    
class Route:
    def __init__(self, method: str, path: str, handler: Handler):
        self.method = method.upper()
        self.path = path
        self.param_names, self.regex = self._compile(path)
        self.handler = handler

    def _compile(self, path:str) -> Tuple[List[str], re.Pattern]:
        param_names: List[str] = []
        regex_str = "^"
        i = 0
        while i < len(path):
            if path[i] == "{":
                j = path.find("}", i)
                if j == -1:
                    raise ValueError("Unmatched '{' in route path")
                name = path[i+1:j]
                param_names.append(name)
                regex_str += r"(?P<" + name + r">[^/]+)"
                i = j + 1
            else:
                c = re.escape(path[i])
                regex_str += c
                i +=1

        regex_str += "$"
        return param_names, re.compile(regex_str)
    def matches(self, method: str, path: str) -> Optional[Dict[str, str]]:
        if method.upper() != self.method:
            return None
        m = self.regex.match(path)
        if not m:
            return None
        return m.groupdict()
    

class Router:
    def __init__(self):
        self.routes: List[Route] = []

    def add(self, method: str, path: str, handler: Handler):
        self.routes.append(Route(method, path, handler))

    def find(self, method: str, path: str) -> Tuple[Optional[Route], Dict[str, str]]:
        for r in self.routes:
            params = r.matches(method, path)
            if params is not None:
                return r, params
        return None, {}
    
class Lilac:
    def __init__(self):
        self.router = Router()
        self._middleware: List[Middleware] = []
    def route(self, method: str, path: str):
        def decorator(func:Handler):
            self.router.add(method, path, func)
            return func
        return decorator
    
    def get(self, path: str): return self.route("GET", path)
    def post(self, path: str): return self.route("POST", path)
    def put(self, path: str): return self.route("PUT", path)
    def patch(self, path: str): return self.route("PATCH", path)
    def delete(self, path: str): return self.route("DELETE", path)
    def use(self, mw: Middleware):
        self._middleware.append(mw)
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b"Not Found"})
            return
        
        async def endpoint(scope: Scope, receive: Receive, send: Send):
            req = Request(scope, receive)
            route, params = self.router.find(req.method, req.path)
            if route is None:
                resp = Response("Not Found", status=404)
            else:
                try:
                    resp = await route.handler(req, **params)
                    if not isinstance(resp, Response):
                        resp = Response(resp)
                except HTTPError as he:
                    resp = Response.json({"detail": he.detail}, status=he.status)
                except Exception as e:
                    resp = Response.json({"detail": "Internal Server Error"}, status=500)
            headers = [(k.encode(), v.encode()) for k, v in resp.headers]
            await send({"type": "http.response.start", "status": resp.status, "headers": headers})
            await send({"type": "http.response.body", "body": resp.body_bytes})
        app = endpoint
        for mw in reversed(self._middleware):
            app = mw(app)
        await app(scope, receive, send)

class HTTPError(Exception):
    def __init__(self, status: int, detail: str = ""):
        self.status = status
        self.detail = detail or f"HTTP {status}"
        super().__init__(self.detail)



app = Lilac()


def logger_middleware(next_app):
    async def _inner(scope, receive, send):
        if scope["type"] == "http":
            method = scope["method"]
            path = scope["path"]
            print(f"{method} {path}")
        return await next_app(scope, receive, send)
    return _inner


app.use(logger_middleware)


@app.get("/hello/{name}")
async def hello(req: Request, name: str):
    return Response.json({"message": f"Hello, {name}"})


@app.post("/echo")
async def echo(req: Request):
    data = await req.json()
    if not isinstance(data, dict):
        raise HTTPError(400, "Expected JSON object")
    return {"you_sent": data} 

@app.get("/health")
async def health(req: Request):
    return Response("ok")