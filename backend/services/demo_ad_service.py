# Demo Mode Service - Эмулятор AD для тестирования без домена
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import random

logger = logging.getLogger(__name__)

class DemoADService:
    """
    Эмулятор Active Directory для демонстрации и тестирования.
    Используется когда LDAP недоступен.
    """
    
    def __init__(self):
        self.demo_users = self._generate_demo_users()
        self.demo_groups = self._generate_demo_groups()
        self.demo_computers = self._generate_demo_computers()
        logger.info("Demo AD Service initialized with sample data")
    
    def _generate_demo_users(self) -> List[Dict]:
        """Генерация демо-пользователей"""
        users = [
            {
                "dn": "CN=John Doe,OU=Users,DC=demo,DC=local",
                "cn": "John Doe",
                "sAMAccountName": "jdoe",
                "givenName": "John",
                "sn": "Doe",
                "mail": "jdoe@demo.local",
                "userPrincipalName": "jdoe@demo.local",
                "displayName": "John Doe",
                "department": "IT",
                "title": "System Administrator",
                "telephoneNumber": "+1-555-0101",
                "mobile": "+1-555-0102",
                "enabled": True,
                "passwordNeverExpires": False,
                "memberOf": [
                    "CN=Domain Admins,CN=Users,DC=demo,DC=local",
                    "CN=IT Support,OU=Groups,DC=demo,DC=local"
                ],
                "whenCreated": datetime.now() - timedelta(days=365),
                "lastLogonTimestamp": datetime.now() - timedelta(hours=2)
            },
            {
                "dn": "CN=Jane Smith,OU=Users,DC=demo,DC=local",
                "cn": "Jane Smith",
                "sAMAccountName": "jsmith",
                "givenName": "Jane",
                "sn": "Smith",
                "mail": "jsmith@demo.local",
                "userPrincipalName": "jsmith@demo.local",
                "displayName": "Jane Smith",
                "department": "Sales",
                "title": "Sales Manager",
                "telephoneNumber": "+1-555-0201",
                "enabled": True,
                "passwordNeverExpires": False,
                "memberOf": [
                    "CN=Sales,OU=Groups,DC=demo,DC=local",
                    "CN=Users,CN=Builtin,DC=demo,DC=local"
                ],
                "whenCreated": datetime.now() - timedelta(days=180),
                "lastLogonTimestamp": datetime.now() - timedelta(days=1)
            },
            {
                "dn": "CN=Bob Wilson,OU=Users,DC=demo,DC=local",
                "cn": "Bob Wilson",
                "sAMAccountName": "bwilson",
                "givenName": "Bob",
                "sn": "Wilson",
                "mail": "bwilson@demo.local",
                "userPrincipalName": "bwilson@demo.local",
                "displayName": "Bob Wilson",
                "department": "Marketing",
                "title": "Marketing Specialist",
                "enabled": True,
                "passwordNeverExpires": True,  # Risk!
                "memberOf": [
                    "CN=Marketing,OU=Groups,DC=demo,DC=local"
                ],
                "whenCreated": datetime.now() - timedelta(days=90),
                "lastLogonTimestamp": datetime.now() - timedelta(days=95)  # Inactive!
            },
            {
                "dn": "CN=Alice Johnson,OU=Users,DC=demo,DC=local",
                "cn": "Alice Johnson",
                "sAMAccountName": "ajohnson",
                "givenName": "Alice",
                "sn": "Johnson",
                "mail": "ajohnson@demo.local",
                "enabled": False,  # Disabled
                "department": "HR",
                "title": "HR Manager",
                "memberOf": ["CN=HR,OU=Groups,DC=demo,DC=local"],
                "whenCreated": datetime.now() - timedelta(days=500),
                "lastLogonTimestamp": datetime.now() - timedelta(days=120)
            },
            {
                "dn": "CN=Test User,OU=Users,DC=demo,DC=local",
                "cn": "Test User",
                "sAMAccountName": "testuser",
                "givenName": "Test",
                "sn": "User",
                "mail": "test@demo.local",
                "enabled": True,
                "department": "Testing",
                "memberOf": [],
                "whenCreated": datetime.now(),
                "lastLogonTimestamp": None
            }
        ]
        return users
    
    def _generate_demo_groups(self) -> List[Dict]:
        """Генерация демо-групп"""
        return [
            {
                "dn": "CN=Domain Admins,CN=Users,DC=demo,DC=local",
                "cn": "Domain Admins",
                "sAMAccountName": "Domain Admins",
                "description": "Designated administrators of the domain",
                "groupType": -2147483646,  # Security, Global
                "member": ["CN=John Doe,OU=Users,DC=demo,DC=local"],
                "whenCreated": datetime.now() - timedelta(days=1000)
            },
            {
                "dn": "CN=IT Support,OU=Groups,DC=demo,DC=local",
                "cn": "IT Support",
                "sAMAccountName": "IT Support",
                "description": "IT Support Team",
                "groupType": -2147483646,
                "member": ["CN=John Doe,OU=Users,DC=demo,DC=local"],
                "whenCreated": datetime.now() - timedelta(days=800)
            },
            {
                "dn": "CN=Sales,OU=Groups,DC=demo,DC=local",
                "cn": "Sales",
                "description": "Sales Department",
                "member": ["CN=Jane Smith,OU=Users,DC=demo,DC=local"],
                "whenCreated": datetime.now() - timedelta(days=600)
            },
            {
                "dn": "CN=Marketing,OU=Groups,DC=demo,DC=local",
                "cn": "Marketing",
                "description": "Marketing Department",
                "member": ["CN=Bob Wilson,OU=Users,DC=demo,DC=local"],
                "whenCreated": datetime.now() - timedelta(days=400)
            }
        ]
    
    def _generate_demo_computers(self) -> List[Dict]:
        """Генерация демо-компьютеров"""
        return [
            {
                "dn": "CN=WS001,OU=Computers,DC=demo,DC=local",
                "cn": "WS001",
                "sAMAccountName": "WS001$",
                "dNSHostName": "ws001.demo.local",
                "operatingSystem": "Windows 11 Pro",
                "operatingSystemVersion": "10.0 (22631)",
                "enabled": True,
                "lastLogonTimestamp": datetime.now() - timedelta(hours=1),
                "whenCreated": datetime.now() - timedelta(days=180)
            },
            {
                "dn": "CN=WS002,OU=Computers,DC=demo,DC=local",
                "cn": "WS002",
                "sAMAccountName": "WS002$",
                "dNSHostName": "ws002.demo.local",
                "operatingSystem": "Windows 10 Pro",
                "operatingSystemVersion": "10.0 (19045)",
                "enabled": True,
                "lastLogonTimestamp": datetime.now() - timedelta(days=5),
                "whenCreated": datetime.now() - timedelta(days=365)
            },
            {
                "dn": "CN=SRV001,OU=Servers,DC=demo,DC=local",
                "cn": "SRV001",
                "sAMAccountName": "SRV001$",
                "dNSHostName": "srv001.demo.local",
                "operatingSystem": "Windows Server 2022",
                "enabled": True,
                "lastLogonTimestamp": datetime.now() - timedelta(minutes=30),
                "whenCreated": datetime.now() - timedelta(days=730)
            }
        ]
    
    def search_users(self, filters: Dict = None, page: int = 1, per_page: int = 50) -> Dict:
        """Поиск пользователей"""
        users = self.demo_users.copy()
        
        # Apply filters
        if filters:
            if filters.get("enabled") is not None:
                users = [u for u in users if u.get("enabled") == filters["enabled"]]
            if filters.get("department"):
                users = [u for u in users if filters["department"].lower() in u.get("department", "").lower()]
        
        # Pagination
        total = len(users)
        start = (page - 1) * per_page
        end = start + per_page
        
        return {
            "users": users[start:end],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }
    
    def get_user(self, username: str) -> Optional[Dict]:
        """Получить пользователя"""
        for user in self.demo_users:
            if user["sAMAccountName"] == username:
                return user
        return None
    
    def create_user(self, user_data: Dict) -> Dict:
        """Создать пользователя (эмуляция)"""
        new_user = {
            "dn": f"CN={user_data.get('cn')},OU=Users,DC=demo,DC=local",
            "cn": user_data.get("cn"),
            "sAMAccountName": user_data.get("sAMAccountName"),
            "givenName": user_data.get("givenName"),
            "sn": user_data.get("sn"),
            "mail": user_data.get("mail"),
            "enabled": user_data.get("enabled", True),
            "department": user_data.get("department", ""),
            "memberOf": user_data.get("memberOf", []),
            "whenCreated": datetime.now(),
            "lastLogonTimestamp": None
        }
        self.demo_users.append(new_user)
        logger.info(f"Demo: Created user {new_user['sAMAccountName']}")
        return new_user
    
    def update_user(self, username: str, updates: Dict) -> Dict:
        """Обновить пользователя"""
        user = self.get_user(username)
        if user:
            user.update(updates)
            logger.info(f"Demo: Updated user {username}")
            return user
        raise Exception(f"User {username} not found")
    
    def delete_user(self, username: str) -> bool:
        """Удалить пользователя"""
        for i, user in enumerate(self.demo_users):
            if user["sAMAccountName"] == username:
                self.demo_users.pop(i)
                logger.info(f"Demo: Deleted user {username}")
                return True
        return False
    
    def search_groups(self, filters: Dict = None) -> List[Dict]:
        """Поиск групп"""
        return self.demo_groups
    
    def search_computers(self, filters: Dict = None) -> List[Dict]:
        """Поиск компьютеров"""
        return self.demo_computers
    
    def test_connection(self) -> Dict:
        """Проверка подключения (всегда успешна в demo)"""
        return {
            "status": "success",
            "mode": "DEMO",
            "message": "Running in DEMO mode with sample data",
            "users_count": len(self.demo_users),
            "groups_count": len(self.demo_groups),
            "computers_count": len(self.demo_computers)
        }

# Singleton instance
demo_ad_service = DemoADService()
