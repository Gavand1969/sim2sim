# Sim2Sim — Launch Checklist

A 30-minute path from "freshly merged PR" to "taking real money".

## 1. Buy your domain (5 min)

Recommended: **sim2sim.app** ($14–20/yr) — short, on-brand, no aftermarket fee.
(`sim2sim.com` is parked at $5,000 — skip it for now.)

Other strong options:
- `sim2sim.tools` — fits the product perfectly
- `getsim2sim.com` or `usesim2sim.com` — keeps you in `.com` for ~$12/yr
- `sim2sim.ai` — premium ($70–100/yr) but great if you want the AI angle

Buy at: [Namecheap](https://namecheap.com), [Porkbun](https://porkbun.com), or [Cloudflare Registrar](https://cloudflare.com/products/registrar/) (no markup).

## 2. Connect domain to Replit (5 min)

1. In Replit: **Deployments → Settings → Custom Domains → Link domain**.
2. Replit shows you a CNAME / A record to add at your registrar.
3. Paste it into your registrar's DNS settings. Wait 5–10 min for propagation.

## 3. Create Stripe Payment Links (5 min)

In your Stripe dashboard:

1. **Product → Add product** — "Sim2Sim Pro", one-time, $49.00.
2. **Product → Add product** — "Sim2Sim Team", one-time, $249.00.
3. Click each product → **Pricing → Create payment link**.
4. Under **After payment**, set **Show confirmation page** to **Redirect** → `https://yourdomain.app/account`.
5. (Optional but recommended) Under **Advanced options → Metadata**, add `tier=pro` (or `team`). Sim2Sim falls back to the amount, but metadata is more robust.
6. Copy both Payment Link URLs.

## 4. Wire the webhook (3 min)

1. Stripe Dashboard → **Developers → Webhooks → Add endpoint**.
2. URL: `https://yourdomain.app/api/billing/webhook`
3. Event: select **`checkout.session.completed`**.
4. Click **Add endpoint**, then reveal **Signing secret** (`whsec_...`).

## 5. Sign up for Resend (2 min)

1. Create an account at [resend.com](https://resend.com).
2. (Optional for launch) Verify a sending domain — until then, emails go from `onboarding@resend.dev`, which works but looks less polished.
3. Copy your API key (`re_...`).

## 6. Set environment variables in Replit (5 min)

In **Replit → Secrets**, add:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `ALLOWED_ORIGIN` | `https://yourdomain.app` (the one from step 2) |
| `APP_BASE_URL` | `https://yourdomain.app` |
| `SIM2SIM_LICENSE_SECRET` | run `python -c "import secrets;print(secrets.token_urlsafe(48))"` and paste the output |
| `STRIPE_WEBHOOK_SECRET` | from step 4 |
| `STRIPE_PRICE_PRO_CENTS` | `4900` |
| `STRIPE_PRICE_TEAM_CENTS` | `24900` |
| `RESEND_API_KEY` | from step 5 |
| `RESEND_FROM` | `Sim2Sim <hello@yourdomain.app>` (or leave default during testing) |
| `ANTHROPIC_API_KEY` | your existing key |

## 7. Paste your Payment Link URLs (2 min)

Open `static/pricing.html` and replace the two `__configure_me__` placeholders (search for `STRIPE_PRO_URL` / `STRIPE_TEAM_URL`), or — cleaner — add this script block right above `</head>` in `pricing.html`:

```html
<script>
  window.SIM2SIM_CONFIG = {
    stripeProUrl:  "https://buy.stripe.com/your-pro-link",
    stripeTeamUrl: "https://buy.stripe.com/your-team-link",
  };
</script>
```

## 8. Deploy

In Replit, click **Deploy**. The web server is `uvicorn main:app --host 0.0.0.0 --port $PORT`. The SQLite DB persists in the home directory across deploys.

## 9. Test the full flow (10 min)

1. Open your live URL → see Pricing nav.
2. Click **Buy Pro** → it opens Stripe Checkout.
3. Use Stripe **test mode** first: card `4242 4242 4242 4242`, any future date, any CVC.
4. Complete checkout → Stripe redirects you to `/account`.
5. Check your email — license key should arrive within seconds.
6. Paste the key into Account → status flips to "Pro".
7. Go to `/` → click any model → click **⬇ Excel** → file downloads.

If steps 5–7 fail, check **Stripe → Developers → Webhooks → your endpoint → Events** for delivery errors, and **Replit → Logs** for server errors.

## 10. Flip to live mode

1. Stripe Dashboard top-right: switch from **Test mode** to **Live mode**.
2. Re-create Payment Links in live mode (test-mode links don't carry over).
3. Re-create the webhook endpoint in live mode → copy the new signing secret → update `STRIPE_WEBHOOK_SECRET` in Replit Secrets.
4. Redeploy.
5. Make a real $1 test purchase (or wait for the first real customer — your call).

---

## Optional polish for v1.1

- Verify a sending domain in Resend so emails come from `hello@yourdomain.app`.
- Add OpenGraph image and meta description for nicer social sharing.
- Add a "Save scenario" Pro feature (we already gate it in the pricing copy).
- Branded PDFs for the Team tier (logo upload field on the account page).
- A simple admin page at `/admin` (gated by `ADMIN_PASSWORD`) showing recent purchases.
