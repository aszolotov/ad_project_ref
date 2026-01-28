# AI/ML Anomaly Detection Plugin
# Detects suspicious behavior using machine learning

def get_metadata():
    return {
        "name": "AI Anomaly Detection",
        "version": "1.0.0",
        "description": "ML-based anomaly detection for AD operations",
        "author": "VibeCode Team",
        "config": {
            "ml_api_url": "http://ml-service.corp.local:5000",
            "risk_threshold": 75,
            "alert_on_anomaly": True
        }
    }

def calculate_risk_score(data):
    """Calculate risk score based on multiple factors"""
    
    score = 0
    violations = []
    
    # Time-based anomaly (creation outside business hours)
    hour = datetime.now().hour
    if hour < 7 or hour > 19:
        score += 30
        violations.append("Created outside business hours")
    
    # Weekend creation
    if datetime.now().weekday() >= 5:  # Saturday or Sunday
        score += 20
        violations.append("Created on weekend")
    
    # Too many group memberships
    groups = data.get("memberOf", [])
    if len(groups) > 15:
        score += 25
        violations.append(f"Too many groups: {len(groups)}")
    
    # Admin groups
    admin_keywords = ["admin", "domain admins", "enterprise admins", "privileged"]
    admin_groups = [g for g in groups if any(kw in g.lower() for kw in admin_keywords)]
    if admin_groups:
        score += 40
        violations.append(f"Admin groups: {len(admin_groups)}")
    
    # Password never expires
    if data.get("passwordNeverExpires"):
        score += 35
        violations.append("Password never expires")
    
    # Multiple failed login attempts (if available in data)
    failed_logins = data.get("failedLoginAttempts", 0)
    if failed_logins > 3:
        score += 20
        violations.append(f"Failed logins: {failed_logins}")
    
    # External email domain
    email = data.get("mail", "")
    if email and not email.endswith("@company.com"):
        score += 15
        violations.append("External email domain")
    
    return min(score, 100), violations

def ml_based_detection(data):
    """Use external ML service for advanced detection"""
    
    config = get_metadata()["config"]
    ml_url = config["ml_api_url"]
    
    # Prepare features for ML model
    features = {
        "hour_of_day": datetime.now().hour,
        "day_of_week": datetime.now().weekday(),
        "num_groups": len(data.get("memberOf", [])),
        "has_admin_groups": any("admin" in g.lower() for g in data.get("memberOf", [])),
        "password_never_expires": data.get("passwordNeverExpires", False),
        "account_enabled": data.get("enabled", True)
    }
    
    try:
        resp = safe_requests.post(
            f"{ml_url}/predict",
            json={"features": features}
        )
        
        if resp.status_code == 200:
            ml_result = resp.json()
            return ml_result.get("anomaly_score", 0), ml_result.get("is_anomaly", False)
    except Exception as e:
        logger.error(f"ML API error: {e}")
    
    return 0, False

def detect_anomaly(data):
    """Main anomaly detection function"""
    
    config = get_metadata()["config"]
    
    # Rule-based scoring
    risk_score, violations = calculate_risk_score(data)
    
    # ML-based detection (if available)
    ml_score, is_ml_anomaly = ml_based_detection(data)
    
    # Combined score
    combined_score = int((risk_score * 0.6) + (ml_score * 0.4))
    
    # Add to data
    data["risk_score"] = combined_score
    data["risk_violations"] = violations
    data["is_anomaly"] = combined_score > config["risk_threshold"]
    data["ml_anomaly"] = is_ml_anomaly
    
    # Alert if high risk
    if combined_score > config["risk_threshold"] and config["alert_on_anomaly"]:
        send_anomaly_alert(data, combined_score, violations)
    
    logger.info(f"Risk score for {data.get('cn')}: {combined_score}/100")
    
    return data

def send_anomaly_alert(data, score, violations):
    """Send alert for detected anomaly"""
    
    message = f"""
⚠️ ANOMALY DETECTED ⚠️

User: {data.get('cn')}
Login: {data.get('sAMAccountName')}
Risk Score: {score}/100

Violations:
{chr(10).join(f'• {v}' for v in violations)}

Action: Review and verify this account
    """
    
    # Send to Telegram (if plugin available)
    try:
        # This would call telegram plugin if it exists
        logger.warning(message)
    except Exception:
        pass

def register_hooks(registrar):
    """Register hooks"""
    registrar.register_hook("post_create", detect_anomaly)
    registrar.register_hook("post_modify", detect_anomaly)
