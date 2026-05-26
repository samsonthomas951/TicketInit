# import math
# import os
# from datetime import datetime, timezone
# from typing import Optional
# from urllib.parse import quote_plus
#
# from fastapi import FastAPI, Request, Depends, HTTPException, Query
# from fastapi.staticfiles import StaticFiles
# from fastapi.templating import Jinja2Templates
# from fastapi.responses import RedirectResponse
# from sqlalchemy import or_, case, asc
# from sqlalchemy.orm import Session
# from starlette.middleware.sessions import SessionMiddleware
#
# from . import models
# from .database import engine, get_db
#
# # ── Bootstrap DB tables ─────────────────────────────────────────────────────
# models.Base.metadata.create_all(bind=engine)
#
# # ── App ──────────────────────────────────────────────────────────────────────
# app = FastAPI(title="TicketInit", docs_url="/api/docs")
#
# SECRET_KEY = os.getenv("SECRET_KEY", "ticketinit-change-this-in-production")
# app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
# app.mount("/static", StaticFiles(directory="static"), name="static")
# templates = Jinja2Templates(directory="app/templates")
#
# EVENTS_PER_PAGE = 24
#
#
# # ── Jinja2 filters ────────────────────────────────────────────────────────────
# def fmt_date(value: datetime, fmt: str = "%a, %b %d, %Y") -> str:
#     if value is None:
#         return ""
#     if value.tzinfo is None:
#         value = value.replace(tzinfo=timezone.utc)
#     return value.strftime(fmt)
#
#
# def fmt_price(value) -> str:
#     if value is None:
#         return "Free"
#     return f"KES {int(value):,}"
#
#
# def fmt_time(value: datetime) -> str:
#     if value is None:
#         return ""
#     if value.tzinfo is None:
#         value = value.replace(tzinfo=timezone.utc)
#     return value.strftime("%I:%M %p")
#
#
# templates.env.filters["fmt_date"] = fmt_date
# templates.env.filters["fmt_price"] = fmt_price
# templates.env.filters["fmt_time"] = fmt_time
#
# # urlencode for map links
# from urllib.parse import quote_plus as _qp
#
# templates.env.filters["urlencode"] = lambda s: _qp(str(s) if s else "")
#
#
# # ── Helpers ───────────────────────────────────────────────────────────────────
# def _now() -> datetime:
#     return datetime.now(timezone.utc)
#
#
# def _is_past(event: models.Event) -> bool:
#     start = event.start_date
#     if start.tzinfo is None:
#         start = start.replace(tzinfo=timezone.utc)
#     return start < _now()
#
#
# def _cart_context(request: Request, event_id: int | None = None):
#     """Return cart items (optionally filtered by event_id) + totals."""
#     cart: dict = request.session.get("cart", {})
#     all_items = list(cart.values())
#     if event_id is not None:
#         items = [i for i in all_items if i["event_id"] == event_id]
#     else:
#         items = all_items
#     total = sum(i["price"] * i["quantity"] for i in items)
#     count = sum(i["quantity"] for i in items)
#     # mapping tier_id → item for quick lookups in templates
#     by_tier = {i["tier_id"]: i for i in items}
#     return items, total, count, by_tier
#
#
# templates.env.globals["is_past"] = _is_past
#
#
# # ── HOME ──────────────────────────────────────────────────────────────────────
# @app.get("/")
# async def home(
#     request: Request,
#     page: int = Query(1, ge=1),
#     search: Optional[str] = Query(None),
#     category: Optional[str] = Query(None),
#     db: Session = Depends(get_db),
# ):
#     q = db.query(models.Event).filter(models.Event.is_published.is_(True))
#
#     if search:
#         like = f"%{search}%"
#         q = q.filter(
#             or_(
#                 models.Event.title.ilike(like),
#                 models.Event.venue.ilike(like),
#                 models.Event.location.ilike(like),
#                 models.Event.organizer.ilike(like),
#             )
#         )
#
#     if category:
#         cat = db.query(models.Category).filter(models.Category.slug == category).first()
#         if cat:
#             q = q.filter(models.Event.category_id == cat.id)
#
#     total = q.count()
#     total_pages = max(1, math.ceil(total / EVENTS_PER_PAGE))
#     now = _now()
#
#     ordering = case((models.Event.start_date >= now, 0), else_=1)
#     events = (
#         q.order_by(ordering, asc(models.Event.start_date))
#         .offset((page - 1) * EVENTS_PER_PAGE)
#         .limit(EVENTS_PER_PAGE)
#         .all()
#     )
#
#     categories = db.query(models.Category).order_by(models.Category.name).all()
#
#     return templates.TemplateResponse(
#         "index.html",
#         {
#             "request": request,
#             "events": events,
#             "total": total,
#             "page": page,
#             "total_pages": total_pages,
#             "pages": list(range(1, total_pages + 1)),
#             "search": search or "",
#             "active_category": category or "",
#             "categories": categories,
#             "now": now,
#         },
#     )
#
#
# # ── EVENT DETAIL ──────────────────────────────────────────────────────────────
# @app.get("/e/{slug}")
# async def event_detail(
#     request: Request,
#     slug: str,
#     db: Session = Depends(get_db),
# ):
#     event = (
#         db.query(models.Event)
#         .filter(models.Event.slug == slug, models.Event.is_published.is_(True))
#         .first()
#     )
#     if not event:
#         raise HTTPException(status_code=404, detail="Event not found")
#
#     tiers = (
#         db.query(models.TicketTier)
#         .filter(models.TicketTier.event_id == event.id)
#         .order_by(models.TicketTier.sort_order, models.TicketTier.price)
#         .all()
#     )
#
#     past = _is_past(event)
#     cart_items, cart_total, cart_count, cart_by_tier = _cart_context(request, event.id)
#
#     # Share URLs
#     event_url = str(request.url)
#     share_whatsapp = (
#         f"https://wa.me/?text={quote_plus(event.title + ' – ' + event_url)}"
#     )
#     share_twitter = (
#         f"https://twitter.com/intent/tweet"
#         f"?url={quote_plus(event_url)}&text={quote_plus(event.title)}"
#     )
#
#     return templates.TemplateResponse(
#         "event_detail.html",
#         {
#             "request": request,
#             "event": event,
#             "tiers": tiers,
#             "past": past,
#             "now": _now(),
#             "cart_items": cart_items,
#             "cart_total": cart_total,
#             "cart_count": cart_count,
#             "cart_by_tier": cart_by_tier,
#             "share_whatsapp": share_whatsapp,
#             "share_twitter": share_twitter,
#             "event_url": event_url,
#         },
#     )
#
#
# # ── CART: ADD / UPDATE ────────────────────────────────────────────────────────
# @app.post("/cart/add")
# async def cart_add(request: Request, db: Session = Depends(get_db)):
#     form = await request.form()
#     tier_id = int(form.get("id", 0))
#     quantity = int(form.get("quantity", 1))
#     slug = form.get("slug", "")
#
#     tier = db.query(models.TicketTier).filter(models.TicketTier.id == tier_id).first()
#     if not tier:
#         raise HTTPException(404, "Ticket tier not found")
#
#     event = db.query(models.Event).filter(models.Event.id == tier.event_id).first()
#
#     cart: dict = request.session.get("cart", {})
#
#     if quantity <= 0:
#         cart.pop(str(tier_id), None)
#     else:
#         avail = (tier.capacity - tier.sold) if tier.capacity else 999
#         cart[str(tier_id)] = {
#             "tier_id": tier_id,
#             "name": tier.name,
#             "price": float(tier.price),
#             "quantity": min(quantity, 10, avail),
#             "event_id": event.id,
#             "event_slug": event.slug,
#             "event_title": event.title,
#         }
#
#     request.session["cart"] = cart
#     return RedirectResponse(f"/e/{event.slug}", status_code=303)
#
#
# # ── CART: REMOVE ──────────────────────────────────────────────────────────────
# @app.post("/cart/remove")
# async def cart_remove(request: Request):
#     form = await request.form()
#     item_id = str(form.get("item_id", ""))
#     slug = form.get("slug", "")
#
#     cart: dict = request.session.get("cart", {})
#     cart.pop(item_id, None)
#     request.session["cart"] = cart
#
#     return RedirectResponse(f"/e/{slug}", status_code=303)
#
#
# # ── CART: BULK UPDATE ─────────────────────────────────────────────────────────
# @app.post("/cart/bulk-update")
# async def cart_bulk_update(request: Request, db: Session = Depends(get_db)):
#     form = await request.form()
#     redirect_to = str(form.get("redirect", "/checkout"))
#     cart: dict = request.session.get("cart", {})
#
#     for key, value in form.items():
#         if key.startswith("quantities["):
#             tier_id = key[len("quantities[") : -1]
#             qty = int(value) if str(value).isdigit() else 0
#             if qty <= 0:
#                 cart.pop(tier_id, None)
#             elif tier_id in cart:
#                 tier = (
#                     db.query(models.TicketTier)
#                     .filter(models.TicketTier.id == int(tier_id))
#                     .first()
#                 )
#                 avail = (tier.capacity - tier.sold) if (tier and tier.capacity) else 999
#                 cart[tier_id]["quantity"] = min(qty, 10, avail)
#
#     request.session["cart"] = cart
#     return RedirectResponse(redirect_to, status_code=303)
#
#
# # ── CHECKOUT ──────────────────────────────────────────────────────────────────
# @app.get("/checkout")
# async def checkout(request: Request):
#     cart_items, cart_total, cart_count, _ = _cart_context(request)
#     return templates.TemplateResponse(
#         "checkout.html",
#         {
#             "request": request,
#             "items": cart_items,
#             "total": cart_total,
#             "count": cart_count,
#             "now": _now(),
#         },
#     )
#
#
# @app.post("/checkout")
# async def checkout_submit(request: Request):
#     """Placeholder – integrate M-Pesa / Stripe here."""
#     request.session["cart"] = {}
#     return RedirectResponse("/checkout/success", status_code=303)
#
#
# @app.get("/checkout/success")
# async def checkout_success(request: Request):
#     return templates.TemplateResponse(
#         "checkout_success.html",
#         {"request": request, "now": _now()},
#     )
#
#
# # ── HEALTH ────────────────────────────────────────────────────────────────────
# @app.get("/health")
# async def health():
#     return {"status": "ok"}

