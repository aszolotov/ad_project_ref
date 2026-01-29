# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

**AD Enterprise Control System v8.0** - A FastAPI-based Active Directory management system with a Bootstrap 5 frontend. Free alternative to Adaxes, ManageEngine AD Manager Plus, and Quest Active Roles. The system provides user/group/computer management, workflow automation, reports, virtual folders (tags), self-service portal, and an extensible plugin system.

## Development Commands

### Starting the Application

**Development mode:**
```powershell
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Demo mode (no AD required):**
```powershell
$env:DEMO_MODE="true"
$env:SECRET_KEY="demo-secret-key-for-testing-only"
uvicorn backend.main:app --reload
```

**Testing demo mode:**
```powershell
python test_demo_mode.py
```

### Dependencies

**Install all dependencies:**
```powershell
pip install -r requirements.txt
```

**Core dependencies:** FastAPI (0.115.6), uvicorn (0.34.0), ldap3 (2.9.1), SQLAlchemy (2.0.37), pydantic (2.10.4)

### Health Checks

**Check overall system status:**
```powershell
curl http://localhost:8000/health
```

**Check LDAP connection:**
```powershell
curl http://localhost:8000/health/ldap
```

**Check database connection:**
```powershell
curl http://localhost:8000/health/db
```

### API Documentation

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Architecture

### Backend Structure

**Core (`backend/core/`):**
- `config.py` - Settings loaded from environment variables (AD_SERVER, AD_DOMAIN, AD_BASE_DN, SECRET_KEY, etc.). All AD settings are required unless DEMO_MODE=true.
- `security.py` - JWT token creation/validation, password hashing, RBAC roles (admin, helpdesk, manager, auditor, user)
- `security_middleware.py` - Security headers (HSTS, CSP, X-Frame-Options)
- `logging_config.py` - Centralized logging configuration

**Database (`backend/db/`):**
- `database.py` - SQLAlchemy engine, session management
- `models.py` - 7 SQLAlchemy models: AuditRecord, UserSettings, ApprovalRequest, Tag, ObjectTag
- Uses SQLite by default (`audit.db`), but PostgreSQL recommended for production

**Services (`backend/services/`):**
- `ldap_service.py` - LDAP connection pool (default 10 connections), all AD operations (search, create, modify, delete). Uses escape_filter_chars for security.
- `audit_service.py` - Logs all operations to AuditRecord table
- `plugin_manager.py` - Sandboxed plugin execution with SafeRequests, NetworkTools, PluginDatabase. Validates plugins for dangerous code patterns.
- `workflow_engine.py` - Multi-step workflow execution with approval steps
- `scheduler.py` - Background task scheduling

**Routers (`backend/routers/`):**
- `auth.py` - Login (/token), JWT validation, RBAC permission checking, self-service password change
- `users.py` - CRUD for AD users, bulk operations, password reset, group membership
- `groups.py` - CRUD for AD groups
- `workflows.py` - Workflow CRUD, execution engine integration
- `reports.py` - Report generation with dynamic filters, 14+ predefined templates
- `tags.py` - Virtual folders (tags) system - 12 endpoints for organizing objects
- `user_templates.py` - 5 predefined templates (Developer, Sales, Marketing, etc.)
- `self_service.py` - User self-service portal for profile editing
- `import_router.py` - Bulk CSV/Excel import
- `system.py` - System health, plugin management

### Frontend Architecture

**Single-page app in `frontend/index.html` (3500+ lines):**
- Bootstrap 5 + jQuery + Chart.js + DataTables
- All functionality embedded in one HTML file
- Key sections: Dashboard, Users, Groups, Computers, Workflows, Reports, Tags, Settings
- Uses JWT tokens stored in localStorage
- API base URL: `/api/v6` (from settings.API_V1_STR)

**Separate component:**
- `wizard_modal.html` - 5-step user creation wizard reference implementation

### Plugin System

**Location:** `plugins/` directory

**Plugin types:**
- Event hooks (pre_create, post_create, pre_modify, post_modify, etc.)
- Scheduled tasks (via schedule library)
- Custom dashboard widgets (render_widget hook)
- API interceptors (api_request hook)

**Plugin execution:**
- Sandboxed with limited builtins
- Access to SafeRequests (whitelist-based HTTP), NetworkTools (ping), PluginDatabase
- Code validation blocks: os.system, subprocess.run, eval, exec, pickle.loads (except specific allowed patterns)

**Available plugins:**
- `access_certification.py` - Access reviews
- `advanced_reporting.py` - Extended reporting
- `ai_anomaly_detection.py` - ML-based anomaly detection
- `computer_status.py` - Computer ping checks
- `dashboard_widgets.py` - Custom dashboard widgets
- `microsoft365_plugin.py` - M365 integration
- `realtime_alerts.py` - Real-time alerting
- `risk_compliance.py` - Compliance monitoring
- `saml_authentication.py` - SAML SSO

### Security Architecture

**Authentication:**
- LDAP bind authentication with multiple candidate formats (UPN, DOMAIN\User, sAMAccountName)
- JWT tokens (HS256 algorithm)
- Rate limiting on login (5/minute), create (10/minute), mass operations (3/minute)
- Token expiry configurable via ACCESS_TOKEN_EXPIRE_MINUTES (default 60)

**Authorization (RBAC):**
- 5 roles: admin (*), helpdesk, manager, auditor, user
- Permission format: `resource:action` (e.g., "users:create", "workflows:execute")
- PermissionChecker dependency for route protection
- Scope-based RBAC via ALLOWED_OUS setting restricts operations to specific OUs

**Audit:**
- All operations logged to audit_logs table via log_event()
- Captures: user, action, target, details (JSON), ip_address, status, timestamp

**LDAP Security:**
- Connection pooling prevents exhaustion attacks
- LDAP filter injection protection via escape_filter_chars()
- LDAPS support (configure via AD_SERVER with ldaps:// protocol)

## Key Implementation Patterns

### LDAP Operations

**Always use the connection pool:**
```python
conn = ldap_pool.get_connection()
try:
    # Perform LDAP operation
    conn.search(...)
