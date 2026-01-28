import threading
import time
from ldap3 import Server, Connection, ALL, SIMPLE, SUBTREE, MODIFY_REPLACE, MODIFY_ADD, MODIFY_DELETE
from ldap3.utils.conv import escape_filter_chars
from fastapi import HTTPException
from backend.core.config import settings

class LdapPool:
    def __init__(self, max_conn=10):
        self.connections = []
        self.in_use = set()
        self.max = max_conn
        self.lock = threading.Lock()

    def get_connection(self):
        with self.lock:
            # Очистка закрытых
            self.connections = [c for c in self.connections if not c.closed]
            
            # Поиск свободного
            avail = [c for c in self.connections if id(c) not in self.in_use]
            if avail:
                conn = avail[0]
                if conn.bind():
                    self.in_use.add(id(conn))
                    return conn
            
            # Создание нового
            if len(self.connections) < self.max:
                s = Server(settings.AD_SERVER, get_info=ALL)
                try:
                    c = Connection(s, user=f"{settings.AD_DOMAIN}\\{settings.AD_SYSTEM_USER}", 
                                   password=settings.AD_SYSTEM_PASSWORD, authentication=SIMPLE, auto_bind=True)
                    self.connections.append(c)
                    self.in_use.add(id(c))
                    return c
                except Exception as e:
                    raise HTTPException(503, f"AD Connect Fail: {e}")
            
            raise HTTPException(503, "LDAP Pool Exhausted")

    def release(self, conn):
        with self.lock:
            if id(conn) in self.in_use:
                self.in_use.remove(id(conn))

ldap_pool = LdapPool()

class LdapService:
    def search(self, base, filter_str, attributes=['*'], scope=SUBTREE):
        conn = ldap_pool.get_connection()
        try:
            conn.search(base, filter_str, attributes=attributes, search_scope=scope)
            return list(conn.entries)
        finally:
            ldap_pool.release(conn)

    def search_users(self, query="", ou=None, active_only=False):
        base = ou if ou else settings.AD_BASE_DN
        q = escape_filter_chars(query)
        f = "(&(objectClass=user)(objectCategory=person)"
        if q:
            f += f"(|(sAMAccountName=*{q}*)(displayName=*{q}*)(mail=*{q}*))"
        if active_only:
            f += "(!(userAccountControl:1.2.840.113556.1.4.803:=2))"
        f += ")"
        
        return self.search(base, f, ["sAMAccountName", "displayName", "mail", "department", "title", "userAccountControl", "distinguishedName"])

    def modify_user(self, dn, changes: dict):
        conn = ldap_pool.get_connection()
        try:
            ldap_changes = {k: [(MODIFY_REPLACE, [v])] for k, v in changes.items() if v is not None}
            if not conn.modify(dn, ldap_changes):
                raise Exception(conn.result['description'])
            return True
        finally:
            ldap_pool.release(conn)

    def create_user(self, dn, attributes):
        conn = ldap_pool.get_connection()
        try:
            if not conn.add(dn, attributes=attributes):
                raise Exception(conn.result['description'])
            return True
        finally:
            ldap_pool.release(conn)
            
    def delete_object(self, dn):
        conn = ldap_pool.get_connection()
        try:
            if not conn.delete(dn):
                raise Exception(conn.result['description'])
            return True
        finally:
            ldap_pool.release(conn)

    def find_user_by_identifier(self, identifier: str):
        """
        Поиск пользователя по идентификатору (sAMAccountName, employeeID, mail, или DN).
        Возвращает первую найденную запись или None.
        """
        base = settings.AD_BASE_DN
        escaped_id = escape_filter_chars(identifier)
        
        # Если это похоже на DN, ищем напрямую
        if identifier.startswith("CN=") or identifier.startswith("DC="):
            entries = self.search(identifier, "(objectClass=user)", attributes=['*'], scope="BASE")
            return entries[0] if entries else None
        
        # Ищем по различным атрибутам
        filter_str = f"(&(objectClass=user)(objectCategory=person)(|(sAMAccountName={escaped_id})(employeeID={escaped_id})(mail={escaped_id})))"
        entries = self.search(base, filter_str, attributes=['*'])
        return entries[0] if entries else None

ldap_service = LdapService()
