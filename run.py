#!/usr/bin/env python
import os
import sys
import subprocess

def main():
    # Detect PORT from environment variable (Render provides this)
    port = os.environ.get('PORT', '8000')
    
    is_dev = os.environ.get('RENDER') is None
    
    print(f"=== JOE CAFETERIA SERVER STARTUP ===")
    
    if is_dev:
        print(f"Starting DEV server on port {port} with auto-reload...")
        command = f"{sys.executable} manage.py runserver 0.0.0.0:{port}"
    else:
        print(f"Starting PROD server on port {port} (Daphne)...")
        command = f"{sys.executable} -m daphne -b 0.0.0.0 -p {port} JOE_Cafeteria.asgi:application"
    
    print(f"$ {command}\n")
    
    try:
        subprocess.run(command, shell=True)
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
