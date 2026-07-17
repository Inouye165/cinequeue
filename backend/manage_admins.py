import argparse
import sys
import os
import getpass

# Add current directory to python path to resolve app.* imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import WATCHLIST_BACKEND, GOOGLE_CLOUD_PROJECT, ADMIN_USERNAME
from app.services.admin_auth import hash_password, generate_salt

def get_repo():
    if WATCHLIST_BACKEND == "firestore":
        from app.firestore_repo import FirestoreWatchlistRepository
        return FirestoreWatchlistRepository(project=GOOGLE_CLOUD_PROJECT or None)
    else:
        from app.sqlite_repo import SqliteWatchlistRepository
        return SqliteWatchlistRepository()

def main():
    parser = argparse.ArgumentParser(description="Cinequeue Administrator Accounts Manager CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List current administrators")
    group.add_argument("--add", metavar="USERNAME", help="Add an administrator account")
    group.add_argument("--remove", metavar="USERNAME", help="Remove an administrator account")
    
    args = parser.parse_args()
    
    try:
        repo = get_repo()
    except Exception as e:
        print(f"Error: Failed to initialize watchlist repository: {e}", file=sys.stderr)
        sys.exit(1)
        
    datastore_name = f"Firestore (project={GOOGLE_CLOUD_PROJECT})" if WATCHLIST_BACKEND == "firestore" else "SQLite (local database)"
    
    if args.list:
        print(f"Listing administrators from {datastore_name}...")
        try:
            admins = repo.list_admin_users()
            if not admins:
                print("No administrators found in the database.")
            else:
                for idx, admin in enumerate(admins, start=1):
                    print(f"  {idx}. {admin}")
            print(f"\nConfiguration baseline ADMIN_USERNAME: '{ADMIN_USERNAME}'")
        except Exception as e:
            print(f"Error: Failed to list administrators: {e}", file=sys.stderr)
            sys.exit(1)
            
    elif args.add:
        username = args.add.strip().lower()
        if not username:
            print("Error: Username cannot be empty.", file=sys.stderr)
            sys.exit(1)
            
        print(f"Adding administrator '{username}' to {datastore_name}...")
        try:
            # Check if user already exists
            existing = repo.get_admin_user(username)
            if existing:
                confirm = input(f"Administrator '{username}' already exists. Overwrite password? [y/N]: ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("Operation cancelled.")
                    sys.exit(0)
            
            # Prompt for password securely
            password = getpass.getpass("Enter administrator password: ")
            if not password:
                print("Error: Password cannot be empty.", file=sys.stderr)
                sys.exit(1)
                
            password_confirm = getpass.getpass("Confirm administrator password: ")
            if password != password_confirm:
                print("Error: Passwords do not match.", file=sys.stderr)
                sys.exit(1)
                
            salt = generate_salt()
            pwd_hash = hash_password(password, salt)
            repo.create_admin_user(username, pwd_hash, salt)
            print(f"Successfully added/updated administrator '{username}' in {datastore_name}.")
        except Exception as e:
            print(f"Error: Failed to add administrator: {e}", file=sys.stderr)
            sys.exit(1)
            
    elif args.remove:
        username = args.remove.strip().lower()
        if not username:
            print("Error: Username cannot be empty.", file=sys.stderr)
            sys.exit(1)
            
        print(f"Preparing to remove administrator '{username}' from {datastore_name}...")
        try:
            existing = repo.get_admin_user(username)
            if not existing and username != ADMIN_USERNAME.strip().lower():
                print(f"Error: Administrator '{username}' not found in the database.", file=sys.stderr)
                sys.exit(1)
                
            confirm = input(f"Are you sure you want to permanently revoke/remove admin privileges for '{username}'? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                print("Operation cancelled.")
                sys.exit(0)
                
            deleted = repo.delete_admin_user(username)
            if deleted:
                print(f"Successfully removed administrator '{username}' and cleared active sessions from {datastore_name}.")
            else:
                print(f"Note: '{username}' was not found in the database (or only exists as static configuration).")
                
            if username == ADMIN_USERNAME.strip().lower():
                print(f"Warning: '{username}' is configured as the active ADMIN_USERNAME in .env. To fully demote, edit your .env.")
        except Exception as e:
            print(f"Error: Failed to remove administrator: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
