// Bootstrap Swagger UI for the Sim2Sim API docs.
// Lives in /static/js/ instead of inline so our CSP (script-src 'self'
// https://cdn.jsdelivr.net) lets it run.
window.addEventListener("DOMContentLoaded", function () {
  // SwaggerUIBundle is loaded from cdn.jsdelivr.net via a <script> tag in the
  // page; this file just configures and mounts it.
  if (typeof SwaggerUIBundle === "undefined") {
    console.error("SwaggerUIBundle failed to load from CDN");
    return;
  }
  SwaggerUIBundle({
    url: "/openapi.json",
    dom_id: "#swagger-ui",
    layout: "BaseLayout",
    deepLinking: true,
    showExtensions: true,
    showCommonExtensions: true,
    presets: [
      SwaggerUIBundle.presets.apis,
      SwaggerUIBundle.SwaggerUIStandalonePreset,
    ],
  });
});
