from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from datetime import datetime

from backend.core.config import settings
from backend.db.database import get_db
from backend.db.models import Tag, ObjectTag
from backend.routers.auth import PermissionChecker
from backend.services.ldap_service import ldap_service

router = APIRouter(prefix=f"{settings.API_V1_STR}/tags", tags=["tags"])

# ===== PYDANTIC MODELS =====

class TagCreate(BaseModel):
    name: str
    description: str = ""
    color: str = "#4f46e5"
    icon: str = "fa-tag"

class TagResponse(BaseModel):
    id: int
    name: str
    description: str
    color: str
    icon: str
    object_count: int = 0

class ObjectTagCreate(BaseModel):
    tag_name: str

# ===== TAG MANAGEMENT =====

@router.get("", response_model=List[TagResponse])
def get_all_tags(
    db: Session = Depends(get_db),
    user=Depends(PermissionChecker("tags:read"))
):
    """
    Получить все доступные теги с количеством объектов.
    """
    tags = db.query(Tag).all()
    
    result = []
    for tag in tags:
        count = db.query(ObjectTag).filter(ObjectTag.tag_name == tag.name).count()
        result.append(TagResponse(
            id=tag.id,
            name=tag.name,
            description=tag.description,
            color=tag.color,
            icon=tag.icon,
            object_count=count
        ))
    
    return result

