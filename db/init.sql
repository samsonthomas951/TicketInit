-- ============================================================
--  TicketInit  –  Database Schema + Seed Data
--  PostgreSQL 16
-- ============================================================

-- ── Extensions ───────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Categories ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR(100) NOT NULL UNIQUE,
    slug  VARCHAR(100) NOT NULL UNIQUE,
    icon  VARCHAR(50)           -- Font Awesome class e.g. fa-music
);

-- ── Events ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
    id           SERIAL PRIMARY KEY,
    slug         VARCHAR(255) NOT NULL UNIQUE,
    title        VARCHAR(255) NOT NULL,
    description  TEXT,
    poster_url   VARCHAR(500),
    venue        VARCHAR(255),
    location     VARCHAR(500),
    start_date   TIMESTAMPTZ  NOT NULL,
    end_date     TIMESTAMPTZ,
    min_price    NUMERIC(10,2),        -- NULL = free
    is_free      BOOLEAN  DEFAULT FALSE,
    category_id  INT REFERENCES categories(id) ON DELETE SET NULL,
    organizer    VARCHAR(255),
    is_published BOOLEAN  DEFAULT TRUE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── Ticket Tiers ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ticket_tiers (
    id          SERIAL PRIMARY KEY,
    event_id    INT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    price       NUMERIC(10,2) NOT NULL,
    capacity    INT,
    sold        INT DEFAULT 0,
    description TEXT,
    sort_order  INT DEFAULT 0
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_events_start_date   ON events(start_date);
CREATE INDEX IF NOT EXISTS idx_events_category_id  ON events(category_id);
CREATE INDEX IF NOT EXISTS idx_events_is_published ON events(is_published);
CREATE INDEX IF NOT EXISTS idx_ticket_tiers_event  ON ticket_tiers(event_id);
-- ── Orders ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id               SERIAL PRIMARY KEY,
    uuid             VARCHAR(36) NOT NULL UNIQUE,
    name             VARCHAR(255) NOT NULL,
    email            VARCHAR(255) NOT NULL,
    phone            VARCHAR(30)  NOT NULL,
    payment_method   VARCHAR(50)  NOT NULL,
    total            NUMERIC(10,2) NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'pending',
    failure_reason   TEXT,
    items_json       TEXT,
    created_at       TIMESTAMPTZ  DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_uuid   ON orders(uuid);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);



-- ============================================================
--  SEED DATA
-- ============================================================

-- Categories
INSERT INTO categories (name, slug, icon) VALUES
  ('Music',       'music',       'fa-music'),
  ('Sports',      'sports',      'fa-trophy'),
  ('Arts',        'arts',        'fa-palette'),
  ('Food & Drink','food',        'fa-utensils'),
  ('Tech',        'tech',        'fa-laptop-code'),
  ('Comedy',      'comedy',      'fa-face-laugh'),
  ('Networking',  'networking',  'fa-handshake'),
  ('Wellness',    'wellness',    'fa-heart-pulse')
ON CONFLICT DO NOTHING;

-- ── UPCOMING EVENTS ──────────────────────────────────────────────────────────

-- 1. Abbas Intelligence Video Launch
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('abbas-intelligence-video-launch',
 'Abbas Intelligence Video Launch',
 'Join us for the official video launch of Abbas Intelligence — a groundbreaking audio-visual project blending afro-fusion and spoken word. Live performances, Q&A with the artist, and exclusive merch drops.',
 'https://picsum.photos/seed/abbas/600/450',
 'Iris Lounge', 'Marsabit Plaza, Ngong Rd, Nairobi',
 NOW() + INTERVAL '3 days',
 NOW() + INTERVAL '3 days 4 hours',
 1000, FALSE,
 (SELECT id FROM categories WHERE slug='music'),
 'Abbas Music Group');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (1, 'General Admission', 1000, 300, 120, 'Standing area access', 1),
  (1, 'VIP Table',         3000,  40,  18, 'Reserved table + bottle service', 2);