import json
import math
import os
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, case, asc
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import models
from .database import engine, get_db

# ── Bootstrap ─────────────────────────────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="TicketInit", docs_url="/api/docs")
SECRET_KEY = os.getenv("SECRET_KEY", "ticketinit-change-this-in-production")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="app/templates")

EVENTS_PER_PAGE = 24


# ── Jinja2 filters ─────────────────────────────────────────────────────────────
def fmt_date(value: datetime, fmt: str = "%a, %b %d, %Y") -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime(fmt)


def fmt_price(value) -> str:
    if value is None:
        return "Free"
    try:
        return f"KES {int(float(value)):,}"
    except (TypeError, ValueError):
        return str(value)


def fmt_time(value: datetime) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime("%I:%M %p")


from urllib.parse import quote_plus as _qp

templates.env.filters["fmt_date"] = fmt_date
templates.env.filters["fmt_price"] = fmt_price
templates.env.filters["fmt_time"] = fmt_time
templates.env.filters["urlencode"] = lambda s: _qp(str(s) if s else "")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_past(event: models.Event) -> bool:
    start = event.start_date
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start < _now()


def _cart_context(request: Request, event_id: int | None = None):
    cart: dict = request.session.get("cart", {})
    all_items = list(cart.values())
    items = (
        [i for i in all_items if i["event_id"] == event_id] if event_id else all_items
    )
    total = sum(i["price"] * i["quantity"] for i in items)
    count = sum(i["quantity"] for i in items)
    by_tier = {i["tier_id"]: i for i in items}
    return items, total, count, by_tier


