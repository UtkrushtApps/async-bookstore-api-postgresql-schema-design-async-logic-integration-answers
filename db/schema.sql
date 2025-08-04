-- Bookstore Normalized PostgreSQL Schema
CREATE TABLE authors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    bio TEXT,
    UNIQUE(name)
);

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE books (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    price NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    author_id INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    published_date DATE NOT NULL
);

CREATE TABLE book_categories (
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY(book_id, category_id)
);

CREATE INDEX idx_books_author_id ON books(author_id);
CREATE INDEX idx_book_categories_category_id ON book_categories(category_id);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    details JSONB,
    created_at TIMESTAMP DEFAULT now()
);

-- For fast search by title and author (showcase index usage)
CREATE INDEX idx_books_title ON books USING gin (to_tsvector('english', title));

-- For fast general search
CREATE INDEX idx_books_title_desc ON books USING gin (to_tsvector('english', title || ' ' || description));