@router.post("")
def create_tag(
    tag: TagCreate,
    db: Session = Depends(get_db),
    user=Depends(PermissionChecker("tags:create"))
):
    """
    Создать новый тег (виртуальную папку).
    """
    # Check if exists
    existing = db.query(Tag).filter(Tag.name == tag.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Tag '{tag.name}' already exists")
    
    new_tag = Tag(
        name=tag.name,
        description=tag.description,
        color=tag.color,
        icon=tag.icon,
        created_by=user.get("username", "system")
    )
    db.add(new_tag)
    db.commit()
    db.refresh(new_tag)
    
    return {"status": "success", "tag": {"id": new_tag.id, "name": new_tag.name}}

@router.delete("/{tag_name}")
def delete_tag(
    tag_name: str,
    db: Session = Depends(get_db),
    user=Depends(PermissionChecker("tags:delete"))
):
    """
    Удалить тег и все связи с объектами.
    """
    tag = db.query(Tag).filter(Tag.name == tag_name).first()
    if not tag:
        raise HTTPException(status_code=404, detail=f"Tag '{tag_name}' not found")
    
    # Delete all object tags
    deleted_count = db.query(ObjectTag).filter(ObjectTag.tag_name == tag_name).delete()
    
    # Delete tag itself
    db.delete(tag)
    db.commit()
    
    return {
        "status": "success", 
        "message": f"Tag '{tag_name}' deleted",
        "objects_untagged": deleted_count
    }

# ===== OBJECT TAGGING =====

@router.get("/objects/{object_dn:path}/tags")
def get_object_tags(
    object_dn: str,
    db: Session = Depends(get_db),
    user=Depends(PermissionChecker("tags:read"))
):
    """
    Получить все теги объекта.
    """
    tags = db.query(ObjectTag).filter(ObjectTag.object_dn == object_dn).all()
    return {"tags": [t.tag_name for t in tags]}

@router.post("/objects/{object_dn:path}/tags")
def add_tag_to_object(
    object_dn: str,
    data: ObjectTagCreate,
    db: Session = Depends(get_db),
    user=Depends(PermissionChecker("tags:create"))
):
    """
    Добавить тег к объекту.
    """
    # Check if tag exists
    tag = db.query(Tag).filter(Tag.name == data.tag_name).first()
    if not tag:
        raise HTTPException(status_code=404, detail=f"Tag '{data.tag_name}' not found")
    
    # Check if already tagged
    existing = db.query(ObjectTag).filter(
        ObjectTag.object_dn == object_dn,
        ObjectTag.tag_name == data.tag_name
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Object already has this tag")
    
    # Determine object type from DN
    object_type = "user"
    dn_lower = object_dn.lower()
    if "ou=groups" in dn_lower or "cn=groups" in dn_lower:
        object_type = "group"
    elif "ou=computers" in dn_lower:
        object_type = "computer"
    
    # Create object tag
    object_tag = ObjectTag(
        object_dn=object_dn,
        object_type=object_type,
        tag_name=data.tag_name,
        tag_color=tag.color,
        created_by=user.get("username", "system")
    )
    db.add(object_tag)
    db.commit()
    
    return {"status": "success", "message": f"Tag '{data.tag_name}' added to object"}

@router.delete("/objects/{object_dn:path}/tags/{tag_name}")
def remove_tag_from_object(
    object_dn: str,
    tag_name: str,
    db: Session = Depends(get_db),
    user=Depends(PermissionChecker("tags:delete"))
):
    """
    Удалить тег у объекта.
    """
    object_tag = db.query(ObjectTag).filter(
        ObjectTag.object_dn == object_dn,
        ObjectTag.tag_name == tag_name
    ).first()
    
    if not object_tag:
        raise HTTPException(status_code=404, detail="Tag not found on this object")
    
    db.delete(object_tag)
    db.commit()
    
    return {"status": "success", "message": f"Tag '{tag_name}' removed from object"}

# ===== VIRTUAL FOLDERS =====

@router.get("/virtual-folders/{tag_name}/objects")
def get_objects_by_tag(
    tag_name: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user=Depends(PermissionChecker("tags:read"))
):
    """
    Получить все объекты с определенным тегом (Virtual Folder view).
    """
    # Check if tag exists
    tag = db.query(Tag).filter(Tag.name == tag_name).first()
    if not tag:
        raise HTTPException(status_code=404, detail=f"Tag '{tag_name}' not found")
    
    object_tags = db.query(ObjectTag).filter(
        ObjectTag.tag_name == tag_name
    ).offset(skip).limit(limit).all()
    
    # Get object details from LDAP
    results = []
    for ot in object_tags:
        try:
            # Try to get object from AD
            obj_data = ldap_service.get_user_details(ot.object_dn)
            if obj_data:
                results.append({
                    "dn": ot.object_dn,
                    "cn": obj_data.get("cn", "Unknown"),
                    "mail": obj_data.get("mail"),
                    "object_type": ot.object_type,
                    "tags": [ot.tag_name]
                })
        except:
            # Object might not exist anymore in AD, but keep in results
            results.append({
                "dn": ot.object_dn,
                "cn": "(Объект не найден в AD)",
                "object_type": ot.object_type,
                "tags": [ot.tag_name],
                "error": "not_found_in_ad"
            })
    
    return {
        "tag": tag_name,
        "tag_color": tag.color,
        "tag_icon": tag.icon,
        "objects": results,
        "count": len(results)
    }

# ===== BULK OPERATIONS =====

class BulkTagRequest(BaseModel):
    object_dns: List[str]
    tag_names: List[str]

@router.post("/bulk-tag")
def bulk_add_tags(
    request: BulkTagRequest,
    db: Session = Depends(get_db),
    user=Depends(PermissionChecker("tags:create"))
):
    """
    Массовое добавление тегов к объектам.
    """
    added_count = 0
    errors = []
    
    for dn in request.object_dns:
        for tag_name in request.tag_names:
            try:
                # Check if tag exists
                tag = db.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    errors.append(f"Tag '{tag_name}' not found")
                    continue
                
                # Check if already tagged
                existing = db.query(ObjectTag).filter(
                    ObjectTag.object_dn == dn,
                    ObjectTag.tag_name == tag_name
                ).first()
                
                if existing:
                    continue  # Skip if already tagged
                
                # Determine type
                object_type = "user"
                dn_lower = dn.lower()
                if "ou=groups" in dn_lower:
                    object_type = "group"
                elif "ou=computers" in dn_lower:
                    object_type = "computer"
                
                # Create
                object_tag = ObjectTag(
                    object_dn=dn,
                    object_type=object_type,
                    tag_name=tag_name,
                    tag_color=tag.color,
                    created_by=user.get("username", "system")
                )
                db.add(object_tag)
                added_count += 1
            except Exception as e:
                errors.append(f"Error tagging {dn}: {str(e)}")
    
    db.commit()
    
    return {
        "status": "success",
        "tags_added": added_count,
        "errors": errors
    }
