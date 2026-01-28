# Microsoft 365 Integration Plugin
# Provides full Graph API integration for user provisioning and management

def get_metadata():
    """Plugin metadata"""
    return {
        "name": "Microsoft 365 Integration",
        "version": "1.0.0",
        "description": "Full Microsoft 365 sync via Graph API",
        "author": "VibeCode Team",
        "requires": ["msal", "requests"],
        "config": {
            "tenant_id": "YOUR_TENANT_ID",
            "client_id": "YOUR_CLIENT_ID",
            "client_secret": "YOUR_CLIENT_SECRET",
            "enabled": True
        }
    }

# Global token cache
_token_cache = {"token": None, "expires_at": None}

def get_access_token():
    """Get Microsoft Graph API access token using OAuth 2.0"""
    from datetime import datetime, timedelta
    
    # Check if cached token is still valid
    if _token_cache["token"] and _token_cache["expires_at"]:
        if datetime.now() < _token_cache["expires_at"]:
            return _token_cache["token"]
    
    # Get new token
    config = get_metadata()["config"]
    
    token_url = f"https://login.microsoftonline.com/{config['tenant_id']}/oauth2/v2.0/token"
    
    data = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }
    
    resp = safe_requests.post(token_url, data=data)
    
    if resp.status_code == 200:
        token_data = resp.json()
        _token_cache["token"] = token_data["access_token"]
        _token_cache["expires_at"] = datetime.now() + timedelta(seconds=token_data.get("expires_in", 3600))
        return token_data["access_token"]
    
    return None

def sync_user_to_m365(data):
    """Create or update user in Microsoft 365"""
    
    token = get_access_token()
    if not token:
        logger.error("Failed to get M365 access token")
        return data
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Prepare user data for Graph API
    user_principal_name = f"{data.get('sAMAccountName')}@yourdomain.com"
    
    m365_user = {
        "accountEnabled": True,
        "displayName": data.get("cn"),
        "mailNickname": data.get("sAMAccountName"),
        "userPrincipalName": user_principal_name,
        "passwordProfile": {
            "forceChangePasswordNextSignIn": False,
            "password": data.get("password", "TempPassword123!")
        },
        "givenName": data.get("givenName"),
        "surname": data.get("sn"),
        "jobTitle": data.get("title"),
        "department": data.get("department"),
        "mobilePhone": data.get("mobile"),
        "businessPhones": [data.get("telephoneNumber")] if data.get("telephoneNumber") else []
    }
    
    # Try to create user
    resp = safe_requests.post(
        "https://graph.microsoft.com/v1.0/users",
        headers=headers,
        json=m365_user
    )
    
    if resp.status_code in [200, 201]:
        logger.info(f"M365 user created: {user_principal_name}")
        data["m365_synced"] = True
        data["m365_id"] = resp.json().get("id")
    else:
        logger.error(f"M365 sync failed: {resp.text}")
        data["m365_synced"] = False
    
    return data

def assign_m365_license(data):
    """Assign Microsoft 365 license to user"""
    
    token = get_access_token()
    if not token or not data.get("m365_id"):
        return data
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Example: Assign E3 license (replace with your SKU ID)
    license_data = {
        "addLicenses": [
            {
                "skuId": "YOUR_LICENSE_SKU_ID",  # E.g., Office 365 E3
                "disabledPlans": []
            }
        ],
        "removeLicenses": []
    }
    
    user_id = data["m365_id"]
    resp = safe_requests.post(
        f"https://graph.microsoft.com/v1.0/users/{user_id}/assignLicense",
        headers=headers,
        json=license_data
    )
    
    if resp.status_code == 200:
        logger.info(f"License assigned to {data.get('cn')}")
        data["m365_licensed"] = True
    
    return data

def delete_m365_user(data):
    """Delete user from Microsoft 365"""
    
    token = get_access_token()
    if not token:
        return data
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Find user by UPN
    upn = f"{data.get('sAMAccountName')}@yourdomain.com"
    
    resp = safe_requests.delete(
        f"https://graph.microsoft.com/v1.0/users/{upn}",
        headers=headers
    )
    
    if resp.status_code == 204:
        logger.info(f"M365 user deleted: {upn}")
        data["m365_deleted"] = True
    
    return data

def register_hooks(registrar):
    """Register plugin hooks"""
    registrar.register_hook("post_create", sync_user_to_m365)
    registrar.register_hook("post_create", assign_m365_license)
    registrar.register_hook("post_delete", delete_m365_user)
