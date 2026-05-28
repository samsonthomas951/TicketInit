from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Numeric,
    ForeignKey,
    func,
)
from .database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    icon = Column(String(50), nullable=True)  # Font Awesome class e.g. "fa-music"


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    poster_url = Column(String(500), nullable=True)
    venue = Column(String(255), nullable=True)
    location = Column(String(500), nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=True)
    min_price = Column(Numeric(10, 2), nullable=True)  # NULL → free
    is_free = Column(Boolean, default=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    organizer = Column(String(255), nullable=True)
    is_published = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TicketTier(Base):
    __tablename__ = "ticket_tiers"

    id = Column(Integer, primary_key=True)
    event_id = Column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(100), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    capacity = Column(Integer, nullable=True)
    sold = Column(Integer, default=0)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(30), nullable=False)
    payment_method = Column(String(50), nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    # status: pending | processing | paid | failed | cancelled
    status = Column(String(20), default="pending", nullable=False)
    failure_reason = Column(Text, nullable=True)
    # JSON snapshot of cart items at time of order
    items_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)     
    is_active    = Column(Boolean, default=True)     
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
