# Risk Assessment and Compliance Plugin
# Advanced risk scoring and compliance checking

def get_metadata():
    return {
        "name": "Risk Assessment & Compliance",
        "version": "1.0.0",
        "description": "Comprehensive risk and compliance checking",
        "author": "VibeCode Team",
        "config": {
            "enabled": True,
            "store_results": True,
            "compliance_frameworks": ["GDPR", "HIPAA", "SOC2"]
        }
    }

# Risk weights for different violations
RISK_WEIGHTS = {
    "password_never_expires": 50,
    "weak_password": 40,
    "inactive_90_days": 30,
    "admin_rights": 45,
    "no_login_restriction": 35,
    "shared_account": 60,
    "service_account_interactive": 55,
    "external_email": 20,
    "no_mfa": 25,
    "orphaned_sid": 15
}

def assess_user_risk(data):
    """Comprehensive risk assessment for a user"""
    
    risk_score = 0
    violations = []
    compliance_issues = {}
    
    # Password policy violations
    if data.get("passwordNeverExpires"):
        risk_score += RISK_WEIGHTS["password_never_expires"]
        violations.append("Password never expires")
        compliance_issues["GDPR"] = compliance_issues.get("GDPR", []) + ["Password policy violation"]
    
    # Account inactivity
    last_logon = data.get("lastLogonTimestamp")
    if last_logon:
        days_since_logon = (datetime.now() - last_logon).days
        if days_since_logon > 90:
            risk_score += RISK_WEIGHTS["inactive_90_days"]
            violations.append(f"Inactive for {days_since_logon} days")
            compliance_issues["SOC2"] = compliance_issues.get("SOC2", []) + ["Inactive account"]
    
    # Privileged access
    groups = data.get("memberOf", [])
    admin_groups = [g for g in groups if "admin" in g.lower()]
    if admin_groups:
        risk_score += RISK_WEIGHTS["admin_rights"]
        violations.append(f"Admin rights: {len(admin_groups)} groups")
        compliance_issues["SOC2"] = compliance_issues.get("SOC2", []) + ["Privileged access"]
    
    # Account type checks
    description = data.get("description", "").lower()
    if "service" in description or "svc" in data.get("sAMAccountName", ""):
        if data.get("userAccountControl", 0) & 0x200 == 0:  # Not disabled
            risk_score += RISK_WEIGHTS["service_account_interactive"]
            violations.append("Service account with interactive logon")
            compliance_issues["HIPAA"] = compliance_issues.get("HIPAA", []) + ["Service account misconfiguration"]
    
    # Shared account detection
    if "shared" in description or "generic" in description:
        risk_score += RISK_WEIGHTS["shared_account"]
        violations.append("Shared account detected")
        compliance_issues["GDPR"] = compliance_issues.get("GDPR", []) + ["Shared account"]
        compliance_issues["HIPAA"] = compliance_issues.get("HIPAA", []) + ["Shared account"]
    
    # External email
    email = data.get("mail", "")
    if email and not email.endswith("@company.com"):
        risk_score += RISK_WEIGHTS["external_email"]
        violations.append("External email domain")
    
    # MFA check (if data available)
    if not data.get("mfaEnabled"):
        risk_score += RISK_WEIGHTS["no_mfa"]
        violations.append("MFA not enabled")
        for framework in ["GDPR", "HIPAA", "SOC2"]:
            compliance_issues[framework] = compliance_issues.get(framework, []) + ["MFA not enabled"]
    
    # Calculate final risk level
    risk_level = "Low"
    if risk_score > 80:
        risk_level = "Critical"
    elif risk_score > 60:
        risk_level = "High"
    elif risk_score > 30:
        risk_level = "Medium"
    
    # Add to data
    data["risk_assessment"] = {
        "score": min(risk_score, 100),
        "level": risk_level,
        "violations": violations,
        "compliance_issues": compliance_issues,
        "assessed_at": datetime.now().isoformat()
    }
    
    # Store in plugin database
    config = get_metadata()["config"]
    if config["store_results"] and hasattr(db, "insert"):
        try:
            # Create table if not exists
            db.create_plugin_table("plugin_risk_assessments", {
                "username": "TEXT",
                "risk_score": "INTEGER",
                "risk_level": "TEXT",
                "violations": "TEXT",
                "assessed_at": "DATETIME"
            })
            
            # Store result
            db.insert("plugin_risk_assessments", {
                "username": data.get("sAMAccountName"),
                "risk_score": data["risk_assessment"]["score"],
                "risk_level": risk_level,
                "violations": json.dumps(violations),
                "assessed_at": datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to store risk assessment: {e}")
    
    logger.info(f"Risk assessment for {data.get('cn')}: {risk_level} ({risk_score}/100)")
    
    return data

def generate_compliance_report():
    """Generate compliance report (scheduled)"""
    
    logger.info("Generating compliance report...")
    
    # This would query all users and generate report
    # For now, just log
    
    config = get_metadata()["config"]
    frameworks = config["compliance_frameworks"]
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "frameworks": frameworks,
        "summary": {
            "total_users": 0,
            "compliant": 0,
            "violations": 0
        }
    }
    
    # Send report to admin
    logger.info(f"Compliance report: {json.dumps(report)}")

def register_hooks(registrar):
    """Register hooks"""
    registrar.register_hook("post_create", assess_user_risk)
    registrar.register_hook("post_modify", assess_user_risk)
    registrar.register_hook("scheduler", lambda: schedule.every().monday.at("09:00").do(generate_compliance_report))
