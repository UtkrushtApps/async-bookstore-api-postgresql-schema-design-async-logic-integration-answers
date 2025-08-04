from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from typing import List, Optional
from db.db import db
from pydantic import BaseModel
from datetime import date

app = FastAPI()


# ---- Pydantic Schemas (request/response models) ----
class AuthorIn(BaseModel):
    name: str
    bio: Optional[str] = None

class AuthorOut(AuthorIn):
    id: int

class CategoryIn(BaseModel):
    name: str

class CategoryOut(CategoryIn):
    id: int

class CategoryLite(BaseModel):
    id: int
    name: str

class BookIn(BaseModel):
    title: str
    description: str
    price: float
    author_id: int
    published_date: date
    category_ids: List[int]

class BookOut(BaseModel):
    id: int
    title: str
    description: str
    price: float
    author_id: int
    author_name: str
    published_date: date
    categories: List[CategoryLite]

class BookUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    author_id: Optional[int] = None
    published_date: Optional[date] = None
    category_ids: Optional[List[int]] = None

class UserIn(BaseModel):
    username: str
    email: str

class UserOut(BaseModel):
    id: int
    username: str
    email: str

# ------------ DB Startup/Shutdown ------------
@app.on_event("startup")
async def startup():
    await db.connect()

@app.on_event("shutdown")
async def shutdown():
    await db.disconnect()


# ------------ Authors Endpoints ------------
@app.post("/authors/", response_model=AuthorOut)
async def create_author(author: AuthorIn):
    try:
        return await db.create_author(author.name, author.bio)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/authors/{author_id}", response_model=AuthorOut)
async def get_author(author_id: int):
    author = await db.get_author_by_id(author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    return author

@app.get("/authors/", response_model=List[AuthorOut])
async def list_authors():
    return await db.list_authors()

# ------------ Categories Endpoints ------------
@app.post("/categories/", response_model=CategoryOut)
async def create_category(category: CategoryIn):
    try:
        return await db.create_category(category.name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/categories/{category_id}", response_model=CategoryOut)
async def get_category(category_id: int):
    cat = await db.get_category_by_id(category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    return cat

@app.get("/categories/", response_model=List[CategoryOut])
async def list_categories():
    return await db.list_categories()

# ------------ Books CRUD ------------
@app.post("/books/", response_model=BookOut)
async def create_book(book: BookIn):
    # Validate author and categories
    if not await db.get_author_by_id(book.author_id):
        raise HTTPException(status_code=400, detail="Invalid author_id")
    for cid in book.category_ids:
        if not await db.get_category_by_id(cid):
            raise HTTPException(status_code=400, detail=f"Invalid category_id {cid}")
    row = await db.create_book(
        book.title, book.description, book.price,
        book.author_id, book.published_date, book.category_ids
    )
    # Get full book (including categories)
    return await db.get_book_by_id(row['id'])

@app.get("/books/{book_id}", response_model=BookOut)
async def get_book(book_id: int):
    book = await db.get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book

@app.put("/books/{book_id}", response_model=BookOut)
async def update_book(book_id: int, book_update: BookUpdateIn):
    if book_update.author_id and not await db.get_author_by_id(book_update.author_id):
        raise HTTPException(status_code=400, detail="Invalid author_id")
    if book_update.category_ids:
        for cid in book_update.category_ids:
            if not await db.get_category_by_id(cid):
                raise HTTPException(status_code=400, detail=f"Invalid category_id {cid}")
    b = await db.update_book(
        book_id,
        book_update.title,
        book_update.description,
        book_update.price,
        book_update.author_id,
        book_update.published_date,
        book_update.category_ids
    )
    if not b:
        raise HTTPException(status_code=404, detail="Book not found")
    # Return full book with categories
    return await db.get_book_by_id(book_id)

@app.delete("/books/{book_id}")
async def delete_book(book_id: int):
    ok = await db.delete_book(book_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"success": True}

# ------------ Search and Listing ------------
@app.get("/books/", response_model=List[BookOut])
async def list_books(
    author_id: Optional[int] = None,
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=100, gt=0),
    offset: int = Query(0, ge=0),
    user_id: Optional[int] = Query(None),
    background_tasks: BackgroundTasks = None
):
    """
    List books, optionally filter by author/category or search phrase.
    Log all search requests (including params) via background task to logs table.
    """
    books = await db.list_books(
        author_id=author_id, category_id=category_id, search=search,
        limit=limit, offset=offset
    )
    if background_tasks is not None:
        details = {"author_id": author_id, "category_id": category_id, "search": search, "limit": limit, "offset": offset}
        background_tasks.add_task(db.log_action, user_id, "search_books", details)
    return books

# ------------ Users CRUD ------------
@app.post("/users/", response_model=UserOut)
async def create_user(user: UserIn):
    try:
        return await db.create_user(user.username, user.email)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int):
    u = await db.get_user_by_id(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u
