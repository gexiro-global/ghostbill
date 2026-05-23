import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

from app.utils.pagination import paginate_cursor

Base = declarative_base()


class Item(Base):
    __tablename__ = "items"
    id = Column(UUID(as_uuid=True), primary_key=True)
    merchant_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime)


class Result:
    def first(self):
        return None


class DB:
    async def execute(self, stmt):
        compiled = str(stmt)
        assert "merchant_id" in compiled
        return Result()


@pytest.mark.asyncio
async def test_cross_tenant_cursor_is_invalid():
    merchant_id = uuid.uuid4()
    with pytest.raises(HTTPException) as exc:
        await paginate_cursor(
            db=DB(),
            base_query=None,
            model=Item,
            starting_after=uuid.uuid4(),
            tenant_filter=Item.merchant_id == merchant_id,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid cursor."
