from pydantic import BaseModel


class Message(BaseModel):
    detail: str


class Paginated(BaseModel):
    total: int
    page: int
    size: int
    items: list
