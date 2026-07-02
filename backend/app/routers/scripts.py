"""User scripts router — AI generation, CRUD, and run history."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.playbook import UserScript
from app.models.user import User
from app.schemas.playbook import UserScriptCreate, UserScriptOut
from app.services import ai_service, metering_service

router = APIRouter(prefix="/api/scripts", tags=["scripts"])


# ── Request / response schemas ────────────────────────────────────────────────

class GenerateScriptRequest(BaseModel):
    """Request body for AI script generation."""
    request: str
    os_family: str = "linux"          # "linux" | "windows" | "both"
    save: bool = False                 # if True, persist to user_scripts immediately
    user_language: str = "en"


class GenerateScriptResult(BaseModel):
    """Response from AI script generation."""
    title: str
    description: str
    script_type: str
    estimated_runtime_seconds: int
    variables: list
    script: str
    post_run_instructions: str
    warnings: list
    saved_id: uuid.UUID | None = None  # set when save=True


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_script(
    script_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> UserScript:
    """Fetch a user script owned by the current user or raise 404."""
    result = await db.execute(
        select(UserScript).where(
            UserScript.id == script_id,
            UserScript.user_id == current_user.id,
        )
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
    return script


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateScriptResult)
async def generate_script(
    body: GenerateScriptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerateScriptResult:
    """Use AI to generate a server administration script."""
    # AI quota gate (docs/AI-METERING.md §2/§4) — script generation = 1 action from the
    # acting user's pool. Only blocks when ENFORCE_AI_QUOTA is on.
    g = await metering_service.gate(db, current_user)
    if not g.allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=metering_service.quota_message(g),
        )

    tok = metering_service.start_collection()
    try:
        result = await ai_service.generate_script(
            request=body.request,
            os_family=body.os_family,
            user_language=body.user_language,
        )
    except Exception as exc:
        # Tokens may have been spent before our error — ledger them at 0 actions (§2).
        calls = metering_service.finish_collection(tok)
        await metering_service.record(
            db, user_id=current_user.id, feature="script_gen", calls=calls,
            actions=0, status="provider_error",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI generation failed: {exc}",
        )
    calls = metering_service.finish_collection(tok)
    await metering_service.record(
        db, user_id=current_user.id, feature="script_gen", calls=calls,
    )

    saved_id: uuid.UUID | None = None
    if body.save:
        script = UserScript(
            user_id=current_user.id,
            title=result.get("title", "Generated Script"),
            description=result.get("description"),
            script_type=result.get("script_type", "bash"),
            script_content=result.get("script", ""),
            variables=result.get("variables") or [],
            source="ai_generated",
            tags=["ai-generated"],
        )
        db.add(script)
        await db.commit()
        await db.refresh(script)
        saved_id = script.id

    return GenerateScriptResult(
        title=result.get("title", ""),
        description=result.get("description", ""),
        script_type=result.get("script_type", "bash"),
        estimated_runtime_seconds=result.get("estimated_runtime_seconds", 30),
        variables=result.get("variables") or [],
        script=result.get("script", ""),
        post_run_instructions=result.get("post_run_instructions", ""),
        warnings=result.get("warnings") or [],
        saved_id=saved_id,
    )


@router.get("", response_model=list[UserScriptOut])
async def list_scripts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UserScript]:
    """List all scripts owned by the current user."""
    result = await db.execute(
        select(UserScript)
        .where(UserScript.user_id == current_user.id)
        .order_by(UserScript.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=UserScriptOut, status_code=status.HTTP_201_CREATED)
async def create_script(
    body: UserScriptCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserScript:
    """Save a script manually (no AI generation)."""
    script = UserScript(
        user_id=current_user.id,
        title=body.title,
        description=body.description,
        script_type=body.script_type,
        script_content=body.script_content,
        variables=body.variables or [],
        source="manual",
        tags=body.tags or [],
    )
    db.add(script)
    await db.commit()
    await db.refresh(script)
    return script


@router.get("/{script_id}", response_model=UserScriptOut)
async def get_script(
    script_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserScript:
    """Get a single user script."""
    return await _get_script(script_id, current_user, db)


@router.put("/{script_id}", response_model=UserScriptOut)
async def update_script(
    script_id: uuid.UUID,
    body: UserScriptCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserScript:
    """Update a user script."""
    script = await _get_script(script_id, current_user, db)
    script.title = body.title
    script.description = body.description
    script.script_type = body.script_type
    script.script_content = body.script_content
    if body.variables is not None:
        script.variables = body.variables
    if body.tags is not None:
        script.tags = body.tags
    await db.commit()
    await db.refresh(script)
    return script


@router.delete("/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script(
    script_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a user script."""
    script = await _get_script(script_id, current_user, db)
    await db.delete(script)
    await db.commit()
