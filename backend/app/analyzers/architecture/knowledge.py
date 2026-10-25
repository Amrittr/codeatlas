"""What known packages and naming conventions say about a component's role.

Keys are import names: the npm package name for JS/TS, or the top-level module name for
Python (which can differ from the PyPI name; see ``PYPI_TO_MODULE``).
"""

from __future__ import annotations

# role → human label shown in the UI
ROLES: dict[str, str] = {
    "frontend": "Frontend / UI",
    "api": "API & routes",
    "backend": "Backend server",
    "service": "Business logic",
    "data": "Data access",
    "auth": "Authentication",
    "jobs": "Background jobs",
    "shared": "Shared library",
    "tests": "Tests",
    "config": "Configuration",
    "module": "Module",
}

# package → (role, framework display name). These are role signals, not external services.
ROLE_PACKAGES: dict[str, tuple[str, str]] = {
    # frontend (JS)
    "react": ("frontend", "React"), "react-dom": ("frontend", "React"), "next": ("frontend", "Next.js"),
    "vue": ("frontend", "Vue"), "nuxt": ("frontend", "Nuxt"), "svelte": ("frontend", "Svelte"),
    "@sveltejs/kit": ("frontend", "SvelteKit"), "@angular/core": ("frontend", "Angular"),
    "solid-js": ("frontend", "Solid"), "preact": ("frontend", "Preact"), "astro": ("frontend", "Astro"),
    "react-native": ("frontend", "React Native"), "expo": ("frontend", "Expo"),
    "@remix-run/react": ("frontend", "Remix"), "lit": ("frontend", "Lit"),
    "react-router": ("frontend", "React Router"), "react-router-dom": ("frontend", "React Router"),
    # backend / API (JS)
    "express": ("api", "Express"), "fastify": ("api", "Fastify"), "koa": ("api", "Koa"),
    "@nestjs/core": ("api", "NestJS"), "@nestjs/common": ("api", "NestJS"), "@hapi/hapi": ("api", "hapi"),
    "hono": ("api", "Hono"), "restify": ("api", "Restify"), "@trpc/server": ("api", "tRPC"),
    "apollo-server": ("api", "Apollo Server"), "@apollo/server": ("api", "Apollo Server"),
    "graphql-yoga": ("api", "GraphQL Yoga"), "socket.io": ("api", "Socket.IO"), "ws": ("api", "WebSocket server"),
    # backend / API (Python)
    "flask": ("api", "Flask"), "fastapi": ("api", "FastAPI"), "django": ("api", "Django"),
    "starlette": ("api", "Starlette"), "tornado": ("api", "Tornado"), "aiohttp": ("api", "aiohttp"),
    "sanic": ("api", "Sanic"), "bottle": ("api", "Bottle"), "pyramid": ("api", "Pyramid"),
    "falcon": ("api", "Falcon"), "rest_framework": ("api", "Django REST framework"), "litestar": ("api", "Litestar"),
    # data access
    "@prisma/client": ("data", "Prisma"), "prisma": ("data", "Prisma"), "mongoose": ("data", "Mongoose"),
    "sequelize": ("data", "Sequelize"), "typeorm": ("data", "TypeORM"), "knex": ("data", "Knex"),
    "drizzle-orm": ("data", "Drizzle"), "objection": ("data", "Objection"), "mikro-orm": ("data", "MikroORM"),
    "sqlalchemy": ("data", "SQLAlchemy"), "sqlmodel": ("data", "SQLModel"), "peewee": ("data", "Peewee"),
    "tortoise": ("data", "Tortoise ORM"), "alembic": ("data", "Alembic"), "pony": ("data", "Pony ORM"),
    "mongoengine": ("data", "MongoEngine"), "beanie": ("data", "Beanie"), "odmantic": ("data", "ODMantic"),
    # auth
    "passport": ("auth", "Passport"), "jsonwebtoken": ("auth", "jsonwebtoken"), "jose": ("auth", "jose"),
    "bcrypt": ("auth", "bcrypt"), "bcryptjs": ("auth", "bcrypt"), "argon2": ("auth", "Argon2"),
    "next-auth": ("auth", "NextAuth"), "@auth/core": ("auth", "Auth.js"), "express-session": ("auth", "express-session"),
    "@clerk/nextjs": ("auth", "Clerk"), "@clerk/clerk-sdk-node": ("auth", "Clerk"), "lucia": ("auth", "Lucia"),
    "jwt": ("auth", "PyJWT"), "passlib": ("auth", "passlib"), "authlib": ("auth", "Authlib"),
    "flask_login": ("auth", "Flask-Login"), "flask_jwt_extended": ("auth", "Flask-JWT-Extended"),
    "itsdangerous": ("auth", "itsdangerous"), "oauthlib": ("auth", "OAuthLib"),
    # background jobs
    "bull": ("jobs", "Bull"), "bullmq": ("jobs", "BullMQ"), "agenda": ("jobs", "Agenda"), "node-cron": ("jobs", "node-cron"),
    "bee-queue": ("jobs", "Bee-Queue"), "celery": ("jobs", "Celery"), "rq": ("jobs", "RQ"), "dramatiq": ("jobs", "Dramatiq"),
    "apscheduler": ("jobs", "APScheduler"), "huey": ("jobs", "Huey"), "arq": ("jobs", "arq"),
    # tests
    "jest": ("tests", "Jest"), "vitest": ("tests", "Vitest"), "mocha": ("tests", "Mocha"), "chai": ("tests", "Chai"),
    "@testing-library/react": ("tests", "Testing Library"), "@playwright/test": ("tests", "Playwright"),
    "cypress": ("tests", "Cypress"), "supertest": ("tests", "supertest"), "pytest": ("tests", "pytest"),
    "unittest": ("tests", "unittest"),
}