finally:
    ldap_pool.release(conn)
```

**Use ldap_service wrapper methods when possible:**
```python
# Preferred
ldap_service.search_users(query="john", active_only=True)

# Instead of manual pool management
```

### Database Sessions

**Use dependency injection:**
```python
@router.post("/example")
def example_endpoint(db: Session = Depends(get_db)):
    # db session is automatically managed
    log_event(db, user="admin", action="EXAMPLE", ...)
```

### Audit Logging

**Log all significant operations:**
```python
log_event(
    db=db,
    user=current_user["username"],
    action="CREATE_USER",  # Convention: VERB_RESOURCE
    target=user_dn,
    details={"attributes": attrs_dict},
    ip=request.client.host,
    status="SUCCESS"  # or "FAIL"
)
```

### Workflow Triggering

**Trigger workflows after operations:**
```python
workflow_engine.trigger("user_created", context={
    "user_dn": new_user_dn,
    "created_by": admin_username,
    "attributes": user_attributes
})
```

### Permission Checking

**Use PermissionChecker dependency:**
```python
@router.post("/users")
def create_user(
    admin=Depends(PermissionChecker("users:create"))
):
    # Route only accessible to users with users:create permission
```

### Rate Limiting

**Apply to sensitive endpoints:**
```python
@router.post("/token")
@limiter.limit("5/minute")
def login(request: Request, ...):
    # Automatically rate-limited per IP
