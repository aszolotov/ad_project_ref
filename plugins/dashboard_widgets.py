# Dashboard Custom Widgets Plugin
# Provides custom dashboard widgets and metrics

def get_metadata():
    return {
        "name": "Custom Dashboard Widgets",
        "version": "1.0.0",
        "description": "Additional widgets for dashboard",
        "author": "VibeCode Team",
        "config": {
            "enabled": True
        }
    }

def widget_risk_score_distribution(data):
    """Widget showing risk score distribution"""
    
    # This would be called from dashboard
    # Returns widget data in JSON format
    
    widget = {
        "id": "risk_score_distribution",
        "title": "Risk Score Distribution",
        "type": "chart",
        "chart_type": "bar",
        "size": "col-md-6",
        "data": {
            "labels": ["Low (0-30)", "Medium (31-60)", "High (61-80)", "Critical (81-100)"],
            "datasets": [{
                "label": "Users",
                "data": [150, 45, 12, 3],  # Would query from database
                "backgroundColor": ["#4caf50", "#ff9800", "#ff5722", "#f44336"]
            }]
        },
        "options": {
            "responsive": True,
            "plugins": {
                "legend": {"display": False}
            }
        }
    }
    
    return widget

def widget_recent_anomalies(data):
    """Widget showing recent detected anomalies"""
    
    # Query plugin table for recent anomalies
    try:
        if hasattr(data, "db"):
            anomalies = db.query("plugin_anomalies", {"detected": True})
        else:
            anomalies = []
    except:
        anomalies = []
    
    widget = {
        "id": "recent_anomalies",
        "title": "Recent Anomalies",
        "type": "list",
        "size": "col-md-6",
        "data": {
            "items": [
                {
                    "text": f"{a['user_name']} - Risk: {a['risk_score']}",
                    "icon": "fa-exclamation-triangle",
                    "color": "text-danger" if a['risk_score'] > 80 else "text-warning"
                }
                for a in anomalies[:5]
            ]
        }
    }
    
    return widget

def widget_m365_sync_status(data):
    """Widget showing Microsoft 365 sync status"""
    
    widget = {
        "id": "m365_sync_status",
        "title": "Microsoft 365 Sync",
        "type": "stats",
        "size": "col-md-3",
        "data": {
            "value": "98.5%",
            "label": "Sync Success Rate",
            "icon": "fa-cloud",
            "color": "text-success",
            "trend": "+2.3%"
        }
    }
    
    return widget

def widget_compliance_score(data):
    """Widget showing overall compliance score"""
    
    widget = {
        "id": "compliance_score",
        "title": "Compliance Score",
        "type": "gauge",
        "size": "col-md-3",
        "data": {
            "value": 87,
            "max": 100,
            "thresholds": [
                {"value": 60, "color": "#f44336"},
                {"value": 80, "color": "#ff9800"},
                {"value": 90, "color": "#4caf50"}
            ]
        }
    }
    
    return widget

def register_hooks(registrar):
    """Register widget hooks"""
    registrar.register_hook("render_widget", widget_risk_score_distribution)
    registrar.register_hook("render_widget", widget_recent_anomalies)
    registrar.register_hook("render_widget", widget_m365_sync_status)
    registrar.register_hook("render_widget", widget_compliance_score)
