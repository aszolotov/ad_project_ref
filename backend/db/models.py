from sqlalchemy import Column, Integer, String, DateTime, Text, UniqueConstraint
from datetime import datetime
from .database import Base

class AuditRecord(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user = Column(String(255), index=True)    # Кто выполнил
    action = Column(String(100), index=True)  # Что выполнил (CREATE_USER, LOGIN)
    target = Column(String(500))              # Над кем/чем выполнил
    details = Column(Text)                    # JSON детали или текст
    ip_address = Column(String(45))
    status = Column(String(50))               # SUCCESS / FAIL

class UserSettings(Base):
    __tablename__ = "user_settings"

    username = Column(String(255), primary_key=True)
    dashboard_config = Column(Text) # Хранит JSON настройки виджетов

class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    requester = Column(String(255), index=True)  # Кто запросил
    approver = Column(String(255), nullable=True) # Кто должен подтвердить (или роль)
    action_type = Column(String(100))            # Тип действия (workflow_step, user_create, etc)
    payload = Column(Text)                       # JSON с данными для выполнения
    status = Column(String(50), default="PENDING") # PENDING, APPROVED, REJECTED
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    processed_by = Column(String(255), nullable=True) # Кто реально подтвердил/отклонил
    comment = Column(Text, nullable=True)

class Tag(Base):
    """
    Модель для определения доступных тегов (Virtual Folders).
    """
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500))
    color = Column(String(7), default="#4f46e5")  # Hex color
    icon = Column(String(50), default="fa-tag")    # Font Awesome icon
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255))

class ObjectTag(Base):
    """
    Модель для привязки тегов к AD объектам.
    Позволяет создавать виртуальные представления объектов.
    """
    __tablename__ = "object_tags"
    
    id = Column(Integer, primary_key=True, index=True)
    object_dn = Column(String(500), index=True, nullable=False)  # DN объекта в AD
    object_type = Column(String(50), nullable=False)  # 'user', 'group', 'computer'
    tag_name = Column(String(100), index=True, nullable=False)   # Название тега
    tag_color = Column(String(7), default="#4f46e5")  # Цвет тега (кэш)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=False)  # Username создателя
    
    # Unique constraint: один объект не может иметь дублирующихся тегов
    __table_args__ = (
        UniqueConstraint('object_dn', 'tag_name', name='uq_object_tag'),
    )
