from lilac import Lilac, Request, Response, HTTPError


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
