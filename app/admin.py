"""
Admin blueprint — all routes prefixed /admin
Auth: session cookie (username stored in session["admin"])
"""
import json
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from slugify import slugify
from sqlalchemy.orm import Session

from .database import get_db
from . import models

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates/admin")

def fmt_date(value: datetime, fmt: str = "%a, %b %d, %Y") -> str:
    if value is None: return ""
    if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
    return value.strftime(fmt)

def fmt_price(value) -> str:
    if value is None: return "Free"
    try: return f"KES {int(float(value)):,}"
    except (TypeError, ValueError): return str(value)

templates.env.filters["fmt_date"] = fmt_date
templates.env.filters["fmt_price"] = fmt_price
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_PER_PAGE = 20


# ── Auth helpers ──────────────────────────────────────────────────────────────
def _logged_in(request: Request) -> bool:
    return bool(request.session.get("admin"))


def _require_auth(request: Request):
    if not _logged_in(request):
        raise HTTPException(status_code=307,
                            headers={"Location": "/admin/login"})


def _redirect_login():
    return RedirectResponse("/admin/login", status_code=303)


# ── Login ──────────────────────────────────────────────────────────────────────
@router.get("/login")
async def admin_login(request: Request, error: str = ""):
    if _logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request, "error": error
    })


@router.post("/login")
async def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(models.AdminUser).filter(
        models.AdminUser.username == username,
        models.AdminUser.is_active.is_(True),
    ).first()

    if not user or not pwd_ctx.verify(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password."
        }, status_code=401)

    request.session["admin"] = {"id": user.id, "username": user.username}
    return RedirectResponse("/admin", status_code=303)


@router.get("/logout")
async def admin_logout(request: Request):
    request.session.pop("admin", None)
    return RedirectResponse("/admin/login", status_code=303)


# ── Dashboard ─────────────────────────────────────────────────────────────────
@router.get("")
@router.get("/")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if not _logged_in(request):
        return _redirect_login()

    total_events   = db.query(models.Event).count()
    upcoming       = db.query(models.Event).filter(
        models.Event.start_date >= datetime.now(timezone.utc)).count()
    total_orders   = db.query(models.Order).count()
    paid_orders    = db.query(models.Order).filter(
        models.Order.status == "paid").count()
    revenue        = db.query(
        models.Order.total).filter(models.Order.status == "paid").all()
    total_revenue  = sum(float(r[0]) for r in revenue)
    categories     = db.query(models.Category).order_by(models.Category.name).all()

    recent_orders = (
        db.query(models.Order)
        .order_by(models.Order.created_at.desc())
        .limit(5).all()
    )

    return templates.TemplateResponse("dashboard.html", {
        "request":       request,
        "total_events":  total_events,
        "upcoming":      upcoming,
        "total_orders":  total_orders,
        "paid_orders":   paid_orders,
        "total_revenue": total_revenue,
        "categories":    categories,
        "recent_orders": recent_orders,
        "admin":         request.session["admin"],
    })