templates.env.globals["is_past"] = _is_past


# ── HOME ──────────────────────────────────────────────────────────────────────
@app.get("/")
async def home(
    request: Request,
    page: int = Query(1, ge=1),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(models.Event).filter(models.Event.is_published.is_(True))

    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                models.Event.title.ilike(like),
                models.Event.venue.ilike(like),
                models.Event.location.ilike(like),
                models.Event.organizer.ilike(like),
            )
        )

    if category:
        cat = db.query(models.Category).filter(models.Category.slug == category).first()
        if cat:
            q = q.filter(models.Event.category_id == cat.id)

    total = q.count()
    total_pages = max(1, math.ceil(total / EVENTS_PER_PAGE))
    now = _now()

    ordering = case((models.Event.start_date >= now, 0), else_=1)
    events = (
        q.order_by(ordering, asc(models.Event.start_date))
        .offset((page - 1) * EVENTS_PER_PAGE)
        .limit(EVENTS_PER_PAGE)
        .all()
    )

    categories = db.query(models.Category).order_by(models.Category.name).all()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "events": events,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "pages": list(range(1, total_pages + 1)),
            "search": search or "",
            "active_category": category or "",
            "categories": categories,
            "now": now,
        },
    )


# ── EVENT DETAIL ──────────────────────────────────────────────────────────────
@app.get("/e/{slug}")
async def event_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    event = (
        db.query(models.Event)
        .filter(models.Event.slug == slug, models.Event.is_published.is_(True))
        .first()
    )
    if not event:
        raise HTTPException(404, "Event not found")

    tiers = (
        db.query(models.TicketTier)
        .filter(models.TicketTier.event_id == event.id)
        .order_by(models.TicketTier.sort_order, models.TicketTier.price)
        .all()
    )

    past = _is_past(event)
    cart_items, cart_total, cart_count, cart_by_tier = _cart_context(request, event.id)

    event_url = str(request.url)
    share_whatsapp = f"https://wa.me/?text={_qp(event.title + ' – ' + event_url)}"
    share_twitter = (
        f"https://twitter.com/intent/tweet?url={_qp(event_url)}&text={_qp(event.title)}"
    )

    return templates.TemplateResponse(
        "event_detail.html",
        {
            "request": request,
            "event": event,
            "tiers": tiers,
            "past": past,
            "now": _now(),
            "cart_items": cart_items,
            "cart_total": cart_total,
            "cart_count": cart_count,
            "cart_by_tier": cart_by_tier,
            "share_whatsapp": share_whatsapp,
            "share_twitter": share_twitter,
            "event_url": event_url,
        },
    )


