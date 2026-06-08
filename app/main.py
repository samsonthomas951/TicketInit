# import json
# import math
# import os
# import uuid as _uuid
# from datetime import datetime, timezone
# from typing import Optional
# from urllib.parse import quote_plus as _qp

# from fastapi import FastAPI, Request, Depends, HTTPException, Query
# from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
# from fastapi.staticfiles import StaticFiles
# from fastapi.templating import Jinja2Templates
# from sqlalchemy import or_, case, asc
# from sqlalchemy.orm import Session
# from starlette.middleware.sessions import SessionMiddleware
# from passlib.context import CryptContext

# from .database import SessionLocal, engine, get_db
# from .admin import router as admin_router
# from . import models
# from . import mpesa as mpesa_api
# from . import tickets as ticket_gen

# # ── Bootstrap ─────────────────────────────────────────────────────────────────
# models.Base.metadata.create_all(bind=engine)

# app = FastAPI(title="TicketInit", docs_url="/api/docs")
# SECRET_KEY = os.getenv("SECRET_KEY", "ticketinit-change-this-in-production")
# app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
# app.mount("/static", StaticFiles(directory="static"), name="static")
# templates = Jinja2Templates(directory="app/templates")

# EVENTS_PER_PAGE = 24
# APP_BASE_URL = os.getenv("APP_BASE_URL")

# # Safaricom STK result codes = definitive failure (not still-pending).
# # 1032 = still waiting for PIN — keep polling, do NOT mark as failed.
# MPESA_FAILURE_CODES = {
#     "1",     # Insufficient funds
#     "17",    # M-Pesa internal error
#     "20",    # Transaction expired
#     "1001",  # Unable to lock subscriber
#     "1019",  # Transaction expired
#     "1025",  # System internal error
#     "1037",  # Timeout waiting for user input
#     "2001",  # Wrong PIN
#     "9999",  # Generic error
# }

# app.include_router(admin_router)


# # ── Jinja2 filters ─────────────────────────────────────────────────────────────
# def fmt_date(value: datetime, fmt: str = "%a, %b %d, %Y") -> str:
#     if value is None:
#         return ""
#     if value.tzinfo is None:
#         value = value.replace(tzinfo=timezone.utc)
#     return value.strftime(fmt)


# def fmt_price(value) -> str:
#     if value is None:
#         return "Free"
#     try:
#         return f"KES {int(float(value)):,}"
#     except (TypeError, ValueError):
#         return str(value)


# def fmt_time(value: datetime) -> str:
#     if value is None:
#         return ""
#     if value.tzinfo is None:
#         value = value.replace(tzinfo=timezone.utc)
#     return value.strftime("%I:%M %p")


# templates.env.filters["fmt_date"] = fmt_date
# templates.env.filters["fmt_price"] = fmt_price
# templates.env.filters["fmt_time"] = fmt_time
# templates.env.filters["urlencode"] = lambda s: _qp(str(s) if s else "")


# # ── Helpers ───────────────────────────────────────────────────────────────────
# def _now() -> datetime:
#     return datetime.now(timezone.utc)


# def _is_past(event: models.Event) -> bool:
#     start = event.start_date
#     if start.tzinfo is None:
#         start = start.replace(tzinfo=timezone.utc)
#     return start < _now()


# def _cart_context(request: Request, event_id: int | None = None):
#     cart: dict = request.session.get("cart", {})
#     all_items = list(cart.values())
#     items = (
#         [i for i in all_items if i["event_id"] == event_id] if event_id else all_items
#     )
#     total = sum(i["price"] * i["quantity"] for i in items)
#     count = sum(i["quantity"] for i in items)
#     by_tier = {i["tier_id"]: i for i in items}
#     return items, total, count, by_tier


# templates.env.globals["is_past"] = _is_past


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

#     if category:
#         cat = db.query(models.Category).filter(models.Category.slug == category).first()
#         if cat:
#             q = q.filter(models.Event.category_id == cat.id)

#     total = q.count()
#     total_pages = max(1, math.ceil(total / EVENTS_PER_PAGE))
#     now = _now()

#     ordering = case((models.Event.start_date >= now, 0), else_=1)
#     events = (
#         q.order_by(ordering, asc(models.Event.start_date))
#         .offset((page - 1) * EVENTS_PER_PAGE)
#         .limit(EVENTS_PER_PAGE)
#         .all()
#     )

#     categories = db.query(models.Category).order_by(models.Category.name).all()
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


# # ── EVENT DETAIL ──────────────────────────────────────────────────────────────
# @app.get("/e/{slug}")
# async def event_detail(request: Request, slug: str, db: Session = Depends(get_db)):
#     event = (
#         db.query(models.Event)
#         .filter(models.Event.slug == slug, models.Event.is_published.is_(True))
#         .first()
#     )
#     if not event:
#         raise HTTPException(404, "Event not found")

