-- ============================================================
--  Migration: Add M-Pesa fields + order_tickets table
--  Run this if upgrading an existing TicketInit database.
--  Safe to run multiple times (uses IF NOT EXISTS / DO blocks).
-- ============================================================
 
-- Add M-Pesa fields to orders table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='orders' AND column_name='mpesa_checkout_request_id'
    ) THEN
        ALTER TABLE orders ADD COLUMN mpesa_checkout_request_id VARCHAR(100);
        CREATE INDEX IF NOT EXISTS idx_orders_mpesa_checkout ON orders(mpesa_checkout_request_id);
    END IF;
 
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='orders' AND column_name='mpesa_receipt'
    ) THEN
        ALTER TABLE orders ADD COLUMN mpesa_receipt VARCHAR(50);
    END IF;
END $$;
 
-- Create order_tickets table (QR code / door scan)
CREATE TABLE IF NOT EXISTS order_tickets (
    id           SERIAL PRIMARY KEY,
    order_id     INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    ticket_code  VARCHAR(64) NOT NULL UNIQUE,
    tier_name    VARCHAR(100) NOT NULL,
    event_title  VARCHAR(255) NOT NULL,
    used         BOOLEAN DEFAULT FALSE,
    used_at      TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
 
CREATE INDEX IF NOT EXISTS idx_order_tickets_order   ON order_tickets(order_id);
CREATE INDEX IF NOT EXISTS idx_order_tickets_code    ON order_tickets(ticket_code);
 
-- Admin users table (in case it doesn't exist yet)
CREATE TABLE IF NOT EXISTS admin_users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);