-- 2. The Discography
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('the-discography',
 'The Discography',
 'A curated evening celebrating Kenya''s finest music catalogue. Genre-spanning, DJ-led sets that journey through Kenyan music history — from benga to gengetone.',
 'https://picsum.photos/seed/discography/600/450',
 'Homeboyz Entertainment Studios', 'Muchai Drive, Nairobi',
 NOW() + INTERVAL '5 days',
 NOW() + INTERVAL '5 days 5 hours',
 1000, FALSE,
 (SELECT id FROM categories WHERE slug='music'),
 'Homeboyz Entertainment');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (2, 'Early Bird',  1000, 200, 200, 'Sold out — next tier available', 1),
  (2, 'Standard',    1500, 300,  80, 'General admission', 2),
  (2, 'VIP',         4000,  30,   5, 'Lounge access + 1 complimentary drink', 3);

-- 3. Raps & Rhymez @ The Labzz
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('raps-rhymez-at-labzz',
 'Raps & Rhymez @ The Labzz',
 'Kenya''s premier open-mic hip-hop night returns. Freestyles, cyphers, and live beat-battles in an intimate studio setting.',
 'https://picsum.photos/seed/rapsrhymez/600/450',
 'HIT Labzz', 'Homeboyz Entertainment Studios, Muchai Drive, Nairobi',
 NOW() + INTERVAL '6 days',
 NOW() + INTERVAL '6 days 4 hours',
 500, FALSE,
 (SELECT id FROM categories WHERE slug='music'),
 'HIT Labzz Collective');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (3, 'General',  500, 150,  60, 'Standing admission', 1),
  (3, 'Artist Pass', 0, 20,   5, 'For performing artists — free', 2);

-- 4. Champagne Stakes – Ngong Racecourse
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('champagne-stakes',
 'Champagne Stakes',
 'The most glamorous race day of the season! Dress to impress, enjoy live racing action, and celebrate in the champagne enclosure with Nairobi''s finest.',
 'https://picsum.photos/seed/champagnestakes/600/450',
 'Ngong Racecourse', 'Ngong Rd, Nairobi',
 NOW() + INTERVAL '5 days',
 NOW() + INTERVAL '5 days 8 hours',
 100, FALSE,
 (SELECT id FROM categories WHERE slug='sports'),
 'Jockey Club of Kenya');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (4, 'Paddock (General)',  100,  2000, 800, 'General race day access', 1),
  (4, 'Members Enclosure',  500,   500, 200, 'Members area + track-side viewing', 2),
  (4, 'Champagne Lounge', 3500,    80,  42, 'VIP lounge + Champagne + 3-course meal', 3);

-- 5. CTRL+OONTZ
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('ctrloontz',
 'CTRL+OONTZ',
 'Nairobi''s biggest electronic music festival under one roof. International and local DJs across three stages — techno, house, and ambient. 12 hours of non-stop sound.',
 'https://picsum.photos/seed/ctrloontz/600/450',
 'Carnivore Simba Saloon', 'Carnivore Grounds, Nairobi',
 NOW() + INTERVAL '17 days',
 NOW() + INTERVAL '17 days 12 hours',
 1000, FALSE,
 (SELECT id FROM categories WHERE slug='music'),
 'OONTZ Events');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (5, 'Early Bird',   1000, 500, 500, 'Sold out', 1),
  (5, 'Standard',     1500, 800, 320, 'General admission', 2),
  (5, 'VIP',          4000, 100,  40, 'VIP area + lounge seating', 3),
  (5, 'Backstage All-Access', 8000, 20, 8, 'Artist meet & greet included', 4);