#     tiers = (
#         db.query(models.TicketTier)
#         .filter(models.TicketTier.event_id == event.id)
#         .order_by(models.TicketTier.sort_order, models.TicketTier.price)
#         .all()
#     )

#     past = _is_past(event)
#     cart_items, cart_total, cart_count, cart_by_tier = _cart_context(request, event.id)

#     event_url = str(request.url)
#     share_whatsapp = f"https://wa.me/?text={_qp(event.title + ' – ' + event_url)}"
#     share_twitter = (
#         f"https://twitter.com/intent/tweet?url={_qp(event_url)}&text={_qp(event.title)}"
#     )

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


# # ── CART: ADD / UPDATE ────────────────────────────────────────────────────────
# @app.post("/cart/add")
# async def cart_add(request: Request, db: Session = Depends(get_db)):
#     form = await request.form()
#     tier_id = int(form.get("id", 0))
#     quantity = int(form.get("quantity", 1))

#     tier = db.query(models.TicketTier).filter(models.TicketTier.id == tier_id).first()
#     if not tier:
#         raise HTTPException(404, "Ticket tier not found")

#     event = db.query(models.Event).filter(models.Event.id == tier.event_id).first()
#     cart: dict = request.session.get("cart", {})

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
#             "event_venue": event.venue or event.location or "",
#         }

#     request.session["cart"] = cart
#     return RedirectResponse(f"/e/{event.slug}", status_code=303)


# # ── CART: REMOVE ──────────────────────────────────────────────────────────────
# @app.post("/cart/remove")
# async def cart_remove(request: Request):
#     form = await request.form()
#     item_id = str(form.get("item_id", ""))
#     slug = form.get("slug", "")

#     cart: dict = request.session.get("cart", {})
#     cart.pop(item_id, None)
#     request.session["cart"] = cart
#     return RedirectResponse(f"/e/{slug}", status_code=303)


# # ── CART: BULK UPDATE ─────────────────────────────────────────────────────────
# @app.post("/cart/bulk-update")
# async def cart_bulk_update(request: Request, db: Session = Depends(get_db)):
#     form = await request.form()
#     redirect_to = str(form.get("redirect", "/checkout"))
#     cart: dict = request.session.get("cart", {})

#     for key, value in form.items():
#         if key.startswith("quantities["):
#             tier_id = key[len("quantities["):-1]
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

#     request.session["cart"] = cart
#     return RedirectResponse(redirect_to, status_code=303)


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
#             "search": "",
#             "active_category": "",
#         },
#     )


# @app.post("/checkout")
# async def checkout_submit(request: Request, db: Session = Depends(get_db)):
#     form = await request.form()
#     cart_items, cart_total, _, _ = _cart_context(request)

#     if not cart_items:
#         return RedirectResponse("/checkout", status_code=303)

#     order_uuid = str(_uuid.uuid4())
#     payment_method = form.get("payment_method", "M-Pesa")
#     phone = form.get("phone", "")

#     order = models.Order(
#         uuid=order_uuid,
#         name=form.get("name", ""),
#         email=form.get("email", ""),
#         phone=phone,
#         payment_method=payment_method,
#         total=cart_total,
#         status="processing",
#         items_json=json.dumps(cart_items),
#     )
#     db.add(order)
#     db.commit()
#     db.refresh(order)

#     # ── Initiate M-Pesa STK push ──────────────────────────────────────────
#     stk_error = None
#     if payment_method == "M-Pesa":
#         result = mpesa_api.stk_push(
#             phone=phone,
#             amount=cart_total,
#             order_uuid=order_uuid,
#             description="TicketInit",
#         )
#         if result["success"]:
#             order.mpesa_checkout_request_id = result["checkout_request_id"]
#             db.commit()
#         else:
#             stk_error = result.get("error")
#             # Keep order in processing so user can retry manually

#     request.session["pending_order"] = {
#         "uuid": order_uuid,
#         "phone": phone,
#         "payment_method": payment_method,
#         "total": cart_total,
#         "stk_error": stk_error,
#     }
#     request.session["cart"] = {}

#     return RedirectResponse(f"/checkout/{order_uuid}/processing", status_code=303)


# # ── CHECKOUT: PROCESSING ──────────────────────────────────────────────────────
# @app.get("/checkout/{order_uuid}/processing")
# async def checkout_processing(
#     request: Request,
#     order_uuid: str,
#     db: Session = Depends(get_db),
# ):
#     order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
#     if not order:
#         raise HTTPException(404, "Order not found")

