# Real-Time Email and Slack Alerting Plugin
# Send immediate notifications for critical AD events

def get_metadata():
    return {
        "name": "Real-Time Alerts",
        "version": "1.0.0",
        "description": "Email and Slack notifications for critical events",
        "author": "VibeCode Team",
        "config": {
            "smtp_host": "smtp.corp.local",
            "smtp_port": 25,
            "admin_email": "admin@company.com",
            "slack_webhook": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL ",
            "enabled": True,
            "alert_on_create": True,
            "alert_on_delete": True,
            "alert_on_admin_changes": True
        }
    }

def send_email_alert(subject, body):
    """Send email notification"""
    
    config = get_metadata()["config"]
    
    email_data = {
        "to": config["admin_email"],
        "subject": subject,
        "body": body,
        "from": "ad-system@company.com"
    }
    
    try:
        resp = safe_requests.post(
            f"http://{config['smtp_host']}:8080/send",
            json=email_data
        )
        
        if resp.status_code == 200:
            logger.info(f"Email sent: {subject}")
        else:
            logger.error(f"Email failed: {resp.status_code}")
    except Exception as e:
        logger.error(f"Email error: {e}")

def send_slack_alert(message, color="warning"):
    """Send Slack notification"""
    
    config = get_metadata()["config"]
    webhook_url = config.get("slack_webhook")
    
    if not webhook_url or webhook_url == "https://hooks.slack.com/services/YOUR/WEBHOOK/URL":
        return  # Not configured
    
    colors = {
        "good": "#36a64f",
        "warning": "#ff9800",
        "danger": "#f44336"
    }
    
    slack_data = {
        "attachments": [{
            "color": colors.get(color, "#808080"),
            "text": message,
            "ts": int(datetime.now().timestamp())
        }]
    }
    
    try:
        resp = safe_requests.post(webhook_url, json=slack_data)
        if resp.status_code == 200:
            logger.info("Slack notification sent")
    except Exception as e:
        logger.error(f"Slack error: {e}")

def alert_on_user_create(data):
    """Alert when new user is created"""
    
    config = get_metadata()["config"]
    if not config["enabled"] or not config["alert_on_create"]:
        return data
    
    cn = data.get("cn", "Unknown")
    username = data.get("sAMAccountName", "unknown")
    creator = data.get("created_by", "system")
    
    subject = f"🆕 New AD User Created: {cn}"
    body = f"""
A new Active Directory user has been created.

User Details:
- Full Name: {cn}
- Username: {username}
- Created By: {creator}
- Created At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Groups: {', '.join(data.get('memberOf', [])[:3])}

Please verify this user creation was authorized.
    """
    
    send_email_alert(subject, body)
    send_slack_alert(f"🆕 New user created: *{cn}* (@{username}) by {creator}", "good")
    
    return data

def alert_on_user_delete(data):
    """Alert when user is deleted"""
    
    config = get_metadata()["config"]
    if not config["enabled"] or not config["alert_on_delete"]:
        return data
    
    cn = data.get("cn", "Unknown")
    username = data.get("sAMAccountName", "unknown")
    deleted_by = data.get("deleted_by", "system")
    
    subject = f"⚠️ AD User Deleted: {cn}"
    body = f"""
CRITICAL: An Active Directory user has been DELETED.

User Details:
- Full Name: {cn}
- Username: {username}
- Deleted By: {deleted_by}
- Deleted At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

IMMEDIATE ACTION REQUIRED: Verify this deletion was authorized.
    """
    
    send_email_alert(subject, body)
    send_slack_alert(f"⚠️ User DELETED: *{cn}* (@{username}) by {deleted_by}", "danger")
    
    return data

def alert_on_admin_privileges(data):
    """Alert when admin privileges are granted"""
    
    config = get_metadata()["config"]
    if not config["enabled"] or not config["alert_on_admin_changes"]:
        return data
    
    groups = data.get("memberOf", [])
    admin_keywords = ["admin", "domain admins", "enterprise admins", "privileged"]
    
    admin_groups = [g for g in groups if any(kw in g.lower() for kw in admin_keywords)]
    
    if admin_groups:
        cn = data.get("cn", "Unknown")
        username = data.get("sAMAccountName", "unknown")
        modified_by = data.get("modified_by", "system")
        
        subject = f"🔒 Admin Privileges Granted: {cn}"
        body = f"""
SECURITY ALERT: Administrative privileges have been granted.

User Details:
- Full Name: {cn}
- Username: {username}
- Modified By: {modified_by}
- Admin Groups: {', '.join(admin_groups)}
- Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

SECURITY REVIEW REQUIRED: Verify this privilege escalation was authorized.
        """
        
        send_email_alert(subject, body)
        send_slack_alert(
            f"🔒 ADMIN privileges granted to *{cn}* (@{username}) by {modified_by}\nGroups: {', '.join(admin_groups)}",
            "danger"
        )
    
    return data

def alert_on_failed_login(data):
    """Alert on repeated failed login attempts"""
    
    failed_attempts = data.get("failed_login_count", 0)
    
    if failed_attempts >= 5:
        username = data.get("sAMAccountName", "unknown")
        
        send_email_alert(
            f"🚨 Failed Login Attempts: {username}",
            f"User {username} has {failed_attempts} failed login attempts. Possible brute force attack."
        )
        send_slack_alert(
            f"🚨 Multiple failed logins for *{username}*: {failed_attempts} attempts",
            "danger"
        )
    
    return data

def register_hooks(registrar):
    """Register alert hooks"""
    registrar.register_hook("post_create", alert_on_user_create)
    registrar.register_hook("post_delete", alert_on_user_delete)
    registrar.register_hook("post_modify", alert_on_admin_privileges)
    registrar.register_hook("auth_failed", alert_on_failed_login)