-- 6. BEATS AND CARS
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('beats-and-cars',
 'BEATS AND CARS',
 'A 2-day festival combining Kenya''s car culture with live music. Expect supercar showcases, drifting demos, and headline DJ sets across two nights.',
 'https://picsum.photos/seed/beatscars/600/450',
 'LAPIS AUTOCITY', 'Mombasa Rd, Nairobi',
 NOW() + INTERVAL '32 days',
 NOW() + INTERVAL '33 days',
 800, FALSE,
 (SELECT id FROM categories WHERE slug='music'),
 'Autocity Events');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (6, 'Day Pass',     800,  1000, 200, 'Single-day entry', 1),
  (6, 'Weekend Pass', 1400, 1000, 180, 'Both days', 2),
  (6, 'VIP Weekend',  5000,   80,  15, 'VIP parking + lounge both days', 3);

-- 7. Nairobi Tech Summit 2026
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('nairobi-tech-summit-2026',
 'Nairobi Tech Summit 2026',
 'Kenya''s leading technology conference bringing together 500+ innovators, investors, and founders. Keynotes, workshops, demos, and networking.',
 'https://picsum.photos/seed/techsummit/600/450',
 'Sarit Expo Centre', 'Westlands, Nairobi',
 NOW() + INTERVAL '20 days',
 NOW() + INTERVAL '21 days',
 2500, FALSE,
 (SELECT id FROM categories WHERE slug='tech'),
 'iHub Nairobi');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (7, 'Startup Founder', 2500, 200, 90, 'Full 2-day access + workshop', 1),
  (7, 'Investor Pass',   5000,  50, 22, 'All-access + VIP networking dinner', 2),
  (7, 'Student',         1000, 100, 65, 'Full conference access — valid student ID', 3);

-- 8. Nairobi Food Festival
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('nairobi-food-festival-2026',
 'Nairobi Food Festival 2026',
 'Celebrate East Africa''s culinary richness at the biggest food festival in Kenya. 80+ vendors, celebrity chefs, cooking classes, and live entertainment.',
 'https://picsum.photos/seed/foodfest/600/450',
 'Uhuru Gardens', 'Langata Rd, Nairobi',
 NOW() + INTERVAL '14 days',
 NOW() + INTERVAL '16 days',
 500, FALSE,
 (SELECT id FROM categories WHERE slug='food'),
 'Nairobi Food Co.');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (8, 'Day Ticket',     500, 5000, 1800, 'Single-day access', 1),
  (8, '3-Day Pass',    1200, 2000,  600, 'Full festival pass', 2),
  (8, 'Chef''s Table', 6000,   20,    8, 'Exclusive 5-course meal with a celebrity chef', 3);

-- 9. Stand Up Nairobi – Comedy Night
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('stand-up-nairobi-june',
 'Stand Up Nairobi – June Edition',
 'Kenya''s funniest comedians take the stage for a night of unfiltered laughter. Headlined by Churchill Show alumni.',
 'https://picsum.photos/seed/standup/600/450',
 'The Alchemist', 'Westlands, Nairobi',
 NOW() + INTERVAL '10 days',
 NOW() + INTERVAL '10 days 3 hours',
 800, FALSE,
 (SELECT id FROM categories WHERE slug='comedy'),
 'Laugh Factory Kenya');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (9, 'Standard',  800, 300, 140, 'General admission', 1),
  (9, 'VIP Table', 2500,  40,  20, 'Reserved front table for 4', 2);

-- 10. Yoga in the Park – Free
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('yoga-in-the-park-june',
 'Yoga in the Park',
 'Free outdoor yoga session for all levels. Bring your mat and enjoy a guided 90-minute flow in the heart of Nairobi.',
 'https://picsum.photos/seed/yoga/600/450',
 'Karura Forest Amphitheatre', 'Karura Forest, Nairobi',
 NOW() + INTERVAL '7 days 7 hours',
 NOW() + INTERVAL '7 days 9 hours',
 NULL, TRUE,
 (SELECT id FROM categories WHERE slug='wellness'),
 'NBO Wellness Collective');

-- ── PAST EVENTS ──────────────────────────────────────────────────────────────