#     if order.status == "paid":
#         return RedirectResponse(f"/checkout/{order_uuid}/thankyou", status_code=303)
#     if order.status == "failed":
#         return RedirectResponse(f"/checkout/{order_uuid}/failed", status_code=303)

#     pending = request.session.get("pending_order", {})
#     phone = pending.get("phone", order.phone)
#     method = order.payment_method
#     stk_error = pending.get("stk_error")

#     return templates.TemplateResponse(
#         "checkout_processing.html",
#         {
#             "request": request,
#             "order": order,
#             "order_uuid": order_uuid,
#             "phone": phone,
#             "method": method,
#             "stk_error": stk_error,
#             "now": _now(),
#             "search": "",
#             "active_category": "",
#             "poll_url": f"/payments/status/{order_uuid}",
#             "success_url": f"/checkout/{order_uuid}/thankyou",
#             "failed_url": f"/checkout/{order_uuid}/failed",
#         },
#     )


# # ── CHECKOUT: THANK YOU ───────────────────────────────────────────────────────
# @app.get("/checkout/{order_uuid}/thankyou")
# async def checkout_thankyou(
#     request: Request,
#     order_uuid: str,
#     db: Session = Depends(get_db),
# ):
#     order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
#     if not order:
#         raise HTTPException(404, "Order not found")

#     if order.status == "processing":
#         order.status = "paid"
#         db.commit()

#     # Generate PDF tickets if not already done
#     items = json.loads(order.items_json) if order.items_json else []
#     existing_tickets = db.query(models.OrderTicket).filter(
#         models.OrderTicket.order_id == order.id
#     ).count()

#     if existing_tickets == 0 and items:
#         try:
#             _, ticket_records = ticket_gen.generate_pdf_tickets(
#                 order, items, base_url=APP_BASE_URL
#             )
#             for rec in ticket_records:
#                 db.add(models.OrderTicket(
#                     order_id=order.id,
#                     ticket_code=rec["ticket_code"],
#                     tier_name=rec["tier_name"],
#                     event_title=rec["event_title"],
#                 ))
#             db.commit()
#         except Exception as exc:
#             import logging
#             logging.getLogger(__name__).error("PDF generation error: %s", exc)

#     return templates.TemplateResponse(
#         "checkout_success.html",
#         {
#             "request": request,
#             "order": order,
#             "items": items,
#             "now": _now(),
#             "search": "",
#             "active_category": "",
#             "download_url": f"/tickets/download/{order_uuid}",
#         },
#     )


# # ── CHECKOUT: FAILED ──────────────────────────────────────────────────────────
# @app.get("/checkout/{order_uuid}/failed")
# async def checkout_failed(
#     request: Request,
#     order_uuid: str,
#     db: Session = Depends(get_db),
# ):
#     order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
#     if not order:
#         raise HTTPException(404, "Order not found")

#     if order.status == "processing":
#         order.status = "failed"
#         db.commit()

#     items = json.loads(order.items_json) if order.items_json else []
#     first_slug = items[0]["event_slug"] if items else ""
#     support_wa = (
#         f"https://wa.me/254707991991"
#         f"?text={_qp(f'Hi, I need help with Order #{order.id} on TicketInit')}"
#     )

#     return templates.TemplateResponse(
#         "checkout_failed.html",
#         {
#             "request": request,
#             "order": order,
#             "items": items,
#             "first_slug": first_slug,
#             "support_wa": support_wa,
#             "now": _now(),
#             "search": "",
#             "active_category": "",
#         },
#     )


# # ── PAYMENT STATUS POLLING API ────────────────────────────────────────────────
# @app.get("/payments/status/{order_uuid}")
# async def payment_status(order_uuid: str, db: Session = Depends(get_db)):
#     """
#     Polling endpoint called by the processing page every 5s.
#     For M-Pesa orders: also queries Daraja STK status directly.
#     """
#     order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
#     if not order:
#         raise HTTPException(404, "Order not found")

#     # If still processing + has an STK checkout ID, query Safaricom directly
#     if (
#         order.status == "processing"
#         and order.payment_method == "M-Pesa"
#         and order.mpesa_checkout_request_id
#     ):
#         stk = mpesa_api.query_stk_status(order.mpesa_checkout_request_id)
#         if stk["success"]:
#             order.status = "paid"
#             db.commit()
#             _ensure_tickets_generated(order, db)
#         elif stk["result_code"] in MPESA_FAILURE_CODES:
#             # Definitive failure — user cancelled, wrong PIN, insufficient funds, etc.
#             order.status = "failed"
#             order.failure_reason = stk["result_desc"]
#             db.commit()
#         # result_code "error" (network/auth issue) or "1032" (still pending)
#         # → do nothing, keep polling

