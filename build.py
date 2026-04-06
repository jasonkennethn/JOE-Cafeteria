#!/usr/bin/env python
"""
JOE Cafeteria — Build Script
Handles: dependencies, migrations, static files, and user seeding.
"""
import os
import sys
import subprocess

# ── Django Setup ──────────────────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JOE_Cafeteria.settings")

def run(cmd, label):
    """Run a shell command, exit on failure."""
    print(f"\n{'─'*50}")
    print(f"  {label}")
    print(f"{'─'*50}")
    print(f"$ {cmd}\n")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"\n✗ FAILED: {label}")
        sys.exit(result.returncode)
    print(f"✓ {label}")

def seed_users():
    """Create all staff users defined in Info.md."""
    import django
    django.setup()
    from JOE.models import User

    USERS = [
        # Super Admin
        {
            "username": "admin",
            "email": "admin@joe.com",
            "password": "admin",
            "role": "Customer",
            "first_name": "Super",
            "last_name": "Admin",
            "is_superuser": True,
            "is_staff": True,
        },
        # Cashier
        {
            "username": "cashier",
            "email": "cashier@joe.com",
            "password": "Cafeteria@123",
            "role": "Cashier",
            "first_name": "JOE",
            "last_name": "Cashier",
        },
        # Kitchen Manager
        {
            "username": "kitchen",
            "email": "kitchen@joe.com",
            "password": "Cafeteria@123",
            "role": "Kitchen Manager",
            "first_name": "JOE",
            "last_name": "Kitchen",
        },
        # Serving Desk
        {
            "username": "serving",
            "email": "serving@joe.com",
            "password": "Cafeteria@123",
            "role": "Serving Desk",
            "first_name": "JOE",
            "last_name": "Serving",
        },
        # Cafeteria Manager
        {
            "username": "manager",
            "email": "manager@joe.com",
            "password": "Cafeteria@123",
            "role": "Cafeteria Manager",
            "first_name": "JOE",
            "last_name": "Manager",
        },
        # Cafeteria Owner
        {
            "username": "owner",
            "email": "owner@joe.com",
            "password": "Cafeteria@123",
            "role": "Cafeteria Owner",
            "first_name": "JOE",
            "last_name": "Owner",
        },
    ]

    print(f"\n{'─'*50}")
    print("  Seeding Users")
    print(f"{'─'*50}\n")

    for data in USERS:
        username = data["username"]
        if User.objects.filter(username=username).exists():
            print(f"  → {username:12s}  already exists, skipped")
            continue

        user = User(
            username=username,
            email=data["email"],
            role=data["role"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            is_superuser=data.get("is_superuser", False),
            is_staff=data.get("is_staff", False) or data.get("is_superuser", False),
        )
        user.set_password(data["password"])
        user.save()

        tag = "superuser" if data.get("is_superuser") else data["role"]
        print(f"  ✓ {username:12s}  ({data['email']})  [{tag}]")

    print(f"\n✓ Seeding Users")

# ── Main ──────────────────────────────────────────────────────
def main():
    print("\n╔══════════════════════════════════════════════════╗")
    print("║         JOE CAFETERIA — BUILD PROCESS           ║")
    print("╚══════════════════════════════════════════════════╝")

    py = sys.executable

    # 1. Install dependencies
    run(f"{py} -m pip install -r requirements.txt", "Installing Dependencies")

    # 2. Generate migrations
    run(f"{py} manage.py makemigrations JOE --noinput", "Making JOE Migrations")
    run(f"{py} manage.py makemigrations --noinput", "Making General Migrations")

    # 3. Apply migrations in correct order
    #    Since we use a custom User model in the JOE app, we MUST migrate JOE first
    #    so the database table is created before allauth data migrations query it.
    run(f"{py} manage.py migrate contenttypes --noinput", "Migrate: contenttypes")
    run(f"{py} manage.py migrate JOE --noinput",          "Migrate: JOE (Custom User Model)")
    run(f"{py} manage.py migrate auth --noinput",         "Migrate: auth")
    run(f"{py} manage.py migrate --noinput",              "Migrate: remaining apps")

    # 4. Collect static files
    run(f"{py} manage.py collectstatic --noinput", "Collecting Static Files")

    # 5. Seed users
    seed_users()

    print("\n╔══════════════════════════════════════════════════╗")
    print("║            BUILD COMPLETE ✓                     ║")
    print("╚══════════════════════════════════════════════════╝\n")

if __name__ == "__main__":
    main()