```

## Configuration

### Environment Variables (Required)

**Security:**
- `SECRET_KEY` - JWT signing key (REQUIRED, no default)

**Active Directory:**
- `AD_SERVER` - LDAP URL (e.g., ldap://dc.company.local or ldaps://dc.company.local:636)
- `AD_DOMAIN` - Domain name (e.g., COMPANY)
- `AD_BASE_DN` - Base DN (e.g., DC=company,DC=local)
- `AD_SYSTEM_USER` - Service account username
- `AD_SYSTEM_PASSWORD` - Service account password

**Optional:**
- `DEMO_MODE=true` - Bypass AD requirements for testing
- `ALLOWED_OUS` - Semicolon-separated list of allowed OUs for security
- `DATABASE_URL` - Database connection string (default: sqlite:///./audit.db)
- `LDAP_POOL_SIZE` - Connection pool size (default: 10)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - JWT expiry (default: 60)

### Configuration File

See `.env` for a complete example configuration. The `.env` file in this project is configured for domain `corp.tcax.ru`.

## Common Development Tasks

### Adding a New Router Endpoint

1. Create endpoint in appropriate router file (e.g., `backend/routers/users.py`)
2. Add permission check via `Depends(PermissionChecker("resource:action"))`
3. Add audit logging via `log_event()`
4. Consider workflow trigger if applicable
5. Register router in `backend/main.py` if new router file created

### Creating a Plugin

1. Create Python file in `plugins/` directory
2. Implement `get_metadata()` function returning name, version, description
3. Implement `register_hooks(registrar)` function
4. Register hooks via `registrar.register_hook(event, callback_function)`
5. Use only safe_requests, network_tools, logger, db from plugin context
6. Plugin tables must be prefixed with `plugin_`

### Adding a Report Template

Edit `backend/routers/reports.py`, add to `get_report_templates()`:
```python
{
    "id": "report_id",
    "name": "Report Name",
    "description": "Description",
    "attributes": ["cn", "mail", "department"],
    "filters": [
        {"field": "department", "operator": "equals", "value": "IT"}
    ]
}
```

### Modifying RBAC Permissions

Edit `backend/core/security.py`, update `ROLES` dictionary:
```python
ROLES = {
    "admin": ["*"],
    "helpdesk": ["users:read", "users:create", "users:update", ...],
    # Add new permissions to existing roles
}
```

## Database Schema

**Key tables:**
- `audit_logs` - All system operations (id, timestamp, user, action, target, details, ip_address, status)
- `tags` - Virtual folder definitions (id, name, description, color, icon, created_at, created_by)
- `object_tags` - Tag assignments (id, object_dn, object_type, tag_name, tag_color, created_at, created_by)
- `approval_requests` - Workflow approvals (id, requester, approver, action_type, payload, status, created_at)
- `user_settings` - User preferences (username, dashboard_config)

## Special Considerations

### Windows vs Linux

- Code is cross-platform compatible (FastAPI/Python)
- NetworkTools.ping() handles OS-specific ping commands
- Path handling uses pathlib.Path for cross-platform compatibility
- Line endings: CRLF on Windows, LF on Linux (handle both)

### LDAP UserAccountControl Flags

- UAC & 2 == Account disabled
- UAC & 16 == Account locked
- 512 = Normal enabled account
- 514 = Normal disabled account

### DN Encoding

Always URL-encode DNs when passing in URLs:
```python
import urllib.parse
dn = urllib.parse.unquote(dn)  # Decode from URL
```

### Demo Mode

When DEMO_MODE=true:
- System bypasses LDAP connection requirements
- Uses `demo_ad_service` for in-memory AD simulation
- Useful for frontend development and testing without AD infrastructure
- Run `python test_demo_mode.py` to verify demo mode functionality

## Testing Approach

**No formal test suite exists.** Testing is done via:

1. Health check endpoints (/health, /health/ldap, /health/db)
2. Demo mode script (test_demo_mode.py)
3. Manual testing via Swagger UI (/docs)
4. Plugin testing via /api/v6/plugins/test endpoint

When making changes, verify via health checks and manual API testing.

## Project Status

**Version:** 8.0 (95% complete)
**Production Ready:** Yes, pending final frontend JavaScript integration
**Next Steps:** Add JavaScript for Virtual Folders and Wizard UI components