#     return JSONResponse(
#         {
#             "status": order.status,
#             "order_id": order.id,
#             "failure_reason": order.failure_reason,
#         }
#     )


# # ── M-PESA DARAJA CALLBACK ────────────────────────────────────────────────────
# @app.post("/payments/mpesa/callback")
# async def mpesa_callback(request: Request, db: Session = Depends(get_db)):
#     """
#     Safaricom STK Push callback endpoint.
#     Must be publicly reachable (register with ngrok / real domain).
#     Register as: MPESA_CALLBACK_URL=https://yourdomain.co.ke/payments/mpesa/callback
#     """
#     try:
#         body = await request.json()
#     except Exception:
#         return JSONResponse({"ResultCode": 1, "ResultDesc": "Invalid JSON"}, status_code=400)

#     parsed = mpesa_api.parse_callback(body)
#     checkout_id = parsed["checkout_request_id"]

#     if not checkout_id:
#         return JSONResponse({"ResultCode": 0, "ResultDesc": "Accepted"})

#     order = db.query(models.Order).filter(
#         models.Order.mpesa_checkout_request_id == checkout_id
#     ).first()

#     if not order:
#         # Unknown order — still ACK to Safaricom so they don't retry
#         return JSONResponse({"ResultCode": 0, "ResultDesc": "Accepted"})

#     if parsed["result_code"] == 0:
#         # Payment successful
#         order.status = "paid"
#         order.mpesa_receipt = parsed["mpesa_receipt"]
#         db.commit()
#         _ensure_tickets_generated(order, db)
#     else:
#         # Payment failed / cancelled
#         order.status = "failed"
#         order.failure_reason = parsed["result_desc"]
#         db.commit()

#     # Always respond 200 with ResultCode 0 so Safaricom doesn't retry
#     return JSONResponse({"ResultCode": 0, "ResultDesc": "Accepted"})


# # ── TICKET DOWNLOAD ───────────────────────────────────────────────────────────
# @app.get("/tickets/download/{order_uuid}")
# async def download_tickets(order_uuid: str, db: Session = Depends(get_db)):
#     """Download the PDF tickets for a paid order."""
#     order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
#     if not order:
#         raise HTTPException(404, "Order not found")
#     if order.status != "paid":
#         raise HTTPException(403, "Tickets are only available for paid orders")

#     pdf_path = ticket_gen.TICKETS_DIR / f"{order_uuid}.pdf"

#     # Re-generate if missing
#     if not pdf_path.exists():
#         items = json.loads(order.items_json) if order.items_json else []
#         if not items:
#             raise HTTPException(404, "No ticket items found")
#         try:
#             ticket_gen.generate_pdf_tickets(order, items, base_url=APP_BASE_URL)
#         except Exception as exc:
#             raise HTTPException(500, f"Could not generate tickets: {exc}")

#     return FileResponse(
#         path=str(pdf_path),
#         media_type="application/pdf",
#         filename=f"TicketInit-Order-{order.id}.pdf",
#         headers={"Content-Disposition": f'attachment; filename="TicketInit-Order-{order.id}.pdf"'},
#     )


# # ── TICKET VERIFICATION (QR SCAN) ────────────────────────────────────────────
# @app.get("/tickets/verify/{ticket_code}")
# async def verify_ticket(
#     request: Request,
#     ticket_code: str,
#     db: Session = Depends(get_db),
# ):
#     """
#     Door-scan verification endpoint.
#     Renders a simple pass/fail page for event staff scanning QR codes.
#     """
#     ticket = db.query(models.OrderTicket).filter(
#         models.OrderTicket.ticket_code == ticket_code
#     ).first()

#     if not ticket:
#         return templates.TemplateResponse(
#             "ticket_verify.html",
#             {
#                 "request": request,
#                 "valid": False,
#                 "already_used": False,
#                 "ticket": None,
#                 "now": _now(),
#                 "search": "",
#                 "active_category": "",
#             },
#         )

#     order = db.query(models.Order).filter(models.Order.id == ticket.order_id).first()
#     already_used = ticket.used

#     # Mark as used on first scan
#     if not ticket.used:
#         ticket.used = True
#         ticket.used_at = _now()
#         db.commit()

#     return templates.TemplateResponse(
#         "ticket_verify.html",
#         {
#             "request": request,
#             "valid": True,
#             "already_used": already_used,
#             "ticket": ticket,
#             "order": order,
#             "now": _now(),
#             "search": "",
#             "active_category": "",
#         },
#     )


