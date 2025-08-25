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

