import asyncpg
from fastapi import FastAPI
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/bookstore"

class Database:
    def __init__(self, dsn):
        self._dsn = dsn
        self._pool = None

    async def connect(self):
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=10)

    async def disconnect(self):
        if self._pool:
            await self._pool.close()

    @asynccontextmanager
    async def acquire(self):
        async with self._pool.acquire() as conn:
            yield conn

    # -- AUTHORS --
    async def get_author_by_id(self, author_id: int) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow("SELECT id, name, bio FROM authors WHERE id=$1", author_id)
            return dict(row) if row else None

    async def create_author(self, name: str, bio: Optional[str] = None) -> dict:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO authors(name, bio) VALUES ($1, $2) RETURNING id, name, bio", name, bio
            )
            return dict(row)

    async def list_authors(self) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch("SELECT id, name, bio FROM authors ORDER BY name")
            return [dict(r) for r in rows]

    # -- CATEGORIES --
    async def get_category_by_id(self, category_id: int) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow("SELECT id, name FROM categories WHERE id=$1", category_id)
            return dict(row) if row else None

    async def create_category(self, name: str) -> dict:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO categories(name) VALUES ($1) RETURNING id, name", name
            )
            return dict(row)

    async def list_categories(self) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch("SELECT id, name FROM categories ORDER BY name")
            return [dict(r) for r in rows]

    # -- BOOKS --
    async def get_book_by_id(self, book_id: int) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT b.id, b.title, b.description, b.price, b.author_id, b.published_date, a.name as author_name
                FROM books b
                JOIN authors a ON b.author_id = a.id
                WHERE b.id=$1
                """, book_id
            )
            if not row:
                return None
            # Now, fetch categories
            cat_rows = await conn.fetch(
                "SELECT c.id, c.name FROM categories c JOIN book_categories bc ON c.id = bc.category_id WHERE bc.book_id = $1",
                book_id
            )
            data = dict(row)
            data['categories'] = [dict(cr) for cr in cat_rows]
            return data

    async def create_book(self, title: str, description: str, price: float, author_id: int, published_date, category_ids: List[int]) -> dict:
        async with self.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "INSERT INTO books(title, description, price, author_id, published_date) VALUES ($1, $2, $3, $4, $5) RETURNING id, title, description, price, author_id, published_date",
                    title, description, price, author_id, published_date
                )
                book_id = row['id']
                # Attach categories
                for cid in category_ids:
                    await conn.execute("INSERT INTO book_categories(book_id, category_id) VALUES ($1, $2)", book_id, cid)
            return dict(row)

    async def update_book(self, book_id: int, title: Optional[str], description: Optional[str], price: Optional[float], author_id: Optional[int], published_date: Optional[str], category_ids: Optional[List[int]]) -> Optional[dict]:
        async with self.acquire() as conn:
            async with conn.transaction():
                # Update book core
                up_fields = []
                params = []
                idx = 1
                if title is not None:
                    up_fields.append(f'title=${idx}')
                    params.append(title)
                    idx += 1
                if description is not None:
                    up_fields.append(f'description=${idx}')
                    params.append(description)
                    idx += 1
                if price is not None:
                    up_fields.append(f'price=${idx}')
                    params.append(price)
                    idx += 1
                if author_id is not None:
                    up_fields.append(f'author_id=${idx}')
                    params.append(author_id)
                    idx += 1
                if published_date is not None:
                    up_fields.append(f'published_date=${idx}')
                    params.append(published_date)
                    idx += 1
                set_part = ", ".join(up_fields)
                if set_part:
                    q = f"UPDATE books SET {set_part} WHERE id=${idx}"
                    params.append(book_id)
                    await conn.execute(q, *params)
                # Update categories if needed
                if category_ids is not None:
                    await conn.execute("DELETE FROM book_categories WHERE book_id=$1", book_id)
                    for cid in category_ids:
                        await conn.execute("INSERT INTO book_categories(book_id, category_id) VALUES ($1, $2)", book_id, cid)
                row = await conn.fetchrow("SELECT * FROM books WHERE id=$1", book_id)
                return dict(row) if row else None

    async def delete_book(self, book_id: int) -> bool:
        async with self.acquire() as conn:
            result = await conn.execute("DELETE FROM books WHERE id=$1", book_id)
            return result[-1] != '0'  # Returns True if row deleted

    async def list_books(self, *, author_id: Optional[int] = None, category_id: Optional[int] = None, search: Optional[str] = None, limit=50, offset=0) -> List[dict]:
        async with self.acquire() as conn:
            # Build query
            query = [
                "SELECT b.id, b.title, b.description, b.price, b.author_id, b.published_date, a.name as author_name"
                " FROM books b JOIN authors a ON b.author_id = a.id"
            ]
            wheres = []
            params = []
            idx = 1
            if author_id is not None:
                wheres.append(f"b.author_id=${idx}")
                params.append(author_id)
                idx += 1
            if category_id is not None:
                query.append("JOIN book_categories bc ON b.id = bc.book_id")
                wheres.append(f"bc.category_id=${idx}")
                params.append(category_id)
                idx += 1
            if search:
                # Use full-text search on title+description
                wheres.append(f"to_tsvector('english', b.title || ' ' || b.description) @@ plainto_tsquery('english', ${idx})")
                params.append(search)
                idx += 1
            if wheres:
                query.append("WHERE " + " AND ".join(wheres))
            query.append(f"ORDER BY b.title LIMIT {limit} OFFSET {offset}")
            sql = " ".join(query)
            rows = await conn.fetch(sql, *params)
            # get categories for all books
            book_ids = [r['id'] for r in rows]
            all_cats = []
            if book_ids:
                cats = await conn.fetch(
                    f"SELECT bc.book_id, c.id, c.name FROM book_categories bc JOIN categories c ON bc.category_id = c.id WHERE bc.book_id = ANY($1::int[])",
                    book_ids
                )
                d = {}
                for cr in cats:
                    bkid = cr['book_id']
                    if bkid not in d:
                        d[bkid] = []
                    d[bkid].append({'id': cr['id'], 'name': cr['name']})
                for row in rows:
                    book_id = row['id']
                    row = dict(row)
                    row['categories'] = d.get(book_id, [])
                    all_cats.append(row)
            return all_cats

    # -- USERS --
    async def get_user_by_id(self, user_id: int) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow("SELECT id, username, email FROM users WHERE id=$1", user_id)
            return dict(row) if row else None

    async def create_user(self, username: str, email: str) -> dict:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO users(username, email) VALUES ($1, $2) RETURNING id, username, email", username, email
            )
            return dict(row)

    # -- LOGGING --
    async def log_action(self, user_id: Optional[int], action: str, details: dict) -> None:
        async with self.acquire() as conn:
            await conn.execute(
                "INSERT INTO logs(user_id, action, details) VALUES ($1, $2, $3)",
                user_id, action, details
            )

db = Database(DATABASE_URL)