# # ── DEV: Simulate payment outcome ─────────────────────────────────────────────
# @app.post("/dev/payments/{order_uuid}/simulate")
# async def dev_simulate(order_uuid: str, status: str, db: Session = Depends(get_db)):
#     if os.getenv("APP_ENV") != "development":
#         raise HTTPException(403, "Only available in development mode")
#     order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
#     if not order:
#         raise HTTPException(404)
#     if status not in ("paid", "failed", "processing"):
#         raise HTTPException(400, "status must be paid | failed | processing")
#     order.status = status
#     db.commit()
#     if status == "paid":
#         _ensure_tickets_generated(order, db)
#     return {"ok": True, "uuid": order_uuid, "status": status}


# # ── HEALTH ────────────────────────────────────────────────────────────────────
# @app.get("/health")
# async def health():
#     return {"status": "ok"}


# # ── Startup ───────────────────────────────────────────────────────────────────
# @app.on_event("startup")
# def create_default_admin():
#     db = SessionLocal()
#     try:
#         if not db.query(models.AdminUser).first():
#             pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
#             hashed_pw = pwd_ctx.hash("admin")
#             db.add(models.AdminUser(username="admin", password_hash=hashed_pw))
#             db.commit()
#             print("Default admin created! Username: admin | Password: admin")
#     finally:
#         db.close()


# # ── Internal helpers ──────────────────────────────────────────────────────────
# def _ensure_tickets_generated(order: models.Order, db: Session) -> None:
#     """Generate PDF tickets + OrderTicket rows if not already done."""
#     existing = db.query(models.OrderTicket).filter(
#         models.OrderTicket.order_id == order.id
#     ).count()
#     if existing > 0:
#         return
#     items = json.loads(order.items_json) if order.items_json else []
#     if not items:
#         return
#     try:
#         _, ticket_records = ticket_gen.generate_pdf_tickets(
#             order, items, base_url=APP_BASE_URL
#         )
#         for rec in ticket_records:
#             db.add(models.OrderTicket(
#                 order_id=order.id,
#                 ticket_code=rec["ticket_code"],
#                 tier_name=rec["tier_name"],
#                 event_title=rec["event_title"],
#             ))
#         db.commit()
#     except Exception as exc:
#         import logging
#         logging.getLogger(__name__).error("Ticket generation error: %s", exc)

"""
TicketInit – Main FastAPI application
"""
import json
import os
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.database import get_db
from app import models
from app.admin import router as admin_router
from app import mpesa as mpesa_module
from app.tickets import generate_pdf_tickets, TICKETS_DIR

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="TicketInit")

SECRET_KEY   = os.getenv("SECRET_KEY", "ticketinit-change-this-in-production")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
APP_ENV      = os.getenv("APP_ENV", "development")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="ticketinit_session")
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="app/templates")
app.include_router(admin_router)

# ── Template filters ──────────────────────────────────────────────────────────
def fmt_date(value: datetime, fmt: str = "%a, %b %d, %Y") -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime(fmt)

def fmt_time(value: datetime, fmt: str = "%I:%M %p") -> str:
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

def is_past(event) -> bool:
    now = datetime.now(timezone.utc)
    end = event.end_date or event.start_date
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return end < now

templates.env.filters["fmt_date"]  = fmt_date
templates.env.filters["fmt_time"]  = fmt_time
templates.env.filters["fmt_price"] = fmt_price
templates.env.globals["is_past"]   = is_past
templates.env.globals["now"]       = datetime.now(timezone.utc)

# ── Cart helpers ──────────────────────────────────────────────────────────────
def _get_cart(request: Request) -> dict:
    return request.session.get("cart", {})

def _save_cart(request: Request, cart: dict):
    request.session["cart"] = cart

def _cart_items(cart: dict, db: Session) -> list[dict]:
    items = []
    for tier_id_str, qty in cart.items():
        tier = db.query(models.TicketTier).filter(
            models.TicketTier.id == int(tier_id_str)
        ).first()
        if not tier or qty <= 0:
            continue
        event = db.query(models.Event).filter(
            models.Event.id == tier.event_id
        ).first()
        if not event:
            continue
        items.append({
            "tier_id":     tier.id,
            "event_id":    event.id,
            "event_slug":  event.slug,
            "event_title": event.title,
            "event_venue": event.venue or "",
            "name":        tier.name,
            "price":       float(tier.price),
            "quantity":    qty,
        })
    return items

def _cart_total(items: list[dict]) -> float:
    return sum(i["price"] * i["quantity"] for i in items)