# ── Events list ───────────────────────────────────────────────────────────────
@router.get("/events")
async def admin_events(
    request: Request,
    page: int = Query(1, ge=1),
    search: str = Query(""),
    db: Session = Depends(get_db),
):
    if not _logged_in(request):
        return _redirect_login()

    q = db.query(models.Event)
    if search:
        like = f"%{search}%"
        q = q.filter(models.Event.title.ilike(like))

    total       = q.count()
    total_pages = max(1, -(-total // ADMIN_PER_PAGE))   # ceil division

    events = (
        q.order_by(models.Event.start_date.desc())
        .offset((page - 1) * ADMIN_PER_PAGE)
        .limit(ADMIN_PER_PAGE)
        .all()
    )
    categories = db.query(models.Category).order_by(models.Category.name).all()

    return templates.TemplateResponse("events_list.html", {
        "request":    request,
        "events":     events,
        "total":      total,
        "page":       page,
        "total_pages":total_pages,
        "pages":      list(range(1, total_pages + 1)),
        "search":     search,
        "categories": categories,
        "admin":      request.session["admin"],
    })


# ── Create event ──────────────────────────────────────────────────────────────
@router.get("/events/new")
async def admin_event_new(request: Request, db: Session = Depends(get_db)):
    if not _logged_in(request):
        return _redirect_login()
    categories = db.query(models.Category).order_by(models.Category.name).all()
    return templates.TemplateResponse("event_form.html", {
        "request":    request,
        "event":      None,
        "tiers":      [],
        "categories": categories,
        "errors":     [],
        "admin":      request.session["admin"],
        "mode":       "create",
    })


@router.post("/events/new")
async def admin_event_create(
    request: Request,
    db: Session = Depends(get_db),
    title:         str = Form(...),
    description:   str = Form(""),
    poster_url:    str = Form(""),
    venue:         str = Form(""),
    location:      str = Form(""),
    start_date:    str = Form(...),
    end_date:      str = Form(""),
    is_free:       str = Form("off"),
    category_id:   str = Form(""),
    organizer:     str = Form(""),
    is_published:  str = Form("off"),
    # Ticket tiers sent as tier_name[], tier_price[], tier_capacity[], tier_desc[]
):
    if not _logged_in(request):
        return _redirect_login()

    errors = []

    # Parse dates
    try:
        start_dt = datetime.fromisoformat(start_date)
    except ValueError:
        errors.append("Invalid start date/time.")
        start_dt = None

    end_dt = None
    if end_date.strip():
        try:
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            errors.append("Invalid end date/time.")

    # Build slug (ensure unique)
    base_slug = slugify(title)
    slug      = base_slug
    suffix    = 1
    while db.query(models.Event).filter(models.Event.slug == slug).first():
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    form_data = await request.form()
    tier_names     = form_data.getlist("tier_name[]")
    tier_prices    = form_data.getlist("tier_price[]")
    tier_capacities= form_data.getlist("tier_capacity[]")
    tier_descs     = form_data.getlist("tier_desc[]")

    # Validate tiers
    parsed_tiers = []
    for i, (name, price) in enumerate(zip(tier_names, tier_prices)):
        if not name.strip():
            continue
        try:
            p = float(price)
        except ValueError:
            errors.append(f"Invalid price for tier "{name}".")
            continue
        cap_raw = tier_capacities[i] if i < len(tier_capacities) else ""
        cap = int(cap_raw) if cap_raw.strip().isdigit() else None
        desc = tier_descs[i] if i < len(tier_descs) else ""
        parsed_tiers.append({"name": name.strip(), "price": p,
                              "capacity": cap, "description": desc, "sort_order": i})

    if errors:
        categories = db.query(models.Category).order_by(models.Category.name).all()
        return templates.TemplateResponse("event_form.html", {
            "request": request, "event": None, "tiers": [],
            "categories": categories, "errors": errors,
            "admin": request.session["admin"], "mode": "create",
        }, status_code=422)

    free     = is_free == "on"
    min_price = None if free or not parsed_tiers else min(t["price"] for t in parsed_tiers)

    event = models.Event(
        slug         = slug,
        title        = title.strip(),
        description  = description.strip() or None,
        poster_url   = poster_url.strip() or None,
        venue        = venue.strip() or None,
        location     = location.strip() or None,
        start_date   = start_dt,
        end_date     = end_dt,
        is_free      = free,
        min_price    = min_price,
        category_id  = int(category_id) if category_id.strip().isdigit() else None,
        organizer    = organizer.strip() or None,
        is_published = is_published == "on",
    )
    db.add(event)
    db.flush()   # get event.id

    for t in parsed_tiers:
        db.add(models.TicketTier(
            event_id    = event.id,
            name        = t["name"],
            price       = t["price"],
            capacity    = t["capacity"],
            description = t["description"] or None,
            sort_order  = t["sort_order"],
        ))

    db.commit()
    return RedirectResponse(f"/admin/events/{event.id}/edit?saved=1", status_code=303)


# ── Edit event ────────────────────────────────────────────────────────────────
@router.get("/events/{event_id}/edit")
async def admin_event_edit(
    request: Request,
    event_id: int,
    saved: str = "",
    db: Session = Depends(get_db),
):
    if not _logged_in(request):
        return _redirect_login()
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(404)
    tiers = (db.query(models.TicketTier)
             .filter(models.TicketTier.event_id == event_id)
             .order_by(models.TicketTier.sort_order).all())
    categories = db.query(models.Category).order_by(models.Category.name).all()
    return templates.TemplateResponse("event_form.html", {
        "request":    request,
        "event":      event,
        "tiers":      tiers,
        "categories": categories,
        "errors":     [],
        "saved":      bool(saved),
        "admin":      request.session["admin"],
        "mode":       "edit",
    })


@router.post("/events/{event_id}/edit")
async def admin_event_update(
    request: Request,
    event_id: int,
    db: Session = Depends(get_db),
    title:        str = Form(...),
    description:  str = Form(""),
    poster_url:   str = Form(""),
    venue:        str = Form(""),
    location:     str = Form(""),
    start_date:   str = Form(...),
    end_date:     str = Form(""),
    is_free:      str = Form("off"),
    category_id:  str = Form(""),
    organizer:    str = Form(""),
    is_published: str = Form("off"),
):
    if not _logged_in(request):
        return _redirect_login()

    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(404)

    errors = []
    try:
        start_dt = datetime.fromisoformat(start_date)
    except ValueError:
        errors.append("Invalid start date/time.")
        start_dt = event.start_date

    end_dt = None
    if end_date.strip():
        try:
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            errors.append("Invalid end date/time.")

    form_data = await request.form()
    tier_names      = form_data.getlist("tier_name[]")
    tier_prices     = form_data.getlist("tier_price[]")
    tier_capacities = form_data.getlist("tier_capacity[]")
    tier_descs      = form_data.getlist("tier_desc[]")
    tier_ids        = form_data.getlist("tier_id[]")   # existing IDs ("" for new)

    parsed_tiers = []
    for i, (name, price) in enumerate(zip(tier_names, tier_prices)):
        if not name.strip():
            continue
        try:
            p = float(price)
        except ValueError:
            errors.append(f"Invalid price for tier "{name}".")
            continue
        cap_raw = tier_capacities[i] if i < len(tier_capacities) else ""
        cap  = int(cap_raw) if cap_raw.strip().isdigit() else None
        desc = tier_descs[i] if i < len(tier_descs) else ""
        tid  = tier_ids[i] if i < len(tier_ids) else ""
        parsed_tiers.append({
            "id": int(tid) if tid.strip().isdigit() else None,
            "name": name.strip(), "price": p,
            "capacity": cap, "description": desc, "sort_order": i,
        })

    if errors:
        tiers = (db.query(models.TicketTier)
                 .filter(models.TicketTier.event_id == event_id)
                 .order_by(models.TicketTier.sort_order).all())
        categories = db.query(models.Category).order_by(models.Category.name).all()
        return templates.TemplateResponse("event_form.html", {
            "request": request, "event": event, "tiers": tiers,
            "categories": categories, "errors": errors,
            "admin": request.session["admin"], "mode": "edit",
        }, status_code=422)

    free      = is_free == "on"
    min_price = None if free or not parsed_tiers else min(t["price"] for t in parsed_tiers)

    event.title        = title.strip()
    event.description  = description.strip() or None
    event.poster_url   = poster_url.strip() or None
    event.venue        = venue.strip() or None
    event.location     = location.strip() or None
    event.start_date   = start_dt
    event.end_date     = end_dt
    event.is_free      = free
    event.min_price    = min_price
    event.category_id  = int(category_id) if category_id.strip().isdigit() else None
    event.organizer    = organizer.strip() or None
    event.is_published = is_published == "on"

    # Sync tiers: delete removed, update existing, create new
    submitted_ids = {t["id"] for t in parsed_tiers if t["id"]}
    for existing in db.query(models.TicketTier).filter(
            models.TicketTier.event_id == event_id).all():
        if existing.id not in submitted_ids:
            db.delete(existing)

    for t in parsed_tiers:
        if t["id"]:
            tier = db.query(models.TicketTier).filter(
                models.TicketTier.id == t["id"]).first()
            if tier:
                tier.name = t["name"]; tier.price = t["price"]
                tier.capacity = t["capacity"]; tier.description = t["description"]
                tier.sort_order = t["sort_order"]
        else:
            db.add(models.TicketTier(
                event_id=event.id, name=t["name"], price=t["price"],
                capacity=t["capacity"], description=t["description"] or None,
                sort_order=t["sort_order"],
            ))

    db.commit()
    return RedirectResponse(f"/admin/events/{event_id}/edit?saved=1", status_code=303)


# ── Toggle publish ────────────────────────────────────────────────────────────
@router.post("/events/{event_id}/toggle-publish")
async def admin_toggle_publish(
    request: Request, event_id: int, db: Session = Depends(get_db)
):
    if not _logged_in(request):
        return _redirect_login()
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if event:
        event.is_published = not event.is_published
        db.commit()
    return RedirectResponse("/admin/events", status_code=303)


# ── Delete event ──────────────────────────────────────────────────────────────
@router.post("/events/{event_id}/delete")
async def admin_event_delete(
    request: Request, event_id: int, db: Session = Depends(get_db)
):
    if not _logged_in(request):
        return _redirect_login()
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if event:
        db.delete(event)
        db.commit()
    return RedirectResponse("/admin/events", status_code=303)


# ── Categories ────────────────────────────────────────────────────────────────
@router.get("/categories")
async def admin_categories(request: Request, db: Session = Depends(get_db)):
    if not _logged_in(request):
        return _redirect_login()
    categories = db.query(models.Category).order_by(models.Category.name).all()
    return templates.TemplateResponse("categories.html", {
        "request": request, "categories": categories,
        "admin": request.session["admin"],
    })


@router.post("/categories/new")
async def admin_category_create(
    request: Request,
    name: str = Form(...),
    icon: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _logged_in(request):
        return _redirect_login()
    slug = slugify(name)
    if not db.query(models.Category).filter(models.Category.slug == slug).first():
        db.add(models.Category(name=name.strip(), slug=slug,
                               icon=icon.strip() or None))
        db.commit()
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/categories/{cat_id}/delete")
async def admin_category_delete(
    request: Request, cat_id: int, db: Session = Depends(get_db)
):
    if not _logged_in(request):
        return _redirect_login()
    cat = db.query(models.Category).filter(models.Category.id == cat_id).first()
    if cat:
        db.delete(cat)
        db.commit()
    return RedirectResponse("/admin/categories", status_code=303)


# ── Orders list ───────────────────────────────────────────────────────────────
@router.get("/orders")
async def admin_orders(
    request: Request,
    page: int = Query(1, ge=1),
    status: str = Query(""),
    db: Session = Depends(get_db),
):
    if not _logged_in(request):
        return _redirect_login()

    q = db.query(models.Order)
    if status:
        q = q.filter(models.Order.status == status)

    total       = q.count()
    total_pages = max(1, -(-total // ADMIN_PER_PAGE))
    orders      = (q.order_by(models.Order.created_at.desc())
                    .offset((page - 1) * ADMIN_PER_PAGE)
                    .limit(ADMIN_PER_PAGE).all())

    return templates.TemplateResponse("orders_list.html", {
        "request":     request,
        "orders":      orders,
        "total":       total,
        "page":        page,
        "total_pages": total_pages,
        "pages":       list(range(1, total_pages + 1)),
        "status_filter": status,
        "admin":       request.session["admin"],
    })