# ── CART: ADD / UPDATE ────────────────────────────────────────────────────────
@app.post("/cart/add")
async def cart_add(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    tier_id = int(form.get("id", 0))
    quantity = int(form.get("quantity", 1))

    tier = db.query(models.TicketTier).filter(models.TicketTier.id == tier_id).first()
    if not tier:
        raise HTTPException(404, "Ticket tier not found")

    event = db.query(models.Event).filter(models.Event.id == tier.event_id).first()
    cart: dict = request.session.get("cart", {})

    if quantity <= 0:
        cart.pop(str(tier_id), None)
    else:
        avail = (tier.capacity - tier.sold) if tier.capacity else 999
        cart[str(tier_id)] = {
            "tier_id": tier_id,
            "name": tier.name,
            "price": float(tier.price),
            "quantity": min(quantity, 10, avail),
            "event_id": event.id,
            "event_slug": event.slug,
            "event_title": event.title,
        }

    request.session["cart"] = cart
    return RedirectResponse(f"/e/{event.slug}", status_code=303)


# ── CART: REMOVE ──────────────────────────────────────────────────────────────
@app.post("/cart/remove")
async def cart_remove(request: Request):
    form = await request.form()
    item_id = str(form.get("item_id", ""))
    slug = form.get("slug", "")

    cart: dict = request.session.get("cart", {})
    cart.pop(item_id, None)
    request.session["cart"] = cart
    return RedirectResponse(f"/e/{slug}", status_code=303)


# ── CART: BULK UPDATE ─────────────────────────────────────────────────────────
@app.post("/cart/bulk-update")
async def cart_bulk_update(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    redirect_to = str(form.get("redirect", "/checkout"))
    cart: dict = request.session.get("cart", {})

    for key, value in form.items():
        if key.startswith("quantities["):
            tier_id = key[len("quantities[") : -1]
            qty = int(value) if str(value).isdigit() else 0
            if qty <= 0:
                cart.pop(tier_id, None)
            elif tier_id in cart:
                tier = (
                    db.query(models.TicketTier)
                    .filter(models.TicketTier.id == int(tier_id))
                    .first()
                )
                avail = (tier.capacity - tier.sold) if (tier and tier.capacity) else 999
                cart[tier_id]["quantity"] = min(qty, 10, avail)

    request.session["cart"] = cart
    return RedirectResponse(redirect_to, status_code=303)


# ── CHECKOUT ──────────────────────────────────────────────────────────────────
@app.get("/checkout")
async def checkout(request: Request):
    cart_items, cart_total, cart_count, _ = _cart_context(request)
    return templates.TemplateResponse(
        "checkout.html",
        {
            "request": request,
            "items": cart_items,
            "total": cart_total,
            "count": cart_count,
            "now": _now(),
            "search": "",
            "active_category": "",
        },
    )


@app.post("/checkout")
async def checkout_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    cart_items, cart_total, _, _ = _cart_context(request)

    if not cart_items:
        return RedirectResponse("/checkout", status_code=303)

    order_uuid = str(_uuid.uuid4())
    order = models.Order(
        uuid=order_uuid,
        name=form.get("name", ""),
        email=form.get("email", ""),
        phone=form.get("phone", ""),
        payment_method=form.get("payment_method", "M-Pesa"),
        total=cart_total,
        status="processing",
        items_json=json.dumps(cart_items),
    )
    db.add(order)
    db.commit()

    # Store order UUID + customer phone in session (for display on processing page)
    request.session["pending_order"] = {
        "uuid": order_uuid,
        "phone": form.get("phone", ""),
        "payment_method": form.get("payment_method", "M-Pesa"),
        "total": cart_total,
    }
    request.session["cart"] = {}  # clear cart

    return RedirectResponse(f"/checkout/{order_uuid}/processing", status_code=303)


# ── CHECKOUT: PROCESSING ──────────────────────────────────────────────────────
@app.get("/checkout/{order_uuid}/processing")
async def checkout_processing(
    request: Request,
    order_uuid: str,
    db: Session = Depends(get_db),
):
    order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
    if not order:
        raise HTTPException(404, "Order not found")

    # Already resolved — redirect straight away
    if order.status == "paid":
        return RedirectResponse(f"/checkout/{order_uuid}/thankyou", status_code=303)
    if order.status == "failed":
        return RedirectResponse(f"/checkout/{order_uuid}/failed", status_code=303)

    pending = request.session.get("pending_order", {})
    phone = pending.get("phone", order.phone)
    method = order.payment_method

    return templates.TemplateResponse(
        "checkout_processing.html",
        {
            "request": request,
            "order": order,
            "order_uuid": order_uuid,
            "phone": phone,
            "method": method,
            "now": _now(),
            "search": "",
            "active_category": "",
            "poll_url": f"/payments/status/{order_uuid}",
            "success_url": f"/checkout/{order_uuid}/thankyou",
            "failed_url": f"/checkout/{order_uuid}/failed",
        },
    )


# ── CHECKOUT: THANK YOU ───────────────────────────────────────────────────────
@app.get("/checkout/{order_uuid}/thankyou")
async def checkout_thankyou(
    request: Request,
    order_uuid: str,
    db: Session = Depends(get_db),
):
    order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
    if not order:
        raise HTTPException(404, "Order not found")

    # Mark paid if still processing (e.g. manual "I've paid" click)
    if order.status == "processing":
        order.status = "paid"
        db.commit()

    items = json.loads(order.items_json) if order.items_json else []
    return templates.TemplateResponse(
        "checkout_success.html",
        {
            "request": request,
            "order": order,
            "items": items,
            "now": _now(),
            "search": "",
            "active_category": "",
        },
    )


# ── CHECKOUT: FAILED ──────────────────────────────────────────────────────────
@app.get("/checkout/{order_uuid}/failed")
async def checkout_failed(
    request: Request,
    order_uuid: str,
    db: Session = Depends(get_db),
):
    order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
    if not order:
        raise HTTPException(404, "Order not found")

    if order.status == "processing":
        order.status = "failed"
        db.commit()

    items = json.loads(order.items_json) if order.items_json else []
    # Get first event slug for "Try again" button
    first_slug = items[0]["event_slug"] if items else ""

    support_wa = (
        f"https://wa.me/254707991991"
        f"?text={_qp(f'Hi, I need help with Order #{order.id} on TicketInit')}"
    )

    return templates.TemplateResponse(
        "checkout_failed.html",
        {
            "request": request,
            "order": order,
            "items": items,
            "first_slug": first_slug,
            "support_wa": support_wa,
            "now": _now(),
            "search": "",
            "active_category": "",
        },
    )


# ── PAYMENT STATUS POLLING API ────────────────────────────────────────────────
@app.get("/payments/status/{order_uuid}")
async def payment_status(order_uuid: str, db: Session = Depends(get_db)):
    """
    Polling endpoint called by the processing page every 5 s.
    In production: check your M-Pesa/payment gateway callback status here.
    Returns JSON: { "status": "processing" | "paid" | "failed" }
    """
    order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
    if not order:
        raise HTTPException(404, "Order not found")

    return JSONResponse(
        {
            "status": order.status,
            "order_id": order.id,
            "failure_reason": order.failure_reason,
        }
    )


# ── DEV: Simulate payment outcome (remove in production) ─────────────────────
@app.post("/dev/payments/{order_uuid}/simulate")
async def dev_simulate(order_uuid: str, status: str, db: Session = Depends(get_db)):
    """
    Development helper. POST /dev/payments/{uuid}/simulate?status=paid
    Accepted values: paid | failed
    """
    if os.getenv("APP_ENV") != "development":
        raise HTTPException(403, "Only available in development mode")
    order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
    if not order:
        raise HTTPException(404)
    if status not in ("paid", "failed", "processing"):
        raise HTTPException(400, "status must be paid | failed | processing")
    order.status = status
    db.commit()
    return {"ok": True, "uuid": order_uuid, "status": status}


# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}