# ── Index ─────────────────────────────────────────────────────────────────────
@app.get("/")
async def index(
    request: Request,
    page: int = 1,
    search: str = "",
    category: str = "",
    db: Session = Depends(get_db),
):
    templates.env.globals["now"] = datetime.now(timezone.utc)
    PER_PAGE = 12
    q = db.query(models.Event).filter(models.Event.is_published.is_(True))
    if search:
        q = q.filter(models.Event.title.ilike(f"%{search}%"))
    if category:
        cat = db.query(models.Category).filter(models.Category.slug == category).first()
        if cat:
            q = q.filter(models.Event.category_id == cat.id)

    total       = q.count()
    total_pages = max(1, -(-total // PER_PAGE))
    events      = (
        q.order_by(models.Event.start_date.asc())
         .offset((page - 1) * PER_PAGE)
         .limit(PER_PAGE)
         .all()
    )
    categories = db.query(models.Category).order_by(models.Category.name).all()

    return templates.TemplateResponse("index.html", {
        "request":         request,
        "events":          events,
        "categories":      categories,
        "active_category": category,
        "search":          search,
        "page":            page,
        "total":           total,
        "total_pages":     total_pages,
        "pages":           list(range(1, total_pages + 1)),
    })


# ── Event detail ──────────────────────────────────────────────────────────────
@app.get("/e/{slug}")
async def event_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    templates.env.globals["now"] = datetime.now(timezone.utc)
    event = db.query(models.Event).filter(
        models.Event.slug == slug,
        models.Event.is_published.is_(True),
    ).first()
    if not event:
        raise HTTPException(404)

    tiers = (
        db.query(models.TicketTier)
        .filter(models.TicketTier.event_id == event.id)
        .order_by(models.TicketTier.sort_order)
        .all()
    )
    past         = is_past(event)
    cart         = _get_cart(request)
    cart_items   = _cart_items(cart, db)
    cart_items   = [i for i in cart_items if i["event_id"] == event.id]
    cart_total   = _cart_total(cart_items)
    cart_count   = sum(i["quantity"] for i in cart_items)
    cart_by_tier = {i["tier_id"]: i for i in cart_items}

    event_url      = f"{APP_BASE_URL}/e/{slug}"
    share_whatsapp = f"https://api.whatsapp.com/send?text={event.title}%20{event_url}"
    share_twitter  = f"https://twitter.com/intent/tweet?text={event.title}&url={event_url}"

    return templates.TemplateResponse("event_detail.html", {
        "request":        request,
        "event":          event,
        "tiers":          tiers,
        "past":           past,
        "cart_items":     cart_items,
        "cart_total":     cart_total,
        "cart_count":     cart_count,
        "cart_by_tier":   cart_by_tier,
        "event_url":      event_url,
        "share_whatsapp": share_whatsapp,
        "share_twitter":  share_twitter,
    })


# ── Cart ──────────────────────────────────────────────────────────────────────
@app.post("/cart/add")
async def cart_add(
    request: Request,
    id: int = Form(...),
    slug: str = Form(...),
    quantity: int = Form(1),
    db: Session = Depends(get_db),
):
    tier = db.query(models.TicketTier).filter(models.TicketTier.id == id).first()
    if not tier:
        raise HTTPException(404)
    cart = _get_cart(request)
    if quantity <= 0:
        cart.pop(str(id), None)
    else:
        cart[str(id)] = quantity
    _save_cart(request, cart)
    return RedirectResponse(f"/e/{slug}", status_code=303)


@app.post("/cart/remove")
async def cart_remove(
    request: Request,
    item_id: int = Form(...),
    slug: str = Form(...),
):
    cart = _get_cart(request)
    cart.pop(str(item_id), None)
    _save_cart(request, cart)
    ref = request.headers.get("referer", f"/e/{slug}")
    return RedirectResponse(ref, status_code=303)


@app.post("/cart/bulk-update")
async def cart_bulk_update(
    request: Request,
    redirect: str = Form("/checkout"),
):
    form   = await request.form()
    cart   = _get_cart(request)
    prefix = "quantities["
    for key, val in form.items():
        if key.startswith(prefix) and key.endswith("]"):
            tier_id = key[len(prefix):-1]
            try:
                qty = int(val)
                if qty <= 0:
                    cart.pop(tier_id, None)
                else:
                    cart[tier_id] = qty
            except ValueError:
                pass
    _save_cart(request, cart)
    return RedirectResponse(redirect, status_code=303)


# ── Checkout ──────────────────────────────────────────────────────────────────
@app.get("/checkout")
async def checkout_get(request: Request, db: Session = Depends(get_db)):
    templates.env.globals["now"] = datetime.now(timezone.utc)
    cart  = _get_cart(request)
    items = _cart_items(cart, db)
    total = _cart_total(items)
    return templates.TemplateResponse("checkout.html", {
        "request": request,
        "items":   items,
        "total":   total,
    })


@app.post("/checkout")
async def checkout_post(
    request: Request,
    name:           str = Form(...),
    email:          str = Form(...),
    phone:          str = Form(...),
    payment_method: str = Form(...),
    db: Session = Depends(get_db),
):
    cart  = _get_cart(request)
    items = _cart_items(cart, db)
    if not items:
        return RedirectResponse("/checkout", status_code=303)

    total      = _cart_total(items)
    order_uuid = str(_uuid.uuid4())

    order = models.Order(
        uuid           = order_uuid,
        name           = name.strip(),
        email          = email.strip(),
        phone          = phone.strip(),
        payment_method = payment_method,
        total          = total,
        status         = "pending",
        items_json     = json.dumps(items),
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    stk_error = None
    if payment_method == "M-Pesa":
        result = mpesa_module.stk_push(
            phone      = phone,
            amount     = total,
            order_uuid = order_uuid,
        )
        if result["success"]:
            order.mpesa_checkout_request_id = result["checkout_request_id"]
            order.status = "processing"
        else:
            stk_error    = result.get("error", "STK push failed")
            order.status = "processing"   # still wait — user may pay manually
        db.commit()

    # Clear cart after successful order creation
    _save_cart(request, {})

    poll_url        = f"/payments/status/{order_uuid}"
    success_url     = f"/orders/{order_uuid}/success"
    failed_url      = f"/orders/{order_uuid}/failed"
    mpesa_shortcode = mpesa_module._shortcode()

    return templates.TemplateResponse("checkout_processing.html", {
        "request":         request,
        "order":           order,
        "method":          payment_method,
        "phone":           phone,
        "stk_error":       stk_error,
        "poll_url":        poll_url,
        "success_url":     success_url,
        "failed_url":      failed_url,
        "mpesa_shortcode": mpesa_shortcode,
    })


# ── Payment polling ───────────────────────────────────────────────────────────
@app.get("/payments/status/{order_uuid}")
async def payment_status(order_uuid: str, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
    if not order:
        raise HTTPException(404)

    # If the callback already finalised us, just return
    if order.status in ("paid", "failed", "cancelled"):
        return JSONResponse({"status": order.status})

    # FIX: Only call query_stk_status when we have a checkout_request_id.
    # Never mark as failed here — only the callback or explicit user action
    # should do that. The STK query is unreliable in the first ~10 seconds.
    if order.mpesa_checkout_request_id:
        result = mpesa_module.query_stk_status(order.mpesa_checkout_request_id)
        rc = result.get("result_code", "")

        if result.get("success") or rc == "0":
            # Confirmed paid via query (callback may have been missed)
            _finalise_order(order, db)
        elif rc == "1032":
            # User explicitly cancelled the STK prompt on their phone
            order.status         = "failed"
            order.failure_reason = "M-Pesa request cancelled by user"
            db.commit()
        # All other codes (including "", "error", "1037" timeout) →
        # keep status as "processing" and let the poller retry

    return JSONResponse({"status": order.status})


# ── M-Pesa callback ───────────────────────────────────────────────────────────
@app.post("/payments/mpesa/callback")
async def mpesa_callback(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ResultCode": 1, "ResultDesc": "Bad JSON"})

    parsed = mpesa_module.parse_callback(body)
    if not parsed["checkout_request_id"]:
        return JSONResponse({"ResultCode": 0, "ResultDesc": "OK"})

    order = db.query(models.Order).filter(
        models.Order.mpesa_checkout_request_id == parsed["checkout_request_id"]
    ).first()
    if not order:
        return JSONResponse({"ResultCode": 0, "ResultDesc": "OK"})

    if parsed["result_code"] == 0:
        order.mpesa_receipt = parsed["mpesa_receipt"]
        _finalise_order(order, db)
    else:
        order.status         = "failed"
        order.failure_reason = parsed["result_desc"]
        db.commit()

    return JSONResponse({"ResultCode": 0, "ResultDesc": "OK"})


def _finalise_order(order: models.Order, db: Session):
    """Mark order paid and generate PDF tickets. Idempotent."""
    if order.status == "paid":
        return

    order.status = "paid"
    db.commit()

    items = json.loads(order.items_json or "[]")
    try:
        _pdf_path, ticket_records = generate_pdf_tickets(
            order, items, base_url=APP_BASE_URL,
        )
        for rec in ticket_records:
            db.add(models.OrderTicket(
                order_id    = order.id,
                ticket_code = rec["ticket_code"],
                tier_name   = rec["tier_name"],
                event_title = rec["event_title"],
            ))
        db.commit()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Ticket generation failed: %s", exc)


# ── Order success / failed pages ──────────────────────────────────────────────
@app.get("/orders/{order_uuid}/success")
async def order_success(
    request: Request, order_uuid: str, db: Session = Depends(get_db),
):
    templates.env.globals["now"] = datetime.now(timezone.utc)
    order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
    if not order:
        raise HTTPException(404)

    # Auto-finalise if user clicked "I've already paid"
    if order.status in ("processing", "pending"):
        _finalise_order(order, db)
        db.refresh(order)

    items        = json.loads(order.items_json or "[]")
    download_url = f"/orders/{order_uuid}/download"

    return templates.TemplateResponse("checkout_success.html", {
        "request":      request,
        "order":        order,
        "items":        items,
        "download_url": download_url,
    })


@app.get("/orders/{order_uuid}/failed")
async def order_failed(
    request: Request, order_uuid: str, db: Session = Depends(get_db),
):
    templates.env.globals["now"] = datetime.now(timezone.utc)
    order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
    if not order:
        raise HTTPException(404)

    if order.status not in ("failed", "cancelled"):
        order.status = "failed"
        db.commit()

    items      = json.loads(order.items_json or "[]")
    first_slug = items[0].get("event_slug") if items else None
    support_wa = f"https://api.whatsapp.com/send?phone=254707991991&text=Help+with+order+%23{order.id}"

    return templates.TemplateResponse("checkout_failed.html", {
        "request":    request,
        "order":      order,
        "items":      items,
        "first_slug": first_slug,
        "support_wa": support_wa,
    })


# ── Ticket download — serves PDF file ────────────────────────────────────────
@app.get("/orders/{order_uuid}/download")
async def order_download(order_uuid: str, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
    if not order:
        raise HTTPException(404, detail="Order not found")
    if order.status != "paid":
        raise HTTPException(403, detail="Tickets only available for paid orders")

    pdf_path = TICKETS_DIR / f"{order_uuid}.pdf"

    # Regenerate if missing (edge case)
    if not pdf_path.exists():
        items = json.loads(order.items_json or "[]")
        if not items:
            raise HTTPException(404, detail="No items in order")
        try:
            pdf_path, ticket_records = generate_pdf_tickets(
                order, items, base_url=APP_BASE_URL,
            )
            existing = {
                t.ticket_code for t in
                db.query(models.OrderTicket)
                  .filter(models.OrderTicket.order_id == order.id).all()
            }
            for rec in ticket_records:
                if rec["ticket_code"] not in existing:
                    db.add(models.OrderTicket(
                        order_id    = order.id,
                        ticket_code = rec["ticket_code"],
                        tier_name   = rec["tier_name"],
                        event_title = rec["event_title"],
                    ))
            db.commit()
        except Exception as exc:
            raise HTTPException(500, detail=f"Could not generate tickets: {exc}")

    if not pdf_path.exists():
        raise HTTPException(404, detail="Ticket file not found")

    safe_name = f"TicketInit-Order-{order.id}.pdf"
    return FileResponse(
        path        = str(pdf_path),
        media_type  = "application/pdf",
        filename    = safe_name,
        headers     = {
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Cache-Control":       "no-store",
        },
    )


# ── Ticket verification ───────────────────────────────────────────────────────
@app.get("/tickets/verify/{ticket_code}")
async def ticket_verify(
    request: Request, ticket_code: str, db: Session = Depends(get_db),
):
    templates.env.globals["now"] = datetime.now(timezone.utc)
    ticket = db.query(models.OrderTicket).filter(
        models.OrderTicket.ticket_code == ticket_code
    ).first()

    if not ticket:
        return templates.TemplateResponse("ticket_verify.html", {
            "request": request, "valid": False,
            "already_used": False, "ticket": None, "order": None,
        })

    order        = db.query(models.Order).filter(models.Order.id == ticket.order_id).first()
    already_used = ticket.used

    if not already_used:
        ticket.used    = True
        ticket.used_at = datetime.now(timezone.utc)
        db.commit()

    return templates.TemplateResponse("ticket_verify.html", {
        "request": request, "valid": True,
        "already_used": already_used, "ticket": ticket, "order": order,
    })


# ── Dev simulator ─────────────────────────────────────────────────────────────
if APP_ENV == "development":
    @app.post("/dev/payments/{order_uuid}/simulate")
    async def dev_simulate(
        order_uuid: str, status: str = "paid", db: Session = Depends(get_db),
    ):
        order = db.query(models.Order).filter(models.Order.uuid == order_uuid).first()
        if not order:
            raise HTTPException(404)
        if status == "paid":
            _finalise_order(order, db)
        else:
            order.status         = "failed"
            order.failure_reason = "Simulated failure"
            db.commit()
        return JSONResponse({"status": order.status})


# ── Refund policy ─────────────────────────────────────────────────────────────
@app.get("/refund-policy")
async def refund_policy(request: Request):
    return templates.TemplateResponse("base.html", {
        "request": request,
    })