-- 11. Hype Sounds (Past - Free)
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('hype-sounds',
 'Hype Sounds',
 'An afternoon of hype culture — street fashion, skateboarding demos, and underground hip-hop.',
 'https://picsum.photos/seed/hypesounds/600/450',
 'HIT Labzz', 'Homeboyz Entertainment Studios, Muchai Drive, Nairobi',
 NOW() - INTERVAL '3 days',
 NOW() - INTERVAL '3 days' + INTERVAL '4 hours',
 NULL, TRUE,
 (SELECT id FROM categories WHERE slug='music'),
 'HIT Labzz');

-- 12. ICEMAN Listening Party (Past)
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('iceman-listening-party',
 'ICEMAN Listening Party',
 'Exclusive first-listen of the debut album "ICEMAN" in a fully immersive audio experience.',
 'https://picsum.photos/seed/iceman/600/450',
 'Homeboyz Entertainment Studios', 'Muchai Drive, Nairobi',
 NOW() - INTERVAL '4 days',
 NOW() - INTERVAL '4 days' + INTERVAL '3 hours',
 500, FALSE,
 (SELECT id FROM categories WHERE slug='music'),
 'Freezer Records');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (12, 'General',  500, 200, 200, 'Sold out', 1),
  (12, 'Platinum', 1500,  30,  30, 'Sold out', 2);

-- 13. Friday Freakuency (Past)
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('friday-freakuency',
 'Friday Freakuency',
 'The weekly Friday night session at Homeboyz — Afrobeats, R&B, and late night vibes.',
 'https://picsum.photos/seed/freakuency/600/450',
 'Homeboyz Entertainment Studios', 'Muchai Drive, Nairobi',
 NOW() - INTERVAL '25 days',
 NOW() - INTERVAL '25 days' + INTERVAL '5 hours',
 500, FALSE,
 (SELECT id FROM categories WHERE slug='music'),
 'Homeboyz Entertainment');

-- 14. 2026 Kenya Derby (Past)
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('2026-kenya-derby',
 '2026 Kenya Derby',
 'The most prestigious flat race in East Africa. A full card of 8 races culminating in the Derby.',
 'https://picsum.photos/seed/kenyaderby/600/450',
 'Ngong Racecourse', 'Ngong Rd, Nairobi',
 NOW() - INTERVAL '37 days',
 NOW() - INTERVAL '37 days' + INTERVAL '8 hours',
 100, FALSE,
 (SELECT id FROM categories WHERE slug='sports'),
 'Jockey Club of Kenya');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (14, 'Paddock',   100, 3000, 3000, 'Sold out', 1),
  (14, 'Members',   500,  500,  500, 'Sold out', 2),
  (14, 'Directors Box', 8000, 40, 40, 'Sold out', 3);

-- 15. Funk & Soul (Past)
INSERT INTO events (slug, title, description, poster_url, venue, location, start_date, end_date, min_price, is_free, category_id, organizer) VALUES
('funk-soul',
 'Funk & Soul',
 'A night dedicated to the golden era of funk and soul music. Live band + DJ sets.',
 'https://picsum.photos/seed/funksoul/600/450',
 'Simba Saloon, Carnivore', 'Carnivore Grounds, Langata Rd, Nairobi',
 NOW() - INTERVAL '59 days',
 NOW() - INTERVAL '59 days' + INTERVAL '6 hours',
 1500, FALSE,
 (SELECT id FROM categories WHERE slug='music'),
 'Carnivore Events');

INSERT INTO ticket_tiers (event_id, name, price, capacity, sold, description, sort_order) VALUES
  (15, 'General',  1500, 800, 800, 'Sold out', 1),
  (15, 'VIP',      4000, 60,   60, 'Sold out', 2);

-- Verify seed
DO $$
DECLARE
  ev_count INT;
  tier_count INT;
BEGIN
  SELECT COUNT(*) INTO ev_count FROM events;
  SELECT COUNT(*) INTO tier_count FROM ticket_tiers;
  RAISE NOTICE 'Seed complete: % events, % ticket tiers', ev_count, tier_count;
END $$;
