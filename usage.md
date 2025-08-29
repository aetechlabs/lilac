@app.get("/users/{id}")
def get_user(id: str, active: str = "false"):
    return {"id": id, "active": active}