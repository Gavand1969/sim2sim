// Wire CTA URLs from window globals injected by license.js (or fall back).
// Moved out of inline <script> so it complies with CSP script-src 'self'.
document.addEventListener("DOMContentLoaded", () => {
  const proCTA  = document.getElementById("cta-pro");
  const teamCTA = document.getElementById("cta-team");
  const proUrl  = window.STRIPE_PRO_URL  || "https://buy.stripe.com/aFabJ2gynea84dOd7LaEE01";
  const teamUrl = window.STRIPE_TEAM_URL || "https://buy.stripe.com/4gMfZigynaXW25Gc3HaEE00";
  if (proCTA)  proCTA.href = proUrl;
  if (teamCTA) teamCTA.href = teamUrl;
});
