from lilac import *

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