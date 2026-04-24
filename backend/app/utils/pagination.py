"""Reusable cursor pagination for all list endpoints.

Stripe-compatible: starting_after/ending_before + has_more.
Sort: order_column DESC, id DESC (deterministic).
Fetch limit+1 to determine has_more without COUNT(*).

Usage:
    from app.utils.pagination import paginate_cursor, validate_cursor_params

    validate_cursor_params(starting_after, ending_before)  # raises HTTPException
    result = await paginate_cursor(
        db=db,
        base_query=select(Invoice).where(Invoice.merchant_id == mid),
        model=Invoice,
        limit=50,
        starting_after=starting_after,
    )
    # result = {"data": [Invoice, ...], "has_more": True}
"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession


def validate_cursor_params(
    starting_after: uuid.UUID | None,
    ending_before: uuid.UUID | None,
) -> None:
    """Raise 400 if both cursors provided (mutual exclusion)."""
    if starting_after is not None and ending_before is not None:
        raise HTTPException(
            status_code=400,
            detail="Cannot use starting_after and ending_before together.",
        )


def clamp_limit(limit: int) -> int:
    """Clamp limit to 1..100 range."""
    return max(1, min(limit, 100))


async def paginate_cursor(
    db: AsyncSession,
    base_query,
    model,
    limit: int = 50,
    starting_after: uuid.UUID | None = None,
    ending_before: uuid.UUID | None = None,
    order_column=None,
) -> dict[str, Any]:
    """Execute cursor-paginated query.

    Args:
        db: Async database session.
        base_query: SQLAlchemy select() with WHERE filters already applied.
        model: ORM model class (must have .id and order_column).
        limit: Results per page (1-100).
        starting_after: Return results AFTER this ID (forward).
        ending_before: Return results BEFORE this ID (backward).
        order_column: Column for primary sort (default: model.created_at).

    Returns:
        {"data": [model_instances], "has_more": bool}
    """
    limit = clamp_limit(limit)
    if order_column is None:
        order_column = model.created_at

    query = base_query

    if starting_after is not None:
        cursor_row = (await db.execute(select(order_column, model.id).where(model.id == starting_after))).first()
        if cursor_row is None:
            raise HTTPException(status_code=400, detail="Invalid cursor: starting_after not found.")
        cursor_ts, cursor_id = cursor_row
        query = query.where(tuple_(order_column, model.id) < tuple_(cursor_ts, cursor_id))

    elif ending_before is not None:
        cursor_row = (await db.execute(select(order_column, model.id).where(model.id == ending_before))).first()
        if cursor_row is None:
            raise HTTPException(status_code=400, detail="Invalid cursor: ending_before not found.")
        cursor_ts, cursor_id = cursor_row
        query = query.where(tuple_(order_column, model.id) > tuple_(cursor_ts, cursor_id))
        # Backward: sort ASC, then reverse
        query = query.order_by(order_column.asc(), model.id.asc())
        query = query.limit(limit + 1)
        rows = list((await db.execute(query)).scalars().all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        rows.reverse()
        return {"data": rows, "has_more": has_more}

    # Forward (default): sort DESC
    query = query.order_by(order_column.desc(), model.id.desc())
    query = query.limit(limit + 1)
    rows = list((await db.execute(query)).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]

    return {"data": rows, "has_more": has_more}