# Python dotted modules that carry a role (checked by prefix).
ROLE_MODULE_PREFIXES: dict[str, tuple[str, str]] = {
    "fastapi.testclient": ("tests", "FastAPI TestClient"),
    "starlette.testclient": ("tests", "Starlette TestClient"),
    "django.test": ("tests", "Django test"),
    "flask.testing": ("tests", "Flask testing"),
    "django.db": ("data", "Django ORM"),
    "django.contrib.auth": ("auth", "Django auth"),
    "django.urls": ("api", "Django"),
    "django.http": ("api", "Django"),
    "django.views": ("api", "Django"),
}

# package → (external service category, service display name)
EXTERNAL_SERVICES: dict[str, tuple[str, str]] = {
    "pg": ("database", "PostgreSQL"), "postgres": ("database", "PostgreSQL"), "mysql": ("database", "MySQL"),
    "mysql2": ("database", "MySQL"), "sqlite3": ("database", "SQLite"), "better-sqlite3": ("database", "SQLite"),
    "mongodb": ("database", "MongoDB"), "mongoose": ("database", "MongoDB"), "@prisma/client": ("database", "Database (Prisma)"),
    "psycopg2": ("database", "PostgreSQL"), "psycopg": ("database", "PostgreSQL"), "asyncpg": ("database", "PostgreSQL"),
    "pymysql": ("database", "MySQL"), "MySQLdb": ("database", "MySQL"),
    "pymongo": ("database", "MongoDB"), "motor": ("database", "MongoDB"), "mongoengine": ("database", "MongoDB"),
    "redis": ("cache", "Redis"), "ioredis": ("cache", "Redis"), "memcached": ("cache", "Memcached"),
    "@supabase/supabase-js": ("database", "Supabase"), "supabase": ("database", "Supabase"),
    "firebase": ("cloud", "Firebase"), "firebase-admin": ("cloud", "Firebase"), "firebase_admin": ("cloud", "Firebase"),
    "stripe": ("payments", "Stripe"), "@stripe/stripe-js": ("payments", "Stripe"), "razorpay": ("payments", "Razorpay"),
    "braintree": ("payments", "Braintree"), "paypalrestsdk": ("payments", "PayPal"), "@paypal/checkout-server-sdk": ("payments", "PayPal"),
    "aws-sdk": ("cloud", "AWS"), "boto3": ("cloud", "AWS"), "botocore": ("cloud", "AWS"),
    "@google-cloud/storage": ("cloud", "Google Cloud"), "google": ("cloud", "Google Cloud"),
    "@azure/storage-blob": ("cloud", "Azure"), "azure": ("cloud", "Azure"),
    "openai": ("ai", "OpenAI"), "@anthropic-ai/sdk": ("ai", "Anthropic"), "anthropic": ("ai", "Anthropic"),
    "@google/generative-ai": ("ai", "Google Gemini"), "langchain": ("ai", "LangChain"), "cohere": ("ai", "Cohere"),
    "nodemailer": ("email", "Email (SMTP)"), "@sendgrid/mail": ("email", "SendGrid"), "sendgrid": ("email", "SendGrid"),
    "smtplib": ("email", "Email (SMTP)"), "resend": ("email", "Resend"), "mailgun": ("email", "Mailgun"), "postmark": ("email", "Postmark"),
    "twilio": ("messaging", "Twilio"), "kafkajs": ("messaging", "Kafka"), "kafka": ("messaging", "Kafka"),
    "amqplib": ("messaging", "RabbitMQ"), "pika": ("messaging", "RabbitMQ"), "@slack/web-api": ("messaging", "Slack"),
    "slack_sdk": ("messaging", "Slack"), "pusher": ("messaging", "Pusher"),
    "axios": ("http", "External HTTP APIs"), "node-fetch": ("http", "External HTTP APIs"), "got": ("http", "External HTTP APIs"),
    "ky": ("http", "External HTTP APIs"), "requests": ("http", "External HTTP APIs"), "httpx": ("http", "External HTTP APIs"),
    "urllib3": ("http", "External HTTP APIs"),
}
# Scoped npm packages that map as a whole family.
EXTERNAL_SCOPES: dict[str, tuple[str, str]] = {
    "@aws-sdk": ("cloud", "AWS"), "@google-cloud": ("cloud", "Google Cloud"), "@azure": ("cloud", "Azure"),
    "@sendgrid": ("email", "SendGrid"),
}

