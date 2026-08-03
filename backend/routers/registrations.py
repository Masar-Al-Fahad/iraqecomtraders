import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.permissions import require_permission
from schemas.auth import UserResponse
from services.registrations import RegistrationsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/registrations", tags=["registrations"])


# ---------- Pydantic Schemas ----------
class RegistrationsData(BaseModel):
    """Entity data schema (for create/update)"""
    business_name: str
    merchant_name: str
    phone: str
    governorate: str
    area: str
    business_type: str
    image_key: str
    notes: str = None
    extra_fields: Optional[dict] = None
    status: str
    membership_number: str = None
    membership_status: str = None
    approved_at: str = None
    whatsapp_registration_sent: bool = None
    whatsapp_approval_sent: bool = None
    whatsapp_last_attempt: str = None
    whatsapp_status: str = None


class RegistrationsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    business_name: Optional[str] = None
    merchant_name: Optional[str] = None
    phone: Optional[str] = None
    governorate: Optional[str] = None
    area: Optional[str] = None
    business_type: Optional[str] = None
    image_key: Optional[str] = None
    notes: Optional[str] = None
    extra_fields: Optional[dict] = None
    status: Optional[str] = None
    membership_number: Optional[str] = None
    membership_status: Optional[str] = None
    approved_at: Optional[str] = None
    whatsapp_registration_sent: Optional[bool] = None
    whatsapp_approval_sent: Optional[bool] = None
    whatsapp_last_attempt: Optional[str] = None
    whatsapp_status: Optional[str] = None


class RegistrationsResponse(BaseModel):
    """Entity response schema"""
    id: int
    business_name: str
    merchant_name: str
    phone: str
    governorate: str
    area: str
    business_type: str
    image_key: str
    notes: Optional[str] = None
    extra_fields: Optional[dict] = None
    status: str
    membership_number: Optional[str] = None
    membership_status: Optional[str] = None
    approved_at: Optional[str] = None
    whatsapp_registration_sent: Optional[bool] = None
    whatsapp_approval_sent: Optional[bool] = None
    whatsapp_last_attempt: Optional[str] = None
    whatsapp_status: Optional[str] = None
    last_modified_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("extra_fields", mode="before")
    @classmethod
    def _parse_extra_fields(cls, v):
        from services.extra_fields import loads_extra_fields

        parsed = loads_extra_fields(v)
        return parsed or None

    class Config:
        from_attributes = True


class RegistrationsListResponse(BaseModel):
    """List response schema"""
    items: List[RegistrationsResponse]
    total: int
    skip: int
    limit: int


class RegistrationsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[RegistrationsData]


class RegistrationsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: RegistrationsUpdateData


class RegistrationsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[RegistrationsBatchUpdateItem]


class RegistrationsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=RegistrationsListResponse)
async def query_registrationss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(require_permission("view")),
    db: AsyncSession = Depends(get_db),
):
    """Query registrationss with filtering, sorting, and pagination"""
    logger.debug(f"Querying registrationss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = RegistrationsService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")
        
        result = await service.get_list(
            skip=skip, 
            limit=limit,
            query_dict=query_dict,
            sort=sort,
        )
        logger.debug(f"Found {result['total']} registrationss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid registrations query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying registrationss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=RegistrationsListResponse)
async def query_registrationss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(require_permission("view")),
    db: AsyncSession = Depends(get_db),
):
    # Query registrationss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying registrationss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    _ = current_user

    service = RegistrationsService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")

        result = await service.get_list(
            skip=skip,
            limit=limit,
            query_dict=query_dict,
            sort=sort
        )
        logger.debug(f"Found {result['total']} registrationss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid registrations query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying registrationss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=RegistrationsResponse)
async def get_registrations(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(require_permission("view")),
    db: AsyncSession = Depends(get_db),
):
    """Get a single registrations by ID"""
    logger.debug(f"Fetching registrations with id: {id}, fields={fields}")
    _ = current_user

    service = RegistrationsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Registrations with id {id} not found")
            raise HTTPException(status_code=404, detail="Registrations not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching registrations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=RegistrationsResponse, status_code=201)
async def create_registrations(
    data: RegistrationsData,
    current_user: UserResponse = Depends(require_permission("add")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new registrations"""
    logger.debug(f"Creating new registrations with data: {data}")
    _ = current_user

    service = RegistrationsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create registrations")
        
        logger.info(f"Registrations created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating registrations: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating registrations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[RegistrationsResponse], status_code=201)
async def create_registrationss_batch(
    request: RegistrationsBatchCreateRequest,
    current_user: UserResponse = Depends(require_permission("add")),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple registrationss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} registrationss")
    _ = current_user

    service = RegistrationsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} registrationss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[RegistrationsResponse])
async def update_registrationss_batch(
    request: RegistrationsBatchUpdateRequest,
    current_user: UserResponse = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple registrationss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} registrationss")
    _ = current_user

    service = RegistrationsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} registrationss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=RegistrationsResponse)
async def update_registrations(
    id: int,
    data: RegistrationsUpdateData,
    request: Request,
    current_user: UserResponse = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing registrations"""
    logger.debug(f"Updating registrations {id} with data: {data}")

    # Resolve actor from DB panel user — never trust client-supplied modifier name
    from services.actor import resolve_actor_name
    from services.extra_fields import dumps_extra_fields

    actor = await resolve_actor_name(db, current_user)

    service = RegistrationsService(db)
    try:
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        if "extra_fields" in update_dict:
            update_dict["extra_fields"] = dumps_extra_fields(update_dict["extra_fields"])
        update_dict["last_modified_by"] = actor
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Registrations with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Registrations not found")

        try:
            from routers.audit_log import log_action

            await log_action(
                db,
                "update_member",
                current_user.email,
                target_id=id,
                details=f"Updated by {actor}: {list(update_dict.keys())}",
                ip_address=request.client.host if request.client else None,
            )
        except Exception as audit_err:
            logger.warning("Audit log failed for update %s: %s", id, audit_err)

        logger.info(f"Registrations {id} updated successfully by {actor}")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating registrations {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating registrations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_registrationss_batch(
    request: RegistrationsBatchDeleteRequest,
    current_user: UserResponse = Depends(require_permission("delete")),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple registrationss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} registrationss")
    _ = current_user

    service = RegistrationsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} registrationss successfully")
        return {"message": f"Successfully deleted {deleted_count} registrationss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_registrations(
    id: int,
    current_user: UserResponse = Depends(require_permission("delete")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single registrations by ID"""
    logger.debug(f"Deleting registrations with id: {id}")
    _ = current_user

    service = RegistrationsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Registrations with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Registrations not found")
        
        logger.info(f"Registrations {id} deleted successfully")
        return {"message": "Registrations deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting registrations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")