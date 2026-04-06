# Complete Guide: Setup "Continue with Google" in Django (Free & Without Database Injection)

This guide provides step-by-step instructions on setting up Google Authentication directly via Django `settings.py` and `.env` variables, entirely bypassing the need for database configuration like `setup_google_auth.py` or `django.contrib.sites` manual injection.

---

## Step 1: Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one).
3. Click on the **Navigation Menu** (hamburger icon) > **APIs & Services** > **Credentials**.

## Step 2: Configure the OAuth Consent Screen

> [!IMPORTANT]
> Google requires you to configure this before generating OAuth keys.

1. In the sidebar under APIs & Services, click **OAuth consent screen**.
2. Choose **External** (unless you have a Google Workspace organization and want it internal). Click **Create**.
3. Fill in the required fields:
   - **App name**: E.g., `JOE Cafeteria`
   - **User support email**: Your email
   - **Developer contact info**: Your email
4. Click **Save and Continue**.
5. On the **Scopes** page, click **Add or Remove Scopes**.
   - Add `.../auth/userinfo.email` and `.../auth/userinfo.profile`.
6. Save and Continue through **Test Users** (add yourself if the App is in "Testing" mode) and finish the setup.

## Step 3: Create OAuth Credentials

1. Go back to **Credentials** in the sidebar.
2. Click **+ CREATE CREDENTIALS** > **OAuth client ID**.
3. Application Type: Select **Web application**.
4. Name: E.g., `Django Web Webclient`
5. **Authorized JavaScript origins**:
   - For local testing: `http://localhost:8000`
   - For production: `https://your-production-domain.com`
6. **Authorized redirect URIs**:
   - For local testing: `http://localhost:8000/accounts/google/login/callback/`
   - For production: `https://your-production-domain.com/accounts/google/login/callback/`
7. Click **Create**.
8. A modal will appear with your **Client ID** and **Client Secret**. Copy these!

## Step 4: Configure Django `.env` File

In the root of your project (where `manage.py` lives), create or update your `.env` file (never commit this to git):

```env
GOOGLE_CLIENT_ID="your-client-id-here"
GOOGLE_CLIENT_SECRET="your-client-secret-here"
```

## Step 5: Django Settings Configuration (`settings.py`)

Ensure your `settings.py` contains the following `SOCIALACCOUNT_PROVIDERS` block. The `APP` dictionary is the magic key that avoids needing a Database `SocialApp` record!

```python
import os

# ...

INSTALLED_APPS = [
    # ... your apps ...
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
]

SITE_ID = 1

ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'none'

# The core setup logic
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
            'secret': os.environ.get('GOOGLE_CLIENT_SECRET', ''),
            'key': '',
        }
    }
}
```

> [!TIP]
> By defining `APP` directly in the provider dictionary, Django Allauth reads the API keys directly from your configuration/environment. You no longer need to run any manual python scripts to push these keys into the database!

## Step 6: Test Your Integration

Run your server and navigate to `http://localhost:8000/accounts/login/` or wherever your login template sits. Your "Continue with Google" button should transparently route you to Google, authenticate you, and bring you straight into your application. If there is a redirect URI mismatch error, double-check your callback URLs in the Google Cloud Console.