EXTERNAL_CATEGORIES: dict[str, str] = {
    "database": "Databases",
    "cache": "Cache",
    "payments": "Payments",
    "cloud": "Cloud services",
    "ai": "AI services",
    "email": "Email",
    "messaging": "Messaging",
    "http": "External HTTP APIs",
}

# Folder-name conventions: weak evidence. The UI shows these as low confidence on their own.
FOLDER_ROLES: dict[str, str] = {
    "components": "frontend", "pages": "frontend", "views": "frontend", "ui": "frontend", "screens": "frontend",
    "hooks": "frontend", "styles": "frontend", "layouts": "frontend", "public": "frontend", "client": "frontend",
    "frontend": "frontend", "web": "frontend", "app": "frontend",
    "routes": "api", "api": "api", "controllers": "api", "handlers": "api", "endpoints": "api", "routers": "api",
    "resolvers": "api", "server": "backend", "backend": "backend", "middleware": "backend", "middlewares": "backend",
    "services": "service", "domain": "service", "usecases": "service", "core": "service",
    "models": "data", "db": "data", "database": "data", "repositories": "data", "repository": "data",
    "migrations": "data", "entities": "data", "schemas": "data", "dao": "data", "prisma": "data",
    "auth": "auth", "authentication": "auth", "security": "auth", "login": "auth", "permissions": "auth",
    "workers": "jobs", "worker": "jobs", "jobs": "jobs", "tasks": "jobs", "queues": "jobs", "cron": "jobs", "scheduler": "jobs",
    "utils": "shared", "lib": "shared", "libs": "shared", "common": "shared", "shared": "shared", "helpers": "shared",
    "packages": "shared", "types": "shared",
    "tests": "tests", "test": "tests", "__tests__": "tests", "spec": "tests", "e2e": "tests",
    "config": "config", "settings": "config", "conf": "config",
}

# Python file-name conventions (weak evidence): models.py, views.py, urls.py, tasks.py …
PY_FILE_ROLES: dict[str, str] = {
    "models.py": "data", "db.py": "data", "database.py": "data", "repositories.py": "data", "schemas.py": "data",
    "views.py": "api", "urls.py": "api", "routes.py": "api", "api.py": "api", "endpoints.py": "api", "serializers.py": "api",
    "tasks.py": "jobs", "worker.py": "jobs", "celery.py": "jobs",
    "auth.py": "auth", "security.py": "auth", "permissions.py": "auth",
    "settings.py": "config", "config.py": "config",
}

FRONTEND_EXTENSIONS = {".jsx", ".tsx", ".vue", ".svelte", ".astro", ".html", ".css", ".scss", ".sass", ".less"}

# PyPI distribution name → import module name, where they differ.
PYPI_TO_MODULE: dict[str, str] = {
    "pyjwt": "jwt", "python-jose": "jose", "flask-login": "flask_login", "flask-jwt-extended": "flask_jwt_extended",
    "psycopg2-binary": "psycopg2", "psycopg-binary": "psycopg", "djangorestframework": "rest_framework",
    "firebase-admin": "firebase_admin", "slack-sdk": "slack_sdk", "mysqlclient": "MySQLdb", "beautifulsoup4": "bs4",
    "pyyaml": "yaml", "pillow": "PIL", "scikit-learn": "sklearn", "python-dotenv": "dotenv",
}

NODE_BUILTINS = {
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console", "constants", "crypto", "dgram",
    "diagnostics_channel", "dns", "domain", "events", "fs", "http", "http2", "https", "inspector", "module", "net",
    "os", "path", "perf_hooks", "process", "punycode", "querystring", "readline", "repl", "stream", "string_decoder",
    "sys", "timers", "tls", "trace_events", "tty", "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib", "test",
}


def external_service(package: str) -> tuple[str, str] | None:
    if package in EXTERNAL_SERVICES:
        return EXTERNAL_SERVICES[package]
    scope = package.split("/", 1)[0]
    return EXTERNAL_SCOPES.get(scope)


def role_signal(package: str, full_module: str = "") -> tuple[str, str] | None:
    for prefix, signal in ROLE_MODULE_PREFIXES.items():
        if full_module == prefix or full_module.startswith(prefix + "."):
            return signal
    return ROLE_PACKAGES.get(package)
